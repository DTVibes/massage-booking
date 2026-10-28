import asyncio

from sqlalchemy import select

from app import worker
from app.models import Appointment, AppointmentStatus, NotificationJob, NotificationStatus, User
from app.services import notifications
from app.services.settings_service import get_app_settings
from tests.conftest import book, login, msk


class FakeSender:
    def __init__(self, fail_with=None):
        self.sent: list[tuple[int, str]] = []
        self.fail_with = fail_with

    async def __call__(self, chat_id, text, with_button):
        if self.fail_with:
            raise self.fail_with
        self.sent.append((chat_id, text))


def jobs(db, **filters):
    db.expire_all()
    q = select(NotificationJob).order_by(NotificationJob.id)
    for k, v in filters.items():
        q = q.where(getattr(NotificationJob, k) == v)
    return db.scalars(q).all()


def run(sender):
    return asyncio.run(worker.process_due_jobs(sender))


def test_jobs_created_on_booking(api, client_headers, admin_headers, service_id, db):
    book(api, client_headers, service_id, msk(4, 12))
    types = sorted((j.notification_type, j.recipient_telegram_id) for j in jobs(db))
    assert types == [("admin_created", 999), ("client_created", 1001), ("reminder_24h", 1001), ("reminder_2h", 1001)]
    r24 = jobs(db, notification_type="reminder_24h")[0]
    assert r24.scheduled_at == msk(3, 12)


def test_no_reminder_when_too_close(api, client_headers, service_id, db, clock):
    clock.now = msk(3, 0)
    book(api, client_headers, service_id, msk(3, 13))  # меньше 24 ч, больше 2 ч
    assert [j.notification_type for j in jobs(db) if j.notification_type.startswith("reminder")] == ["reminder_2h"]


def test_confirmations_and_reminders_sent_once(api, client_headers, admin_headers, service_id, db, clock):
    book(api, client_headers, service_id, msk(4, 12))
    sender = FakeSender()
    assert run(sender) == 2  # подтверждение клиенту и уведомление администратору
    texts = dict(sender.sent)
    assert "Вы записаны" in texts[1001] and "Классический массаж" in texts[1001]
    assert "Новая запись" in texts[999] and "+79161234567" in texts[999] and "Иван" in texts[999]
    assert run(sender) == 0  # повторный запуск ничего не дублирует

    clock.now = msk(3, 12)
    run(sender)
    clock.now = msk(4, 10)
    run(sender)
    clock.now = msk(4, 11)
    run(sender)
    reminders = [t for _, t in sender.sent if "Напоминание" in t]
    assert len(reminders) == 2 and "завтра" in reminders[0] and "через 2 ч" in reminders[1]
    assert all(j.status == NotificationStatus.sent for j in jobs(db))


def test_reminder_enqueue_is_deduplicated(api, client_headers, service_id, db, clock):
    a = book(api, client_headers, service_id, msk(4, 12)).json()
    appt = db.get(Appointment, __import__("uuid").UUID(a["id"]))
    client = db.get(User, appt.client_id)
    notifications.schedule_reminders(db, get_app_settings(db), appt, client, clock.now)
    notifications.schedule_reminders(db, get_app_settings(db), appt, client, clock.now)
    db.commit()
    assert len(jobs(db, notification_type="reminder_24h")) == 1


def test_cancel_and_reschedule_notifications(api, client_headers, admin_headers, service_id, db, clock):
    a = book(api, client_headers, service_id, msk(4, 12)).json()
    run(FakeSender())
    api.post(f"/api/v1/appointments/{a['id']}/reschedule", json={"starts_at": msk(5, 12).isoformat()},
             headers=client_headers)
    old_reminders = [j for j in jobs(db) if j.notification_type.startswith("reminder") and j.status == NotificationStatus.cancelled]
    assert len(old_reminders) == 2
    new_reminders = [j for j in jobs(db) if j.notification_type.startswith("reminder") and j.status == NotificationStatus.pending]
    assert sorted(j.scheduled_at for j in new_reminders) == [msk(4, 12), msk(5, 10)]
    sender = FakeSender()
    run(sender)
    texts = dict(sender.sent)
    assert "перенесена" in texts[1001] and "Было:" in texts[1001]
    assert "перенёс" in texts[999]

    api.post(f"/api/v1/appointments/{a['id']}/cancel", headers=client_headers)
    sender = FakeSender()
    run(sender)
    texts = dict(sender.sent)
    assert "отменена" in texts[1001] and "отменил" in texts[999]
    assert all(j.status != NotificationStatus.pending for j in jobs(db))


def test_admin_actions_do_not_notify_admin(api, client_headers, admin_headers, service_id, db):
    a = book(api, client_headers, service_id, msk(4, 12)).json()
    run(FakeSender())
    api.patch(f"/api/v1/admin/appointments/{a['id']}", json={"status": "cancelled_by_admin"}, headers=admin_headers)
    sender = FakeSender()
    run(sender)
    assert [c for c, _ in sender.sent] == [1001]
    assert "массажистом" in sender.sent[0][1]


def test_telegram_error_does_not_lose_booking_and_retries(api, client_headers, service_id, db, clock):
    a = book(api, client_headers, service_id, msk(4, 12)).json()
    failing = FakeSender(fail_with=ConnectionError("network down"))
    for _ in range(worker.MAX_ATTEMPTS + 2):
        run(failing)
        clock.shift(minutes=30)
    job = jobs(db, notification_type="client_created")[0]
    assert job.status == NotificationStatus.failed and job.attempts == worker.MAX_ATTEMPTS
    assert "network down" in job.last_error
    assert db.get(Appointment, __import__("uuid").UUID(a["id"])).status == AppointmentStatus.booked


def test_retry_after_and_blocked_bot(api, client_headers, service_id, db, clock):
    book(api, client_headers, service_id, msk(4, 12))
    run(FakeSender(fail_with=worker.RetryAfterError(10)))
    job = jobs(db, notification_type="client_created")[0]
    assert job.status == NotificationStatus.pending and job.attempts == 0 and job.scheduled_at > clock.now
    clock.shift(seconds=20)
    run(FakeSender(fail_with=worker.PermanentSendError("blocked", bot_blocked=True)))
    assert jobs(db, notification_type="client_created")[0].status == NotificationStatus.failed
    user = db.scalar(select(User).where(User.telegram_id == 1001))
    assert user.bot_blocked
    # дальнейшие сообщения пользователю, заблокировавшему бота, не отправляются
    clock.now = msk(3, 12)
    sender = FakeSender()
    run(sender)
    assert sender.sent == []
    assert jobs(db, notification_type="reminder_24h")[0].status == NotificationStatus.skipped


def test_user_without_bot_access_is_skipped(api, service_id, db):
    from app.security import build_init_data

    init = build_init_data({"id": 7777, "first_name": "Тихий", "allows_write_to_pm": False}, "123456:TEST-TOKEN")
    h = {"Authorization": "Bearer " + api.post("/api/v1/auth/telegram", json={"init_data": init}).json()["token"]}
    api.patch("/api/v1/me/profile", json={"phone": "+79167777777"}, headers=h)
    book(api, h, service_id, msk(4, 12))
    sender = FakeSender()
    run(sender)
    assert [c for c, _ in sender.sent] == [999]
    job = jobs(db, notification_type="client_created")[0]
    assert job.status == NotificationStatus.skipped
