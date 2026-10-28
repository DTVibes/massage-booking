"""Административные endpoints. Каждый запрос проверяет роль администратора на сервере (AdminUser)."""

import uuid
from datetime import date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Response
from sqlalchemy import String, and_, case, cast, delete, func, or_, select
from sqlalchemy.orm import Session

from app import timeutil
from app.deps import DB, AdminUser
from app.errors import Conflict, NotFound, ValidationFailed
from app.models import (
    AdminAuditLog,
    Appointment,
    AppointmentHistory,
    AppointmentStatus,
    ExceptionType,
    ScheduleException,
    Service,
    User,
    UserRole,
    WorkingHours,
)
from app.schemas import (
    AdminAppointmentCreateIn,
    AdminAppointmentDetailOut,
    AdminAppointmentOut,
    AdminAppointmentPatch,
    AdminClientDetailOut,
    AdminClientOut,
    AdminClientPatch,
    AdminServiceOut,
    AdminSettingsOut,
    AdminSettingsPatch,
    AuditOut,
    DaySchedule,
    NewClientIn,
    Page,
    ScheduleExceptionIn,
    ScheduleExceptionOut,
    ScheduleIn,
    ScheduleOut,
    ServiceIn,
    ServicePatch,
    SlotOut,
    TimeInterval,
)
from app.services import booking
from app.services.audit import audit, record_history
from app.services.availability import appointment_snapshot, available_slots, slots_out
from app.services.phone import normalize_phone
from app.services.schedule import find_schedule_conflicts
from app.services.settings_service import get_app_settings

router = APIRouter(prefix="/admin", tags=["admin"])

CANCELLED = (AppointmentStatus.cancelled_by_client, AppointmentStatus.cancelled_by_admin)


# ---------- Записи ----------

def _appt_out(appt: Appointment, client: User) -> AdminAppointmentOut:
    out = AdminAppointmentOut.model_validate({**_appt_dict(appt), "client": client})
    return out


def _appt_dict(appt: Appointment) -> dict:
    return {c.key: getattr(appt, c.key) for c in Appointment.__table__.columns}


@router.get("/appointments", response_model=list[AdminAppointmentOut])
def list_appointments(admin: AdminUser, db: DB, date_from: date, date_to: date,
                      status: Annotated[list[AppointmentStatus] | None, Query()] = None,
                      client_id: uuid.UUID | None = None):
    if date_to < date_from or (date_to - date_from).days > 62:
        raise ValidationFailed("Диапазон дат: не более 62 дней", code="bad_range")
    tz = ZoneInfo(get_app_settings(db).timezone)
    start = datetime.combine(date_from, time(0), tzinfo=tz)
    end = datetime.combine(date_to + timedelta(days=1), time(0), tzinfo=tz)
    q = (select(Appointment, User).join(User, User.id == Appointment.client_id)
         .where(Appointment.starts_at >= start, Appointment.starts_at < end).order_by(Appointment.starts_at))
    if status:
        q = q.where(Appointment.status.in_(status))
    if client_id:
        q = q.where(Appointment.client_id == client_id)
    return [_appt_out(a, u) for a, u in db.execute(q).all()]


def _detail(db: Session, appointment_id: uuid.UUID) -> AdminAppointmentDetailOut:
    row = db.execute(select(Appointment, User).join(User, User.id == Appointment.client_id)
                     .where(Appointment.id == appointment_id)).first()
    if row is None:
        raise NotFound("Запись не найдена")
    appt, client = row
    history = db.scalars(select(AppointmentHistory).where(AppointmentHistory.appointment_id == appt.id)
                         .order_by(AppointmentHistory.id)).all()
    return AdminAppointmentDetailOut.model_validate({**_appt_dict(appt), "client": client, "history": history})


@router.get("/appointments/{appointment_id}", response_model=AdminAppointmentDetailOut)
def get_appointment(appointment_id: uuid.UUID, admin: AdminUser, db: DB):
    return _detail(db, appointment_id)


def _create_offline_client(db: Session, data: NewClientIn) -> User:
    client = User(name=data.name.strip(), phone=normalize_phone(data.phone), role=UserRole.client)
    db.add(client)
    db.flush()
    return client


