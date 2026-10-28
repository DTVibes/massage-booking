from sqlalchemy import select

from app.models import Appointment, AppointmentHistory, AppointmentStatus
from tests.conftest import book, login, msk


def test_client_cancel_allowed_6h_before(api, client_headers, service_id, clock):
    a = book(api, client_headers, service_id, msk(2, 16)).json()
    clock.now = msk(2, 10)  # ровно за 6 часов
    r = api.post(f"/api/v1/appointments/{a['id']}/cancel", headers=client_headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled_by_client" and r.json()["cancelled_at"]


def test_client_cancel_forbidden_less_than_6h(api, client_headers, admin_headers, service_id, clock):
    a = book(api, client_headers, service_id, msk(2, 16)).json()
    clock.now = msk(2, 10, 1)
    mine = api.get("/api/v1/appointments/my", headers=client_headers).json()["upcoming"][0]
    assert mine["can_cancel"] is False and mine["can_reschedule"] is False
    r = api.post(f"/api/v1/appointments/{a['id']}/cancel", headers=client_headers)
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "too_late_to_change" and "6 ч" in err["message"] and "свяж" in err["message"].lower()
    # администратор может отменить независимо от срока
    r = api.patch(f"/api/v1/admin/appointments/{a['id']}", json={"status": "cancelled_by_admin", "reason": "Болезнь"},
                  headers=admin_headers)
    assert r.status_code == 200 and r.json()["status"] == "cancelled_by_admin"
    assert r.json()["cancelled_by"] is not None


def test_cannot_touch_foreign_appointment(api, client_headers, service_id):
    a = book(api, client_headers, service_id, msk(3, 10)).json()
    other = login(api, 1800, "Чужой")
    assert api.post(f"/api/v1/appointments/{a['id']}/cancel", headers=other).status_code == 404
    r = api.post(f"/api/v1/appointments/{a['id']}/reschedule", json={"starts_at": msk(3, 12).isoformat()}, headers=other)
    assert r.status_code == 404
    r = api.get("/api/v1/availability/slots", headers=other,
                params={"service_id": service_id, "date": "2026-11-03", "exclude_appointment_id": a["id"]})
    assert r.status_code == 404


def test_reschedule_keeps_history(api, client_headers, admin_headers, service_id, db):
    a = book(api, client_headers, service_id, msk(3, 10)).json()
    r = api.post(f"/api/v1/appointments/{a['id']}/reschedule", json={"starts_at": msk(3, 14).isoformat()},
                 headers=client_headers)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == a["id"] and r.json()["starts_at"].startswith("2026-11-03T11:00")
    detail = api.get(f"/api/v1/admin/appointments/{a['id']}", headers=admin_headers).json()
    resched = [h for h in detail["history"] if h["action"] == "rescheduled"][0]
    assert resched["old_starts_at"].startswith("2026-11-03T07:00") and resched["new_starts_at"].startswith("2026-11-03T11:00")
    # старый слот освободился
    slots = api.get("/api/v1/availability/slots", params={"service_id": service_id, "date": "2026-11-03"},
                    headers=client_headers).json()
    assert "10:00" in [s["local_time"] for s in slots]


def test_reschedule_by_30_minutes_overlapping_itself(api, client_headers, service_id):
    a = book(api, client_headers, service_id, msk(3, 10)).json()
    slots = api.get("/api/v1/availability/slots", headers=client_headers,
                    params={"service_id": service_id, "date": "2026-11-03", "exclude_appointment_id": a["id"]}).json()
    assert "10:30" in [s["local_time"] for s in slots]
    r = api.post(f"/api/v1/appointments/{a['id']}/reschedule", json={"starts_at": msk(3, 10, 30).isoformat()},
                 headers=client_headers)
    assert r.status_code == 200, r.text


def test_failed_reschedule_keeps_original(api, client_headers, service_id, db):
    a = book(api, client_headers, service_id, msk(3, 10)).json()
    other = login(api, 1900, "Другой")
    api.patch("/api/v1/me/profile", json={"phone": "+79160000099"}, headers=other)
    assert book(api, other, service_id, msk(3, 14)).status_code == 201
    r = api.post(f"/api/v1/appointments/{a['id']}/reschedule", json={"starts_at": msk(3, 14, 30).isoformat()},
                 headers=client_headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "slot_taken"
    appt = db.scalar(select(Appointment).where(Appointment.id == a["id"]))
    assert appt.status == AppointmentStatus.booked and appt.starts_at == msk(3, 10)
    assert db.scalars(select(AppointmentHistory).where(AppointmentHistory.action == "rescheduled")).all() == []


def test_failed_reschedule_db_level_race_keeps_original(client_headers, api, service_id, db):
    """Если слот заняли между проверкой и сохранением, срабатывает exclusion constraint и откат."""
    from app.services import booking
    from app.services.availability import ScheduleContext

    a = book(api, client_headers, service_id, msk(3, 10)).json()
    other = login(api, 1901, "Гонщик")
    api.patch("/api/v1/me/profile", json={"phone": "+79160000098"}, headers=other)
    assert book(api, other, service_id, msk(3, 15)).status_code == 201

    original = ScheduleContext.is_busy
    ScheduleContext.is_busy = lambda self, *a, **k: False  # имитируем гонку: предпроверка «не видит» запись
    try:
        r = api.post(f"/api/v1/appointments/{a['id']}/reschedule", json={"starts_at": msk(3, 15).isoformat()},
                     headers=client_headers)
    finally:
        ScheduleContext.is_busy = original
    assert r.status_code == 409
    db.expire_all()
    appt = db.get(Appointment, booking.uuid.UUID(a["id"]))
    assert appt.status == AppointmentStatus.booked and appt.starts_at == msk(3, 10)


def test_reschedule_too_late(api, client_headers, service_id, clock):
    a = book(api, client_headers, service_id, msk(2, 14)).json()
    clock.now = msk(2, 9)
    r = api.post(f"/api/v1/appointments/{a['id']}/reschedule", json={"starts_at": msk(3, 14).isoformat()},
                 headers=client_headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "too_late_to_change"


def test_reschedule_disabled_by_settings(api, client_headers, admin_headers, service_id):
    a = book(api, client_headers, service_id, msk(3, 10)).json()
    api.patch("/api/v1/admin/settings", json={"allow_client_reschedule": False}, headers=admin_headers)
    r = api.post(f"/api/v1/appointments/{a['id']}/reschedule", json={"starts_at": msk(3, 14).isoformat()},
                 headers=client_headers)
    assert r.status_code == 403
    # админ переносит вручную, в том числе вне графика
    r = api.patch(f"/api/v1/admin/appointments/{a['id']}", headers=admin_headers,
                  json={"starts_at": msk(7, 12).isoformat(), "ignore_schedule": True})
    assert r.status_code == 200 and r.json()["starts_at"].startswith("2026-11-07T09:00")


def test_my_appointments_sections(api, client_headers, admin_headers, service_id, clock):
    a1 = book(api, client_headers, service_id, msk(2, 10)).json()
    a2 = book(api, client_headers, service_id, msk(3, 10)).json()
    a3 = book(api, client_headers, service_id, msk(4, 10)).json()
    api.post(f"/api/v1/appointments/{a3['id']}/cancel", headers=client_headers)
    clock.now = msk(2, 11, 30)
    api.patch(f"/api/v1/admin/appointments/{a1['id']}", json={"status": "completed"}, headers=admin_headers)
    mine = api.get("/api/v1/appointments/my", headers=client_headers).json()
    assert [x["id"] for x in mine["upcoming"]] == [a2["id"]]
    assert [x["id"] for x in mine["history"]] == [a1["id"]]
    assert [x["id"] for x in mine["cancelled"]] == [a3["id"]]
