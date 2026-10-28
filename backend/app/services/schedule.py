"""Управление рабочим графиком и поиск конфликтов графика с существующими записями.

Изменение графика никогда не удаляет и не отменяет записи автоматически: если
активные записи выпадают из нового графика, администратор получает список конфликтов
и решает сам — подтвердить изменение (force) и перенести/отменить записи вручную.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentStatus, AppSettings, User
from app.services.availability import ScheduleContext


def find_schedule_conflicts(db: Session, settings: AppSettings, now: datetime) -> list[dict]:
    rows = db.execute(
        select(Appointment, User)
        .join(User, User.id == Appointment.client_id)
        .where(Appointment.status == AppointmentStatus.booked, Appointment.ends_at > now)
        .order_by(Appointment.starts_at)
    ).all()
    if not rows:
        return []
    tz = ZoneInfo(settings.timezone)
    first = rows[0][0].starts_at.astimezone(tz).date()
    last = rows[-1][0].starts_at.astimezone(tz).date()
    ctx = ScheduleContext(db, settings, first, last + timedelta(days=1))
    conflicts = []
    for appt, client in rows:
        d = appt.starts_at.astimezone(tz).date()
        inside = any(a <= appt.starts_at and appt.ends_at <= b for a, b in ctx.working_intervals(d))
        if not inside:
            conflicts.append({
                "appointment_id": str(appt.id),
                "starts_at": appt.starts_at.isoformat(),
                "ends_at": appt.ends_at.isoformat(),
                "client_name": client.name,
                "client_phone": client.phone,
                "service_name": appt.service_name_snapshot,
            })
    return conflicts
