import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.errors import Conflict
from app.main import app
from app.models import Appointment, AppointmentStatus, Service, User
from app.services import booking
from tests.conftest import NOW, book, login, msk


def count_active(db):
    return db.scalar(select(func.count()).select_from(Appointment).where(Appointment.status == AppointmentStatus.booked))


def test_create_appointment_snapshot(api, client_headers, service_id, admin_headers):
    api.patch(f"/api/v1/admin/services/{service_id}", json={"price_minor": 250000}, headers=admin_headers)
    r = api.post("/api/v1/appointments", headers=client_headers, json={
        "service_id": service_id, "starts_at": msk(3, 10).isoformat(),
        # клиент пытается подменить цену, длительность и статус — игнорируется
        "price_minor": 1, "duration_minutes": 5, "status": "completed"})
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["status"] == "booked" and a["price_minor"] == 250000 and a["duration_minutes"] == 60
    assert a["service_name"] == "Классический массаж"
    assert a["can_cancel"] and a["can_reschedule"]

    # изменение услуги не переписывает созданные записи
    api.patch(f"/api/v1/admin/services/{service_id}", headers=admin_headers,
              json={"name": "Новый массаж", "price_minor": 500000, "duration_minutes": 90})
    mine = api.get("/api/v1/appointments/my", headers=client_headers).json()["upcoming"][0]
    assert mine["service_name"] == "Классический массаж" and mine["price_minor"] == 250000
    assert mine["duration_minutes"] == 60


def test_double_booking_rejected(api, client_headers, service_id):
    assert book(api, client_headers, service_id, msk(2, 10)).status_code == 201
    other = login(api, 1700, "Ольга")
    api.patch("/api/v1/me/profile", json={"phone": "+79160000001"}, headers=other)
    r = book(api, other, service_id, msk(2, 10))
    assert r.status_code == 409 and r.json()["error"]["code"] == "slot_taken"
    r = book(api, other, service_id, msk(2, 10, 30))
    assert r.status_code == 409
    assert book(api, other, service_id, msk(2, 11, 30)).status_code == 201


def test_idempotent_retry(api, client_headers, service_id, db):
    key = str(uuid.uuid4())
    r1 = book(api, client_headers, service_id, msk(2, 10), key=key)
    r2 = book(api, client_headers, service_id, msk(2, 10), key=key)
    assert r1.status_code == 201 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]
    assert count_active(db) == 1


def test_inactive_service_cannot_be_booked(api, client_headers, admin_headers, service_id):
    api.patch(f"/api/v1/admin/services/{service_id}", json={"is_active": False}, headers=admin_headers)
    assert api.get("/api/v1/services").json() == []
    r = book(api, client_headers, service_id, msk(2, 10))
    assert r.status_code == 404


def test_max_active_bookings(api, client_headers, service_id):
    for d in (2, 3, 4):
        assert book(api, client_headers, service_id, msk(d, 10)).status_code == 201
    r = book(api, client_headers, service_id, msk(5, 10))
    assert r.status_code == 409 and r.json()["error"]["code"] == "too_many_active_bookings"


def _make_clients(n):
    ids = []
    with SessionLocal() as db:
        for i in range(n):
            u = User(telegram_id=50_000 + i, name=f"Клиент {i}", phone=f"+7916000{i:04d}")
            db.add(u)
            db.flush()
            ids.append(u.id)
        db.commit()
    return ids


def test_concurrent_booking_same_slot_service_level():
    n = 12
    client_ids = _make_clients(n)
    with SessionLocal() as db:
        service_id = db.scalar(select(Service.id))
    barrier = threading.Barrier(n)
    starts = [msk(2, 10), msk(2, 10, 30)] * (n // 2)  # одинаковые и пересекающиеся интервалы

    def attempt(i):
        with SessionLocal() as db:
            client = db.get(User, client_ids[i])
            barrier.wait()
            try:
                booking.create_appointment(db, actor=client, client=client, service_id=service_id,
                                           starts_at=starts[i], now=NOW)
                return "ok"
            except Conflict:
                return "conflict"

    with ThreadPoolExecutor(n) as pool:
        results = list(pool.map(attempt, range(n)))
    assert results.count("ok") == 1, results
    assert results.count("conflict") == n - 1
    with SessionLocal() as db:
        assert count_active(db) == 1


def test_concurrent_booking_via_api():
    n = 8
    with TestClient(app) as c:
        headers = []
        for i in range(n):
            h = login(c, 60_000 + i, f"Клиент {i}")
            c.patch("/api/v1/me/profile", json={"phone": f"+7916100{i:04d}"}, headers=h)
            headers.append(h)
        sid = c.get("/api/v1/services").json()[0]["id"]
    barrier = threading.Barrier(n)

    def attempt(i):
        with TestClient(app) as c:
            barrier.wait()
            return book(c, headers[i], sid, msk(3, 15)).status_code

    with ThreadPoolExecutor(n) as pool:
        codes = list(pool.map(attempt, range(n)))
    assert sorted(codes) == [201] + [409] * (n - 1), codes


def test_database_constraint_blocks_overlap_directly(db):
    """Даже в обход API PostgreSQL не позволит сохранить пересекающиеся активные записи."""
    client = User(telegram_id=7, name="X", phone="+79160000007")
    db.add(client)
    db.flush()

    def appt(start, status=AppointmentStatus.booked):
        return Appointment(client_id=client.id, service_name_snapshot="M", duration_minutes=60,
                           price_minor_snapshot=0, currency_snapshot="RUB", starts_at=start,
                           ends_at=start + timedelta(minutes=60), buffer_minutes=10,
                           blocked_until=start + timedelta(minutes=70), status=status)

    db.add(appt(msk(2, 10)))
    db.commit()
    db.add(appt(msk(2, 11)))  # попадает в буфер 11:00–11:10
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(appt(msk(2, 11), status=AppointmentStatus.cancelled_by_client))  # отменённые не блокируют
    db.add(appt(msk(2, 11, 10)))
    db.commit()
    assert db.execute(text("select count(*) from appointments where status='booked'")).scalar() == 2
