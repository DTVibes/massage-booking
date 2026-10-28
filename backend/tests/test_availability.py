from datetime import timedelta

from tests.conftest import book, msk


def slots(api, headers, service_id, day):
    r = api.get("/api/v1/availability/slots", params={"service_id": service_id, "date": day}, headers=headers)
    assert r.status_code == 200, r.text
    return [s["local_time"] for s in r.json()]


def test_default_slots_step_30(api, client_headers, service_id):
    times = slots(api, client_headers, service_id, "2026-11-02")
    assert times[:3] == ["10:00", "10:30", "11:00"]
    assert times[-1] == "18:00"  # 18:00–19:00 последний сеанс
    assert len(times) == 17


def test_buffer_blocks_next_slot(api, client_headers, service_id):
    assert book(api, client_headers, service_id, msk(2, 10)).status_code == 201
    times = slots(api, client_headers, service_id, "2026-11-02")
    # 10:00–11:00 + буфер 10 мин = блокировка до 11:10: 10:30 и 11:00 недоступны, 11:30 доступно
    assert "10:00" not in times and "10:30" not in times and "11:00" not in times
    assert times[0] == "11:30"


def test_buffer_before_existing_booking(api, client_headers, service_id):
    assert book(api, client_headers, service_id, msk(2, 11, 30)).status_code == 201
    times = slots(api, client_headers, service_id, "2026-11-02")
    # 10:30 → блокировка до 11:40 пересекается с 11:30; 10:00 → до 11:10 не пересекается
    assert "10:00" in times and "10:30" not in times and "11:00" not in times and "12:00" not in times
    assert "12:30" not in times and "12:41" not in times and "13:00" in times


def test_dates_horizon_14_days(api, client_headers, service_id):
    r = api.get("/api/v1/availability/dates", params={"service_id": service_id}, headers=client_headers)
    dates = r.json()
    assert len(dates) == 14
    assert dates[0]["date"] == "2026-11-02" and dates[-1]["date"] == "2026-11-15"
    by_date = {d["date"]: d["status"] for d in dates}
    assert by_date["2026-11-07"] == "closed" and by_date["2026-11-08"] == "closed"  # выходные
    assert by_date["2026-11-03"] == "available"
    assert slots(api, client_headers, service_id, "2026-11-16") == []
    r = book(api, client_headers, service_id, msk(16, 10))
    assert r.status_code == 422 and r.json()["error"]["code"] == "outside_horizon"
    assert book(api, client_headers, service_id, msk(13, 10)).status_code == 201


def test_horizon_uses_master_timezone(api, client_headers, service_id, clock):
    # 22:30 UTC 2 ноября = 01:30 3 ноября по Москве → горизонт начинается с 3 ноября
    clock.now = msk(3, 1, 30)
    dates = api.get("/api/v1/availability/dates", params={"service_id": service_id}, headers=client_headers).json()
    assert dates[0]["date"] == "2026-11-03" and dates[-1]["date"] == "2026-11-16"


def test_full_day_status(api, client_headers, admin_headers, service_id):
    # Оставляем один интервал 10:00–11:00 в среду и занимаем его
    days = [{"weekday": wd, "is_working_day": wd < 5, "intervals": [{"start": "10:00", "end": "19:00"}] if wd < 5 else []}
            for wd in range(7)]
    days[2]["intervals"] = [{"start": "10:00", "end": "11:00"}]
    assert api.put("/api/v1/admin/schedule", json={"days": days}, headers=admin_headers).status_code == 200
    assert book(api, client_headers, service_id, msk(4, 10)).status_code == 201
    dates = {d["date"]: d["status"] for d in
             api.get("/api/v1/availability/dates", params={"service_id": service_id}, headers=client_headers).json()}
    assert dates["2026-11-04"] == "full"


