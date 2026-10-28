from sqlalchemy import func, select

from app.models import Appointment, AppointmentStatus
from tests.conftest import book, login, msk

WEEK = [{"weekday": wd, "is_working_day": wd < 5, "intervals": [{"start": "10:00", "end": "19:00"}] if wd < 5 else []}
        for wd in range(7)]


def test_schedule_change_warns_and_never_deletes(api, client_headers, admin_headers, service_id, db):
    a = book(api, client_headers, service_id, msk(4, 17)).json()  # среда 17:00
    days = [dict(d) for d in WEEK]
    days[2] = {"weekday": 2, "is_working_day": True, "intervals": [{"start": "10:00", "end": "15:00"}]}
    r = api.put("/api/v1/admin/schedule", json={"days": days}, headers=admin_headers)
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "schedule_conflicts" and err["details"][0]["appointment_id"] == a["id"]
    # график не изменился
    sched = api.get("/api/v1/admin/schedule", headers=admin_headers).json()
    assert sched["days"][2]["intervals"][0]["end"] == "19:00:00"
    # подтверждение: график меняется, запись остаётся активной
    r = api.put("/api/v1/admin/schedule", json={"days": days, "force": True}, headers=admin_headers)
    assert r.status_code == 200 and len(r.json()["conflicts"]) == 1
    assert db.get(Appointment, __import__("uuid").UUID(a["id"])).status == AppointmentStatus.booked
    assert api.get("/api/v1/admin/schedule/conflicts", headers=admin_headers).json()[0]["appointment_id"] == a["id"]


