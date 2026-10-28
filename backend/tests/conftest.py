import os

os.environ.setdefault("DATABASE_URL", os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/massage_test"))
os.environ["BOT_TOKEN"] = "123456:TEST-TOKEN"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ADMIN_TELEGRAM_IDS"] = "999"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["TIMEZONE"] = "Europe/Moscow"

from datetime import UTC, datetime, timedelta  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import timeutil  # noqa: E402
from app.cli import init_defaults  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security import build_init_data  # noqa: E402

# Понедельник, 2 ноября 2026, 07:00 по Москве (04:00 UTC). График по умолчанию: пн–пт 10:00–19:00.
NOW = datetime(2026, 11, 2, 4, 0, tzinfo=UTC)
TABLES = ("notification_jobs", "appointment_history", "admin_audit_log", "appointments", "schedule_exceptions",
          "working_hours", "services", "settings", "users")


def msk(day: int, hour: int, minute: int = 0, month: int = 11) -> datetime:
    """Время по Москве (UTC+3) в ноябре 2026."""
    return datetime(2026, month, day, hour, minute, tzinfo=UTC) - timedelta(hours=3)


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    cfg.attributes["configure_logger"] = False
    cfg.attributes["database_url"] = get_settings().database_url
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


class Clock:
    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def shift(self, **kw) -> None:
        self.now = self.now + timedelta(**kw)


@pytest.fixture(autouse=True)
def clean_db(monkeypatch):
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE " + ", ".join(TABLES) + " RESTART IDENTITY CASCADE"))
    with SessionLocal() as db:
        init_defaults(db)
    yield


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    c = Clock(NOW)
    monkeypatch.setattr(timeutil, "now_utc", c)
    return c


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def api():
    with TestClient(app) as c:
        yield c


def login(api: TestClient, telegram_id: int, name: str = "Иван", **user_extra) -> dict:
    init_data = build_init_data({"id": telegram_id, "first_name": name, "allows_write_to_pm": True, **user_extra},
                                os.environ["BOT_TOKEN"])
    r = api.post("/api/v1/auth/telegram", json={"init_data": init_data})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def client_headers(api):
    h = login(api, 1001, "Иван")
    r = api.patch("/api/v1/me/profile", json={"phone": "+7 916 123-45-67"}, headers=h)
    assert r.status_code == 200, r.text
    return h


@pytest.fixture
def admin_headers(api):
    return login(api, 999, "Анна")


@pytest.fixture
def service_id(api):
    return api.get("/api/v1/services").json()[0]["id"]


def book(api, headers, service_id, starts_at: datetime, key: str | None = None):
    h = dict(headers)
    if key:
        h["Idempotency-Key"] = key
    return api.post("/api/v1/appointments", json={"service_id": service_id, "starts_at": starts_at.isoformat()},
                    headers=h)
