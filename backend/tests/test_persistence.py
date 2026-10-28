from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import engine
from app.models import Appointment
from tests.conftest import book, msk


def test_data_survives_restart(api, client_headers, service_id):
    a = book(api, client_headers, service_id, msk(3, 10)).json()
    engine.dispose()  # закрываем все соединения, как при перезапуске процесса
    fresh = create_engine(get_settings().database_url)
    with Session(fresh) as s:
        appt = s.scalar(select(Appointment).where(Appointment.id == a["id"]))
        assert appt is not None and appt.status.value == "booked"
    fresh.dispose()
    assert api.get("/api/v1/appointments/my", headers=client_headers).json()["upcoming"][0]["id"] == a["id"]