@router.post("/appointments", response_model=AdminAppointmentDetailOut, status_code=201)
def create_appointment(body: AdminAppointmentCreateIn, admin: AdminUser, db: DB):
    if body.client_id:
        client = db.get(User, body.client_id)
        if client is None:
            raise NotFound("Клиент не найден")
    else:
        client = _create_offline_client(db, body.new_client)
    appt, _ = booking.create_appointment(
        db, actor=admin, client=client, service_id=body.service_id, starts_at=body.starts_at,
        now=timeutil.now_utc(), comment=body.comment, ignore_schedule=body.ignore_schedule, as_admin=True,
    )
    return _detail(db, appt.id)


@router.patch("/appointments/{appointment_id}", response_model=AdminAppointmentDetailOut)
def update_appointment(appointment_id: uuid.UUID, body: AdminAppointmentPatch, admin: AdminUser, db: DB):
    now = timeutil.now_utc()
    if body.starts_at is not None and body.status is not None:
        raise ValidationFailed("Перенос и смену статуса выполняйте отдельными запросами")
    if body.starts_at is not None:
        booking.reschedule_appointment(db, actor=admin, appointment_id=appointment_id, new_starts_at=body.starts_at,
                                       now=now, ignore_schedule=body.ignore_schedule,
                                       notify_client=body.notify_client, as_admin=True)
    if body.status == "cancelled_by_admin":
        booking.cancel_appointment(db, actor=admin, appointment_id=appointment_id, now=now, reason=body.reason,
                                   notify_client=body.notify_client, as_admin=True)
    elif body.status in ("completed", "no_show"):
        booking.set_visit_status(db, actor=admin, appointment_id=appointment_id,
                                 status=AppointmentStatus(body.status), now=now)
    if body.comment is not None:
        appt = booking.get_appointment_for_update(db, appointment_id)
        old = appt.comment
        appt.comment = body.comment or None
        record_history(db, appt, "updated", admin, details={"field": "comment", "old": old, "new": appt.comment})
        db.commit()
    return _detail(db, appointment_id)


@router.get("/availability/slots", response_model=list[SlotOut])
def admin_slots(admin: AdminUser, db: DB, date: date, service_id: uuid.UUID | None = None,
                appointment_id: uuid.UUID | None = None):
    """Свободные слоты по правилам графика (для ручной записи и переноса администратором)."""
    settings = get_app_settings(db)
    if appointment_id is not None:
        appt = db.get(Appointment, appointment_id)
        if appt is None:
            raise NotFound("Запись не найдена")
        service, exclude = appointment_snapshot(appt), appt.id
    elif service_id is not None:
        service, exclude = db.get(Service, service_id), None
        if service is None:
            raise NotFound("Услуга не найдена")
    else:
        raise ValidationFailed("Укажите service_id или appointment_id")
    return slots_out(available_slots(db, settings, service, date, timeutil.now_utc(), exclude), settings)


# ---------- Клиенты ----------

def _client_stats_query():
    a = Appointment
    return (
        select(
            User,
            func.count(a.id).filter(a.status == AppointmentStatus.completed).label("completed_count"),
            func.count(a.id).filter(a.status.in_(CANCELLED)).label("cancelled_count"),
            func.count(a.id).filter(a.status == AppointmentStatus.no_show).label("no_show_count"),
            func.max(case((a.status == AppointmentStatus.completed, a.starts_at))).label("last_visit_at"),
            func.min(case((and_(a.status == AppointmentStatus.booked, a.starts_at > func.now()), a.starts_at)))
            .label("upcoming_at"),
        )
        .outerjoin(a, a.client_id == User.id)
        .group_by(User.id)
    )


def _client_out(row) -> dict:
    user, completed, cancelled, no_show, last_visit, upcoming = row
    return {**{c.key: getattr(user, c.key) for c in User.__table__.columns}, "completed_count": completed,
            "cancelled_count": cancelled, "no_show_count": no_show, "last_visit_at": last_visit,
            "upcoming_at": upcoming}


