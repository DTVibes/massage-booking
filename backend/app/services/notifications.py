"""Постановка задач уведомлений в очередь (таблица notification_jobs).

Отправкой занимается отдельный процесс app.worker. Задачи создаются в той же транзакции,
что и изменение записи, поэтому не теряются при перезапуске и не создаются для
неудавшихся операций. Уникальный ключ (dedup_key, recipient) исключает дубли.
"""

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Appointment, AppSettings, NotificationJob, NotificationStatus, User, UserRole


def enqueue(db: Session, *, appointment_id, recipient: int, notification_type: str, dedup_key: str,
            scheduled_at: datetime, payload: dict | None = None) -> None:
    stmt = (
        insert(NotificationJob)
        .values(
            appointment_id=appointment_id,
            recipient_telegram_id=recipient,
            notification_type=notification_type,
            dedup_key=dedup_key,
            payload=payload,
            scheduled_at=scheduled_at,
            status=NotificationStatus.pending,
            attempts=0,
        )
        .on_conflict_do_nothing(constraint="uq_notification_jobs_dedup")
    )
    db.execute(stmt)


def admin_recipients(db: Session) -> set[int]:
    ids = set(get_settings().admin_telegram_ids)
    ids.update(
        tid
        for tid in db.scalars(
            select(User.telegram_id).where(User.role == UserRole.admin, User.is_active, User.telegram_id.is_not(None))
        )
    )
    return ids


def schedule_reminders(db: Session, settings: AppSettings, appt: Appointment, client: User, now: datetime) -> None:
    if client.telegram_id is None:
        return
    for hours in sorted(set(settings.reminder_hours or [])):
        at = appt.starts_at - timedelta(hours=hours)
        if at <= now:
            continue  # до визита осталось меньше — напоминание не отправляем
        enqueue(
            db,
            appointment_id=appt.id,
            recipient=client.telegram_id,
            notification_type=f"reminder_{hours}h",
            dedup_key=f"{appt.id}:reminder_{hours}h:{appt.starts_at.isoformat()}",
            scheduled_at=at,
            payload={"starts_at": appt.starts_at.isoformat()},
        )


def cancel_pending_reminders(db: Session, appointment_id) -> None:
    db.execute(
        update(NotificationJob)
        .where(
            NotificationJob.appointment_id == appointment_id,
            NotificationJob.status == NotificationStatus.pending,
            NotificationJob.notification_type.like("reminder_%"),
        )
        .values(status=NotificationStatus.cancelled, last_error="Запись отменена или перенесена")
    )


def notify_event(db: Session, settings: AppSettings, appt: Appointment, client: User, event: str,
                 by_admin: bool, now: datetime, event_id: str, payload: dict | None = None,
                 notify_client: bool = True) -> None:
    """event: created | cancelled | rescheduled."""
    if notify_client and client.telegram_id is not None:
        enqueue(
            db,
            appointment_id=appt.id,
            recipient=client.telegram_id,
            notification_type=f"client_{event}",
            dedup_key=f"{appt.id}:{event}:{event_id}",
            scheduled_at=now,
            payload=payload,
        )
    if by_admin:
        return  # администратор сам совершил действие — не уведомляем его же
    flag = {"created": settings.notify_admin_new, "cancelled": settings.notify_admin_cancel,
            "rescheduled": settings.notify_admin_reschedule}[event]
    if not flag:
        return
    for admin_id in admin_recipients(db):
        if admin_id == client.telegram_id:
            continue
        enqueue(
            db,
            appointment_id=appt.id,
            recipient=admin_id,
            notification_type=f"admin_{event}",
            dedup_key=f"{appt.id}:{event}:{event_id}",
            scheduled_at=now,
            payload=payload,
        )