def test_past_and_min_lead_time(api, client_headers, service_id, clock):
    clock.now = msk(2, 12, 10)  # минимальный срок до визита 60 минут → не раньше 13:10
    times = slots(api, client_headers, service_id, "2026-11-02")
    assert times[0] == "13:30"
    r = book(api, client_headers, service_id, msk(2, 11))
    assert r.status_code == 422 and r.json()["error"]["code"] == "past_time"
    r = book(api, client_headers, service_id, msk(2, 13))
    assert r.status_code == 422 and r.json()["error"]["code"] == "too_soon"
    r = book(api, client_headers, service_id, msk(1, 10))
    assert r.status_code == 422


def test_outside_schedule_rejected(api, client_headers, service_id):
    for t in (msk(2, 9), msk(2, 10, 15), msk(2, 18, 30), msk(7, 12)):
        r = book(api, client_headers, service_id, t)
        assert r.status_code == 422, t
        assert r.json()["error"]["code"] in ("outside_schedule",)


def test_cancelled_does_not_block(api, client_headers, service_id):
    appt = book(api, client_headers, service_id, msk(3, 10)).json()
    assert "10:00" not in slots(api, client_headers, service_id, "2026-11-03")
    api.post(f"/api/v1/appointments/{appt['id']}/cancel", headers=client_headers)
    assert "10:00" in slots(api, client_headers, service_id, "2026-11-03")


def test_break_exception(api, client_headers, admin_headers, service_id):
    r = api.post("/api/v1/admin/schedule/exceptions", headers=admin_headers, json={
        "starts_at": msk(3, 13).isoformat(), "ends_at": msk(3, 14).isoformat(), "exception_type": "break"})
    assert r.status_code == 201, r.text
    times = slots(api, client_headers, service_id, "2026-11-03")
    assert "12:00" in times and "12:30" not in times and "13:00" not in times and "13:30" not in times
    assert "14:00" in times


def test_closed_and_open_exceptions(api, client_headers, admin_headers, service_id):
    api.post("/api/v1/admin/schedule/exceptions", headers=admin_headers, json={
        "starts_at": msk(5, 0).isoformat(), "ends_at": msk(6, 0).isoformat(), "exception_type": "closed",
        "reason": "Выходной"})
    api.post("/api/v1/admin/schedule/exceptions", headers=admin_headers, json={
        "starts_at": msk(7, 10).isoformat(), "ends_at": msk(7, 14).isoformat(), "exception_type": "open"})
    dates = {d["date"]: d["status"] for d in
             api.get("/api/v1/availability/dates", params={"service_id": service_id}, headers=client_headers).json()}
    assert dates["2026-11-05"] == "closed"
    assert dates["2026-11-07"] == "available"
    assert slots(api, client_headers, service_id, "2026-11-07") == ["10:00", "10:30", "11:00", "11:30", "12:00", "12:30", "13:00"]
    assert book(api, client_headers, service_id, msk(7, 13)).status_code == 201
    assert book(api, client_headers, service_id, msk(5, 12)).status_code == 422


def test_multiple_intervals_per_day(api, client_headers, admin_headers, service_id):
    days = [{"weekday": 1, "is_working_day": True,
             "intervals": [{"start": "10:00", "end": "12:00"}, {"start": "15:00", "end": "17:00"}]}]
    assert api.put("/api/v1/admin/schedule", json={"days": days}, headers=admin_headers).status_code == 200
    assert slots(api, client_headers, service_id, "2026-11-03") == ["10:00", "10:30", "11:00", "15:00", "15:30", "16:00"]


def test_service_duration_respected(api, client_headers, admin_headers):
    r = api.post("/api/v1/admin/services", headers=admin_headers,
                 json={"name": "Массаж спины", "duration_minutes": 90, "price_minor": 300000})
    sid = r.json()["id"]
    times = slots(api, client_headers, sid, "2026-11-02")
    assert times[-1] == "17:30" and len(times) == 16
    appt = book(api, client_headers, sid, msk(2, 10)).json()
    assert appt["duration_minutes"] == 90
    assert appt["ends_at"].startswith("2026-11-02T08:30")  # 11:30 МСК, буфер не входит во время услуги
    assert (msk(2, 10) + timedelta(minutes=90)).hour == 8