@router.get("/clients", response_model=Page[AdminClientOut])
def list_clients(admin: AdminUser, db: DB, q: Annotated[str | None, Query(max_length=100)] = None,
                 page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 20):
    base = select(User.id).where(User.role == UserRole.client)
    if q:
        term = f"%{q.strip()}%"
        digits = "".join(ch for ch in q if ch.isdigit())
        conds = [User.name.ilike(term), User.username.ilike(term)]
        if digits:
            conds += [User.phone.like(f"%{digits}%"), cast(User.telegram_id, String).like(f"%{digits}%")]
        base = base.where(or_(*conds))
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.execute(
        _client_stats_query().where(User.id.in_(base)).order_by(User.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {"items": [_client_out(r) for r in rows], "total": total, "page": page, "page_size": page_size}


def _client_detail(db: Session, client_id: uuid.UUID) -> dict:
    row = db.execute(_client_stats_query().where(User.id == client_id)).first()
    if row is None:
        raise NotFound("Клиент не найден")
    user = row[0]
    appts = db.scalars(select(Appointment).where(Appointment.client_id == client_id)
                       .order_by(Appointment.starts_at.desc())).all()
    return {**_client_out(row), "appointments": [_appt_out(a, user) for a in appts]}


@router.post("/clients", response_model=AdminClientDetailOut, status_code=201)
def create_client(body: NewClientIn, admin: AdminUser, db: DB):
    client = _create_offline_client(db, body)
    audit(db, admin, "client.create", "user", client.id, {"name": client.name})
    db.commit()
    return _client_detail(db, client.id)


@router.get("/clients/{client_id}", response_model=AdminClientDetailOut)
def get_client(client_id: uuid.UUID, admin: AdminUser, db: DB):
    return _client_detail(db, client_id)


@router.patch("/clients/{client_id}", response_model=AdminClientDetailOut)
def update_client(client_id: uuid.UUID, body: AdminClientPatch, admin: AdminUser, db: DB):
    client = db.get(User, client_id)
    if client is None:
        raise NotFound("Клиент не найден")
    changes = body.model_dump(exclude_unset=True)
    if "phone" in changes and changes["phone"]:
        changes["phone"] = normalize_phone(changes["phone"])
    if client.id == admin.id and changes.get("is_active") is False:
        raise ValidationFailed("Нельзя заблокировать самого себя")
    for k, v in changes.items():
        setattr(client, k, v)
    audit(db, admin, "client.update", "user", client.id, {"fields": sorted(changes)})
    db.commit()
    return _client_detail(db, client.id)


# ---------- Рабочий график ----------

def _schedule_out(db: Session, conflicts: list[dict] | None = None) -> ScheduleOut:
    settings = get_app_settings(db)
    rows = db.scalars(select(WorkingHours).order_by(WorkingHours.weekday, WorkingHours.start_time)).all()
    days = []
    for wd in range(7):
        day_rows = [r for r in rows if r.weekday == wd]
        working = bool(day_rows) and all(r.is_working_day for r in day_rows)
        days.append(DaySchedule(weekday=wd, is_working_day=working,
                                intervals=[TimeInterval(start=r.start_time, end=r.end_time) for r in day_rows] if working else []))
    now = timeutil.now_utc()
    exceptions = db.scalars(select(ScheduleException).where(ScheduleException.ends_at > now - timedelta(days=1))
                            .order_by(ScheduleException.starts_at)).all()
    return ScheduleOut(days=days, exceptions=[ScheduleExceptionOut.model_validate(e) for e in exceptions],
                       timezone=settings.timezone, conflicts=conflicts or [])


def _apply_or_reject(db: Session, force: bool) -> list[dict]:
    """Проверяет конфликты после изменения графика в текущей транзакции."""
    db.flush()
    conflicts = find_schedule_conflicts(db, get_app_settings(db), timeutil.now_utc())
    if conflicts and not force:
        db.rollback()
        raise Conflict(
            "Изменение затрагивает существующие записи. Перенесите или отмените их, либо подтвердите изменение.",
            code="schedule_conflicts",
            details=conflicts,
        )
    return conflicts


@router.get("/schedule", response_model=ScheduleOut)
def get_schedule(admin: AdminUser, db: DB):
    return _schedule_out(db)


@router.put("/schedule", response_model=ScheduleOut)
def put_schedule(body: ScheduleIn, admin: AdminUser, db: DB):
    weekdays = [d.weekday for d in body.days]
    db.execute(delete(WorkingHours).where(WorkingHours.weekday.in_(weekdays)))
    for day in body.days:
        if day.is_working_day:
            for iv in day.intervals:
                db.add(WorkingHours(weekday=day.weekday, start_time=iv.start, end_time=iv.end, is_working_day=True))
        else:
            db.add(WorkingHours(weekday=day.weekday, is_working_day=False))
    conflicts = _apply_or_reject(db, body.force)
    audit(db, admin, "schedule.update", "working_hours", None,
          {"days": [d.model_dump(mode="json") for d in body.days], "conflicts": len(conflicts)})
    db.commit()
    return _schedule_out(db, conflicts)


@router.post("/schedule/exceptions", response_model=ScheduleExceptionOut, status_code=201)
def create_exception(body: ScheduleExceptionIn, admin: AdminUser, db: DB):
    exc = ScheduleException(starts_at=body.starts_at, ends_at=body.ends_at,
                            exception_type=body.exception_type, reason=body.reason)
    db.add(exc)
    conflicts = _apply_or_reject(db, body.force) if body.exception_type != ExceptionType.open else []
    audit(db, admin, "schedule.exception.create", "schedule_exception", exc.id,
          {"type": body.exception_type.value, "starts_at": body.starts_at.isoformat(),
           "ends_at": body.ends_at.isoformat(), "conflicts": len(conflicts)})
    db.commit()
    out = ScheduleExceptionOut.model_validate(exc)
    out.conflicts = conflicts
    return out


@router.delete("/schedule/exceptions/{exception_id}", status_code=204)
def delete_exception(exception_id: int, admin: AdminUser, db: DB, force: bool = False):
    exc = db.get(ScheduleException, exception_id)
    if exc is None:
        raise NotFound("Исключение не найдено")
    info = {"type": exc.exception_type.value, "starts_at": exc.starts_at.isoformat(), "ends_at": exc.ends_at.isoformat()}
    db.delete(exc)
    _apply_or_reject(db, force)
    audit(db, admin, "schedule.exception.delete", "schedule_exception", exception_id, info)
    db.commit()
    return Response(status_code=204)


@router.get("/schedule/conflicts")
def schedule_conflicts(admin: AdminUser, db: DB):
    return find_schedule_conflicts(db, get_app_settings(db), timeutil.now_utc())


# ---------- Услуги ----------

@router.get("/services", response_model=list[AdminServiceOut])
def admin_services(admin: AdminUser, db: DB):
    return db.scalars(select(Service).order_by(Service.sort_order, Service.created_at)).all()


@router.post("/services", response_model=AdminServiceOut, status_code=201)
def create_service(body: ServiceIn, admin: AdminUser, db: DB):
    data = body.model_dump()
    data["currency"] = data["currency"] or get_app_settings(db).currency
    service = Service(**data)
    db.add(service)
    db.flush()
    audit(db, admin, "service.create", "service", service.id, body.model_dump(mode="json"))
    db.commit()
    return service


@router.patch("/services/{service_id}", response_model=AdminServiceOut)
def update_service(service_id: uuid.UUID, body: ServicePatch, admin: AdminUser, db: DB):
    service = db.get(Service, service_id)
    if service is None:
        raise NotFound("Услуга не найдена")
    changes = body.model_dump(exclude_unset=True)
    # Существующие записи не меняются: в них хранится снимок названия, длительности и цены.
    for k, v in changes.items():
        if k in ("name", "duration_minutes", "price_minor", "currency", "is_active", "sort_order") and v is None:
            continue
        setattr(service, k, v)
    audit(db, admin, "service.update", "service", service.id, {k: v for k, v in body.model_dump(mode="json", exclude_unset=True).items()})
    db.commit()
    return service


# ---------- Настройки и журнал ----------

@router.get("/settings", response_model=AdminSettingsOut)
def get_settings_(admin: AdminUser, db: DB):
    return get_app_settings(db)


@router.patch("/settings", response_model=AdminSettingsOut)
def patch_settings(body: AdminSettingsPatch, admin: AdminUser, db: DB):
    s = get_app_settings(db)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    old = {k: getattr(s, k) for k in changes}
    for k, v in changes.items():
        setattr(s, k, v)
    audit(db, admin, "settings.update", "settings", 1, {"old": old, "new": changes})
    db.commit()
    return s


@router.get("/audit", response_model=Page[AuditOut])
def audit_log(admin: AdminUser, db: DB, page: Annotated[int, Query(ge=1)] = 1,
              page_size: Annotated[int, Query(ge=1, le=100)] = 50):
    total = db.scalar(select(func.count()).select_from(AdminAuditLog))
    items = db.scalars(select(AdminAuditLog).order_by(AdminAuditLog.id.desc())
                       .offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}