def test_closing_day_with_bookings_warns(api, client_headers, admin_headers, service_id, db):
    book(api, client_headers, service_id, msk(4, 12))
    body = {"starts_at": msk(4, 0).isoformat(), "ends_at": msk(5, 0).isoformat(), "exception_type": "closed"}
    r = api.post("/api/v1/admin/schedule/exceptions", json=body, headers=admin_headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "schedule_conflicts"
    assert api.get("/api/v1/admin/schedule", headers=admin_headers).json()["exceptions"] == []
    r = api.post("/api/v1/admin/schedule/exceptions", json={**body, "force": True}, headers=admin_headers)
    assert r.status_code == 201 and len(r.json()["conflicts"]) == 1
    assert db.scalar(select(func.count()).select_from(Appointment).where(Appointment.status == "booked")) == 1
    exc_id = r.json()["id"]
    assert api.delete(f"/api/v1/admin/schedule/exceptions/{exc_id}", headers=admin_headers).status_code == 204


def test_admin_views_and_filters(api, client_headers, admin_headers, service_id):
    book(api, client_headers, service_id, msk(3, 10))
    a2 = book(api, client_headers, service_id, msk(5, 10)).json()
    api.post(f"/api/v1/appointments/{a2['id']}/cancel", headers=client_headers)
    day = api.get("/api/v1/admin/appointments", params={"date_from": "2026-11-03", "date_to": "2026-11-03"},
                  headers=admin_headers).json()
    assert len(day) == 1 and day[0]["client"]["name"] == "Иван"
    week = api.get("/api/v1/admin/appointments", params={"date_from": "2026-11-02", "date_to": "2026-11-08"},
                   headers=admin_headers).json()
    assert len(week) == 2
    booked = api.get("/api/v1/admin/appointments", headers=admin_headers,
                     params={"date_from": "2026-11-01", "date_to": "2026-11-30", "status": "booked"}).json()
    assert len(booked) == 1
    r = api.get("/api/v1/admin/appointments", params={"date_from": "2026-11-01", "date_to": "2027-03-01"},
                headers=admin_headers)
    assert r.status_code == 422


def test_admin_manual_booking_new_client(api, admin_headers, service_id):
    r = api.post("/api/v1/admin/appointments", headers=admin_headers, json={
        "new_client": {"name": "Светлана", "phone": "89035556677"}, "service_id": service_id,
        "starts_at": msk(2, 10).isoformat(), "comment": "Записалась по телефону"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["client"]["phone"] == "+79035556677" and body["client"]["telegram_id"] is None
    assert body["history"][0]["action"] == "created" and body["history"][0]["actor_role"] == "admin"
    # пересечение запрещено и для администратора
    r = api.post("/api/v1/admin/appointments", headers=admin_headers, json={
        "client_id": body["client"]["id"], "service_id": service_id, "starts_at": msk(2, 10, 30).isoformat(),
        "ignore_schedule": True})
    assert r.status_code == 409


def test_admin_marks_completed_and_no_show(api, client_headers, admin_headers, service_id, clock):
    a = book(api, client_headers, service_id, msk(3, 10)).json()
    r = api.patch(f"/api/v1/admin/appointments/{a['id']}", json={"status": "completed"}, headers=admin_headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "visit_not_started"
    clock.now = msk(3, 11, 5)
    r = api.patch(f"/api/v1/admin/appointments/{a['id']}", json={"status": "no_show"}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["status"] == "no_show"
    r = api.patch(f"/api/v1/admin/appointments/{a['id']}", json={"comment": "Опоздал"}, headers=admin_headers)
    assert r.json()["comment"] == "Опоздал"


def test_clients_list_search_and_card(api, client_headers, admin_headers, service_id, clock):
    a = book(api, client_headers, service_id, msk(3, 10)).json()
    b = book(api, client_headers, service_id, msk(4, 10)).json()
    api.post(f"/api/v1/appointments/{b['id']}/cancel", headers=client_headers)
    for i in range(3):
        h = login(api, 4000 + i, f"Тест{i}")
        api.patch("/api/v1/me/profile", json={"phone": f"+7926000000{i}"}, headers=h)
    clock.now = msk(3, 11, 30)
    api.patch(f"/api/v1/admin/appointments/{a['id']}", json={"status": "completed"}, headers=admin_headers)

    page = api.get("/api/v1/admin/clients", params={"page_size": 2}, headers=admin_headers).json()
    assert page["total"] == 4 and len(page["items"]) == 2
    found = api.get("/api/v1/admin/clients", params={"q": "иван"}, headers=admin_headers).json()
    assert found["total"] == 1
    c = found["items"][0]
    assert c["completed_count"] == 1 and c["cancelled_count"] == 1 and c["last_visit_at"].startswith("2026-11-03T07:00")
    by_phone = api.get("/api/v1/admin/clients", params={"q": "9161234"}, headers=admin_headers).json()
    assert by_phone["total"] == 1

    r = api.patch(f"/api/v1/admin/clients/{c['id']}", json={"admin_notes": "Любит сильный массаж"}, headers=admin_headers)
    card = api.get(f"/api/v1/admin/clients/{c['id']}", headers=admin_headers).json()
    assert card["admin_notes"] == "Любит сильный массаж" and len(card["appointments"]) == 2
    # заметки не видны клиенту
    assert "Любит" not in api.get("/api/v1/me", headers=client_headers).text


def test_services_management(api, admin_headers):
    r = api.post("/api/v1/admin/services", headers=admin_headers,
                 json={"name": "Антицеллюлитный", "description": "Курс", "duration_minutes": 45, "price_minor": 200000})
    assert r.status_code == 201 and r.json()["currency"] == "RUB"
    sid = r.json()["id"]
    assert api.patch(f"/api/v1/admin/services/{sid}", json={"is_active": False}, headers=admin_headers).status_code == 200
    assert len(api.get("/api/v1/admin/services", headers=admin_headers).json()) == 2
    assert [s["name"] for s in api.get("/api/v1/services").json()] == ["Классический массаж"]
    r = api.post("/api/v1/admin/services", headers=admin_headers, json={"name": "", "duration_minutes": 0, "price_minor": -1})
    assert r.status_code == 422


def test_no_services_message(api, client_headers, admin_headers, service_id):
    api.patch(f"/api/v1/admin/services/{service_id}", json={"is_active": False}, headers=admin_headers)
    assert api.get("/api/v1/services").json() == []


def test_settings_change_applies_without_code(api, client_headers, admin_headers, service_id):
    s = api.get("/api/v1/admin/settings", headers=admin_headers).json()
    assert (s["slot_step_minutes"], s["buffer_minutes"], s["booking_horizon_days"], s["cancel_min_hours"],
            s["default_duration_minutes"], s["reminder_hours"]) == (30, 10, 14, 6, 60, [24, 2])
    r = api.patch("/api/v1/admin/settings", headers=admin_headers,
                  json={"slot_step_minutes": 60, "booking_horizon_days": 7, "address": "ул. Ленина, 1"})
    assert r.status_code == 200
    slots = api.get("/api/v1/availability/slots", params={"service_id": service_id, "date": "2026-11-03"},
                    headers=client_headers).json()
    assert [x["local_time"] for x in slots][:3] == ["10:00", "11:00", "12:00"]
    dates = api.get("/api/v1/availability/dates", params={"service_id": service_id}, headers=client_headers).json()
    assert len(dates) == 7
    assert api.get("/api/v1/info").json()["address"] == "ул. Ленина, 1"
    assert api.patch("/api/v1/admin/settings", json={"timezone": "Mars/Base"}, headers=admin_headers).status_code == 422
    audit = api.get("/api/v1/admin/audit", headers=admin_headers).json()
    assert audit["items"][0]["action"] == "settings.update"


def test_admin_slots_for_reschedule(api, client_headers, admin_headers, service_id):
    a = book(api, client_headers, service_id, msk(3, 10)).json()
    r = api.get("/api/v1/admin/availability/slots", params={"date": "2026-11-03", "appointment_id": a["id"]},
                headers=admin_headers)
    assert r.status_code == 200 and r.json()[0]["local_time"] == "10:00"
    r = api.get("/api/v1/admin/availability/slots", params={"date": "2026-11-03", "service_id": service_id},
                headers=admin_headers)
    assert r.json()[0]["local_time"] == "11:30"
    assert api.get("/api/v1/admin/availability/slots", params={"date": "2026-11-03", "service_id": service_id},
                   headers=client_headers).status_code == 403
