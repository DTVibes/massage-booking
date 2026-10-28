"""Служебные команды.

    python -m app.cli init                         # настройки, график и услуга по умолчанию (идемпотентно)
    python -m app.cli create-admin --telegram-id 123456789 [--name "Анна"]
    python -m app.cli revoke-admin --telegram-id 123456789
"""

import argparse
import sys
from datetime import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import AppSettings, Service, User, UserRole, WorkingHours

DEFAULT_SERVICE = {
    "name": "Классический массаж",
    "description": "Расслабляющий массаж всего тела.",
    "duration_minutes": 60,
    "price_minor": 0,  # стоимость задаёт администратор в разделе «Услуги»
}


def init_defaults(db: Session, timezone: str | None = None) -> list[str]:
    done = []
    settings = db.get(AppSettings, 1)
    if settings is None:
        settings = AppSettings(
            id=1, timezone=timezone or get_settings().timezone, currency="RUB",
            default_duration_minutes=60, slot_step_minutes=30, buffer_minutes=10,
            booking_horizon_days=14, min_lead_minutes=60, cancel_min_hours=6,
            allow_client_reschedule=True, max_active_bookings_per_client=3, reminder_hours=[24, 2],
            notify_admin_new=True, notify_admin_cancel=True, notify_admin_reschedule=True,
            studio_name="Массаж", master_name="", welcome_text="", address="",
            contact_phone="", contact_telegram="",
        )
        db.add(settings)
        done.append("settings")
    if db.scalar(select(WorkingHours.id).limit(1)) is None:
        for wd in range(7):
            if wd < 5:  # пн–пт 10:00–19:00
                db.add(WorkingHours(weekday=wd, start_time=time(10), end_time=time(19), is_working_day=True))
            else:
                db.add(WorkingHours(weekday=wd, is_working_day=False))
        done.append("working_hours")
    if db.scalar(select(Service.id).limit(1)) is None:
        db.add(Service(**DEFAULT_SERVICE, currency=settings.currency, is_active=True))
        done.append("service")
    db.commit()
    return done


def set_admin(db: Session, telegram_id: int, name: str | None, admin: bool) -> User:
    user = db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        user = User(telegram_id=telegram_id, name=name or "Администратор")
        db.add(user)
    elif name:
        user.name = name
    user.role = UserRole.admin if admin else UserRole.client
    db.commit()
    return user


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="создать настройки и данные по умолчанию")
    for cmd in ("create-admin", "revoke-admin"):
        p = sub.add_parser(cmd)
        p.add_argument("--telegram-id", type=int, required=True)
        p.add_argument("--name")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        if args.cmd == "init":
            done = init_defaults(db)
            print("Инициализировано: " + (", ".join(done) if done else "ничего (данные уже есть)"))
        elif args.cmd == "create-admin":
            user = set_admin(db, args.telegram_id, args.name, True)
            print(f"Администратор: {user.name} (telegram_id={user.telegram_id})")
        elif args.cmd == "revoke-admin":
            if args.telegram_id in get_settings().admin_telegram_ids:
                print("Внимание: этот ID указан в ADMIN_TELEGRAM_IDS — уберите его оттуда, иначе роль вернётся при входе.")
            set_admin(db, args.telegram_id, None, False)
            print("Роль администратора снята")
    return 0


if __name__ == "__main__":
    sys.exit(main())
