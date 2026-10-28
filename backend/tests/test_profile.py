from tests.conftest import book, login, msk


def test_phone_required_before_booking(api, service_id):
    h = login(api, 1500)
    # без телефона можно смотреть услуги и слоты
    assert api.get("/api/v1/services").status_code == 200
    assert api.get("/api/v1/availability/slots", params={"service_id": service_id, "date": "2026-11-02"},
                   headers=h).status_code == 200
    r = book(api, h, service_id, msk(2, 10))
    assert r.status_code == 422 and r.json()["error"]["code"] == "phone_required"
    api.patch("/api/v1/me/profile", json={"phone": "8 (916) 555-44-33"}, headers=h)
    assert book(api, h, service_id, msk(2, 10)).status_code == 201


def test_phone_normalized_and_validated(api):
    h = login(api, 1500)
    r = api.patch("/api/v1/me/profile", json={"phone": "8 916 555 44 33"}, headers=h)
    assert r.json()["phone"] == "+79165554433"
    r = api.patch("/api/v1/me/profile", json={"phone": "12345"}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_phone"
    assert api.get("/api/v1/me", headers=h).json()["phone"] == "+79165554433"
    r = api.patch("/api/v1/me/profile", json={"phone": "+7 999 000-11-22"}, headers=h)
    assert r.json()["phone"] == "+79990001122"


def test_phone_visible_to_admin_not_to_other_clients(api, client_headers, admin_headers, service_id):
    book(api, client_headers, service_id, msk(2, 10))
    other = login(api, 1600, "Пётр")
    api.patch("/api/v1/me/profile", json={"phone": "+79160000000"}, headers=other)
    mine = api.get("/api/v1/appointments/my", headers=other).json()
    assert mine["upcoming"] == []
    assert "+79161234567" not in api.get("/api/v1/availability/slots",
                                         params={"service_id": service_id, "date": "2026-11-02"}, headers=other).text
    rows = api.get("/api/v1/admin/appointments", params={"date_from": "2026-11-02", "date_to": "2026-11-02"},
                   headers=admin_headers).json()
    assert rows[0]["client"]["phone"] == "+79161234567"


def test_validation_error_format(api, client_headers):
    r = api.post("/api/v1/appointments", json={"service_id": "not-a-uuid"}, headers=client_headers)
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "validation_error" and isinstance(body["details"], list)
