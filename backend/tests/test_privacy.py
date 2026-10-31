import uuid

from sqlalchemy import select

from app.models import (
    Appointment,
    AppointmentStatus,
    NotificationJob,
    NotificationStatus,
    User,
)
from tests.conftest import book, login, msk


def test_first_booking_requires_consent(api, client_headers, service_id):
    r = book(api, client_headers, service_id, msk(3, 12), accept_privacy=False)
    assert r.status_code == 422 and r.json()["error"]["code"] == "privacy_consent_required"
    assert api.get("/api/v1/me", headers=client_headers).json()["privacy_accepted_at"] is None

    assert book(api, client_headers, service_id, msk(3, 12)).status_code == 201
    assert api.get("/api/v1/me", headers=client_headers).json()["privacy_accepted_at"] is not None
    # Повторно соглашаться не нужно.
    assert book(api, client_headers, service_id, msk(4, 12), accept_privacy=False).status_code == 201


def test_operator_details_in_public_info(api, admin_headers):
    body = {"operator_name": "Иванов Иван Иванович", "operator_inn": "123456789012", "privacy_email": "a@b.ru"}
    assert api.patch("/api/v1/admin/settings", json=body, headers=admin_headers).status_code == 200
    info = api.get("/api/v1/info").json()
    assert info["operator_name"] == "Иванов Иван Иванович" and info["operator_inn"] == "123456789012"
    assert api.patch("/api/v1/admin/settings", json={"operator_inn": "12ab"}, headers=admin_headers).status_code == 422


def test_client_deletes_own_data(api, client_headers, service_id, db):
    future = book(api, client_headers, service_id, msk(4, 12)).json()
    me = api.get("/api/v1/me", headers=client_headers).json()

    assert api.delete("/api/v1/me", headers=client_headers).status_code == 204

    user = db.get(User, uuid.UUID(me["id"]))
    assert user.phone is None and user.telegram_id is None and user.anonymized_at is not None
    assert user.name == "Клиент удалён"
    appt = db.get(Appointment, uuid.UUID(future["id"]))
    assert appt.status == AppointmentStatus.cancelled_by_client
    pending = db.scalars(select(NotificationJob).where(NotificationJob.recipient_telegram_id == 1001,
                                                       NotificationJob.status == NotificationStatus.pending)).all()
    assert pending == []
    # Старая сессия больше не действует; новый вход создаёт чистый профиль.
    assert api.get("/api/v1/me", headers=client_headers).status_code == 401
    fresh = api.get("/api/v1/me", headers=login(api, 1001, "Иван")).json()
    assert fresh["id"] != me["id"] and fresh["phone"] is None and fresh["privacy_accepted_at"] is None


def test_admin_anonymizes_client(api, client_headers, admin_headers, service_id):
    book(api, client_headers, service_id, msk(4, 12))
    cid = api.get("/api/v1/me", headers=client_headers).json()["id"]
    r = api.post(f"/api/v1/admin/clients/{cid}/anonymize", headers=admin_headers)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["phone"] is None and d["anonymized_at"] is not None and d["admin_notes"] is None
    assert d["appointments"][0]["status"] == "cancelled_by_admin"


def test_admin_cannot_anonymize_admin(api, admin_headers):
    aid = api.get("/api/v1/me", headers=admin_headers).json()["id"]
    r = api.post(f"/api/v1/admin/clients/{aid}/anonymize", headers=admin_headers)
    assert r.status_code == 422
