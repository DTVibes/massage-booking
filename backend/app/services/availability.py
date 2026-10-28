"""Расчёт доступных слотов (ТЗ, раздел 8.2).

Все вычисления выполняются в UTC с привязкой к календарным датам в часовом поясе массажиста.
Интервал блокировки записи: [starts_at, starts_at + длительность + буфер).
Окончание самой услуги должно укладываться в рабочий интервал; буфер может выходить
за его границу (например, последний сеанс 19:00–20:00 при окончании работы в 20:00).
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    AppointmentStatus,
    AppSettings,
    ExceptionType,
    ScheduleException,
    Service,
    WorkingHours,
)

Interval = tuple[datetime, datetime]


@dataclass
class Slot:
    starts_at: datetime
    ends_at: datetime


def merge(intervals: list[Interval]) -> list[Interval]:
    out: list[Interval] = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def subtract(intervals: list[Interval], holes: list[Interval]) -> list[Interval]:
    result = intervals
    for ha, hb in merge(holes):
        nxt: list[Interval] = []
        for a, b in result:
            if hb <= a or ha >= b:
                nxt.append((a, b))
                continue
            if a < ha:
                nxt.append((a, ha))
            if hb < b:
                nxt.append((hb, b))
        result = nxt
    return result


def overlaps(a: Interval, b: Interval) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def local_today(settings: AppSettings, now: datetime) -> date:
    return now.astimezone(ZoneInfo(settings.timezone)).date()


def horizon_dates(settings: AppSettings, now: datetime) -> list[date]:
    """Горизонт: сегодня + (N-1) дней в часовом поясе массажиста, итого N календарных дней."""
    today = local_today(settings, now)
    return [today + timedelta(days=i) for i in range(settings.booking_horizon_days)]


def service_buffer(settings: AppSettings, service: Service) -> int:
    return service.buffer_minutes if service.buffer_minutes is not None else settings.buffer_minutes


class ScheduleContext:
    """Загружает рабочие часы, исключения и активные записи на диапазон дат одним набором запросов."""

    def __init__(self, db: Session, settings: AppSettings, first: date, last: date,
                 exclude_appointment_id: uuid.UUID | None = None):
        self.settings = settings
        self.tz = ZoneInfo(settings.timezone)
        self.range_start = self.day_start(first)
        self.range_end = self.day_start(last + timedelta(days=1))

        self.hours: dict[int, list[WorkingHours]] = {}
        for row in db.scalars(select(WorkingHours)):
            self.hours.setdefault(row.weekday, []).append(row)

        self.exceptions = list(
            db.scalars(
                select(ScheduleException).where(
                    ScheduleException.starts_at < self.range_end,
                    ScheduleException.ends_at > self.range_start,
                )
            )
        )
        q = select(Appointment.starts_at, Appointment.blocked_until).where(
            Appointment.status == AppointmentStatus.booked,
            Appointment.starts_at < self.range_end + timedelta(days=1),
            Appointment.blocked_until > self.range_start - timedelta(days=1),
        )
        if exclude_appointment_id is not None:
            q = q.where(Appointment.id != exclude_appointment_id)
        self.busy: list[Interval] = [(s, e) for s, e in db.execute(q)]

    def day_start(self, d: date) -> datetime:
        return datetime.combine(d, time(0), tzinfo=self.tz)

    def working_intervals(self, d: date) -> list[Interval]:
        start, end = self.day_start(d), self.day_start(d + timedelta(days=1))
        rows = self.hours.get(d.weekday(), [])
        base: list[Interval] = []
        if rows and all(r.is_working_day for r in rows):
            base = [
                (datetime.combine(d, r.start_time, tzinfo=self.tz), datetime.combine(d, r.end_time, tzinfo=self.tz))
                for r in rows
            ]

        def clipped(kind: ExceptionType) -> list[Interval]:
            return [
                (max(e.starts_at, start), min(e.ends_at, end))
                for e in self.exceptions
                if e.exception_type == kind and e.starts_at < end and e.ends_at > start
            ]

        intervals = merge(base + clipped(ExceptionType.open))
        intervals = subtract(intervals, clipped(ExceptionType.closed) + clipped(ExceptionType.break_))
        return intervals

    def candidates(self, d: date, duration: int, buffer: int) -> list[Slot]:
        """Шаги 4–7: кандидаты с шагом slot_step внутри рабочих интервалов (без учёта занятости)."""
        step = timedelta(minutes=self.settings.slot_step_minutes)
        dur = timedelta(minutes=duration)
        out: list[Slot] = []
        for a, b in self.working_intervals(d):
            t = a
            while t + dur <= b:
                out.append(Slot(t, t + dur))
                t += step
        return out

    def is_busy(self, starts_at: datetime, duration: int, buffer: int) -> bool:
        blocked = (starts_at, starts_at + timedelta(minutes=duration + buffer))
        return any(overlaps(blocked, b) for b in self.busy)

    def free_slots(self, d: date, duration: int, buffer: int, earliest: datetime) -> list[Slot]:
        return [
            s
            for s in self.candidates(d, duration, buffer)
            if s.starts_at >= earliest and not self.is_busy(s.starts_at, duration, buffer)
        ]


def earliest_start(settings: AppSettings, now: datetime) -> datetime:
    return now + timedelta(minutes=max(settings.min_lead_minutes, 0))


def available_slots(db: Session, settings: AppSettings, service: Service, d: date, now: datetime,
                    exclude_appointment_id: uuid.UUID | None = None) -> list[Slot]:
    if d not in horizon_dates(settings, now):
        return []
    ctx = ScheduleContext(db, settings, d, d, exclude_appointment_id)
    return ctx.free_slots(d, service.duration_minutes, service_buffer(settings, service), earliest_start(settings, now))


def available_dates(db: Session, settings: AppSettings, service: Service, now: datetime) -> list[dict]:
    dates = horizon_dates(settings, now)
    ctx = ScheduleContext(db, settings, dates[0], dates[-1])
    buffer = service_buffer(settings, service)
    earliest = earliest_start(settings, now)
    result = []
    for d in dates:
        if not ctx.working_intervals(d):
            status, count = "closed", 0
        else:
            count = len(ctx.free_slots(d, service.duration_minutes, buffer, earliest))
            status = "available" if count else "full"
        result.append({"date": d, "status": status, "free_slots": count})
    return result
