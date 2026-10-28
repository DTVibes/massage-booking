import os
import time

from app.cli import set_admin
from app.security import build_init_data, compute_init_data_hash
from tests.conftest import login

TOKEN = os.environ["BOT_TOKEN"]


def test_valid_init_data_creates_user(api):
    h = login(api, 2001, "Мария", username="maria")
    me = api.get("/api/v1/me", headers=h).json()
    assert me["telegram_id"] == 2001 and me["name"] == "Мария" and me["role"] == "client"
    assert me["phone"] is None


def test_repeated_login_same_user(api):
    login(api, 2001)
    h = login(api, 2001)
    assert api.get("/api/v1/me", headers=h).json()["telegram_id"] == 2001


def test_bad_signature_rejected(api):
    init_data = build_init_data({"id": 1, "first_name": "X"}, "999:WRONG-TOKEN")
    r = api.post("/api/v1/auth/telegram", json={"init_data": init_data})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_tampered_user_rejected(api):
    init_data = build_init_data({"id": 1, "first_name": "X"}, TOKEN)
    tampered = init_data.replace("%22id%22%3A1", "%22id%22%3A2")
    assert tampered != init_data
    assert api.post("/api/v1/auth/telegram", json={"init_data": tampered}).status_code == 401


def test_expired_auth_date_rejected(api):
    init_data = build_init_data({"id": 1, "first_name": "X"}, TOKEN, auth_date=int(time.time()) - 2 * 24 * 3600)
    r = api.post("/api/v1/auth/telegram", json={"init_data": init_data})
    assert r.status_code == 401 and r.json()["error"]["code"] == "init_data_expired"


def test_signature_field_is_part_of_check_string():
    fields = {"auth_date": "1", "user": "{}", "signature": "abc", "hash": "x"}
    assert compute_init_data_hash(fields, TOKEN) != compute_init_data_hash({**fields, "signature": "abd"}, TOKEN)


def test_requests_without_session_are_401(api, service_id):
    assert api.get("/api/v1/me").status_code == 401
    assert api.get("/api/v1/me", headers={"Authorization": "Bearer garbage.token"}).status_code == 401
    r = api.post("/api/v1/appointments", json={"service_id": service_id, "starts_at": "2026-11-02T10:00:00+03:00"})
    assert r.status_code == 401
    assert api.get("/api/v1/appointments/my").status_code == 401


def test_frontend_telegram_id_is_not_trusted(api):
    # Сессия привязана к пользователю из подписанного initData; передать чужой ID нельзя.
    h = login(api, 2001)
    r = api.patch("/api/v1/me/profile", json={"telegram_id": 999, "role": "admin", "phone": "+79161234567"}, headers=h)
    assert r.status_code == 200
    me = api.get("/api/v1/me", headers=h).json()
    assert me["telegram_id"] == 2001 and me["role"] == "client"


def test_client_cannot_self_promote_via_init_data(api):
    h = login(api, 2001, role="admin", is_admin=True)
    assert api.get("/api/v1/me", headers=h).json()["role"] == "client"
    assert api.get("/api/v1/admin/settings", headers=h).status_code == 403


def test_admin_endpoints_forbidden_for_client(api, client_headers):
    for path in ("/api/v1/admin/settings", "/api/v1/admin/clients", "/api/v1/admin/schedule", "/api/v1/admin/services",
                 "/api/v1/admin/appointments?date_from=2026-11-02&date_to=2026-11-02"):
        r = api.get(path, headers=client_headers)
        assert r.status_code == 403, path
        assert r.json()["error"]["code"] == "forbidden"


def test_admin_from_env(api, admin_headers):
    assert api.get("/api/v1/me", headers=admin_headers).json()["role"] == "admin"
    assert api.get("/api/v1/admin/settings", headers=admin_headers).status_code == 200


def test_admin_via_cli_and_role_checked_each_request(api, db):
    h = login(api, 3001)
    assert api.get("/api/v1/admin/settings", headers=h).status_code == 403
    set_admin(db, 3001, None, True)
    assert api.get("/api/v1/admin/settings", headers=h).status_code == 200
    set_admin(db, 3001, None, False)
    assert api.get("/api/v1/admin/settings", headers=h).status_code == 403
