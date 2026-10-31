"""Клиентские endpoints: профиль, услуги, доступность, собственные записи."""

import uuid
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Header, Query, Response
from sqlalchemy import select

from app import timeutil
from app.deps import DB, CurrentUser
from app.errors import NotFound, ValidationFailed
from app.models import Appointment, AppointmentStatus, Service
from app.schemas import (
    AppointmentCreateIn,
    AppointmentOut,
    CancelIn,
    DateAvailabilityOut,
    MyAppointmentsOut,
    ProfileUpdateIn,
    PublicInfoOut,
    RescheduleIn,
    ServiceOut,
    SlotOut,
    UserOut,
)
from app.services import booking, privacy
from app.services.availability import appointment_snapshot, available_dates, available_slots, slots_out
from app.services.phone import normalize_phone
from app.services.settings_service import get_app_settings

router = APIRouter()


@router.get("/info", response_model=PublicInfoOut, tags=["public"])
def public_info(db: DB):
    return get_app_settings(db)


@router.get("/me", response_model=UserOut, tags=["profile"])
def me(user: CurrentUser):
    return user


@router.patch("/me/profile", response_model=UserOut, tags=["profile"])
def update_profile(body: ProfileUpdateIn, user: CurrentUser, db: DB):
    # Меняется только профиль текущего пользователя (id берётся из сессии, не из запроса).
    if body.phone is not None:
        user.phone = normalize_phone(body.phone)
    if body.name is not None:
        user.name = body.name.strip()
    if body.notifications_enabled is not None:
        user.notifications_enabled = body.notifications_enabled
    db.commit()
    return user


@router.delete("/me", status_code=204, tags=["profile"])
def delete_my_data(user: CurrentUser, db: DB):
    """Клиент удаляет свои персональные данные (отзыв согласия, ст. 9 и 21 152-ФЗ)."""
    privacy.anonymize_client(db, client=user, actor=user, now=timeutil.now_utc())
    db.commit()
    return Response(status_code=204)


@router.get("/services", response_model=list[ServiceOut], tags=["services"])
def list_services(db: DB):
    return db.scalars(select(Service).where(Service.is_active).order_by(Service.sort_order, Service.name)).all()


def _active_service(db, service_id: uuid.UUID) -> Service:
    service = db.get(Service, service_id)
    if service is None or not service.is_active:
        raise NotFound("Услуга не найдена или недоступна", code="service_not_found")
    return service


@router.get("/availability/dates", response_model=list[DateAvailabilityOut], tags=["availability"])
def availability_dates(service_id: uuid.UUID, user: CurrentUser, db: DB):
    settings = get_app_settings(db)
    return available_dates(db, settings, _active_service(db, service_id), timeutil.now_utc())


@router.get("/availability/slots", response_model=list[SlotOut], tags=["availability"])
def availability_slots(date: date, user: CurrentUser, db: DB, service_id: uuid.UUID | None = None,
                       exclude_appointment_id: uuid.UUID | None = None):
    """Свободные слоты на дату. Для переноса передаётся exclude_appointment_id: тогда
    используется длительность из снимка записи, а сама запись не считается занятостью."""
    settings = get_app_settings(db)
    if exclude_appointment_id is not None:
        appt = db.get(Appointment, exclude_appointment_id)
        if appt is None or appt.client_id != user.id:
            raise NotFound("Запись не найдена")
        service, exclude = appointment_snapshot(appt), appt.id
    elif service_id is not None:
        service, exclude = _active_service(db, service_id), None
    else:
        raise ValidationFailed("Укажите service_id или exclude_appointment_id")
    return slots_out(available_slots(db, settings, service, date, timeutil.now_utc(), exclude), settings)


def _with_permissions(appt: Appointment, settings, now) -> AppointmentOut:
    out = AppointmentOut.model_validate(appt)
    changeable = appt.status == AppointmentStatus.booked and appt.starts_at - now >= timedelta(hours=settings.cancel_min_hours)
    out.can_cancel = changeable
    out.can_reschedule = changeable and settings.allow_client_reschedule
    return out


@router.post("/appointments", response_model=AppointmentOut, status_code=201, tags=["appointments"])
def create_appointment(body: AppointmentCreateIn, user: CurrentUser, db: DB, response: Response,
                       idempotency_key: Annotated[str | None, Header(max_length=64)] = None):
    now = timeutil.now_utc()
    if user.privacy_accepted_at is None:
        if not body.accept_privacy:
            raise ValidationFailed("Чтобы записаться, подтвердите согласие с политикой конфиденциальности",
                                   code="privacy_consent_required")
        user.privacy_accepted_at = now
    appt, created = booking.create_appointment(
        db, actor=user, client=user, service_id=body.service_id, starts_at=body.starts_at, now=now,
        idempotency_key=idempotency_key, comment=body.comment,
    )
    if not created:
        response.status_code = 200
    return _with_permissions(appt, get_app_settings(db), now)


@router.get("/appointments/my", response_model=MyAppointmentsOut, tags=["appointments"])
def my_appointments(user: CurrentUser, db: DB, history_limit: Annotated[int, Query(ge=1, le=200)] = 50):
    now = timeutil.now_utc()
    settings = get_app_settings(db)
    rows = db.scalars(select(Appointment).where(Appointment.client_id == user.id).order_by(Appointment.starts_at)).all()
    upcoming = [_with_permissions(a, settings, now) for a in rows
                if a.status == AppointmentStatus.booked and a.ends_at > now]
    history = [_with_permissions(a, settings, now) for a in reversed(rows)
               if a.status in (AppointmentStatus.completed, AppointmentStatus.no_show)
               or (a.status == AppointmentStatus.booked and a.ends_at <= now)][:history_limit]
    cancelled = [_with_permissions(a, settings, now) for a in reversed(rows)
                 if a.status in (AppointmentStatus.cancelled_by_client, AppointmentStatus.cancelled_by_admin)][:history_limit]
    return MyAppointmentsOut(upcoming=upcoming, history=history, cancelled=cancelled)


@router.post("/appointments/{appointment_id}/cancel", response_model=AppointmentOut, tags=["appointments"])
def cancel(appointment_id: uuid.UUID, user: CurrentUser, db: DB, body: CancelIn | None = None):
    now = timeutil.now_utc()
    appt = booking.cancel_appointment(db, actor=user, appointment_id=appointment_id, now=now,
                                      reason=body.reason if body else None)
    return _with_permissions(appt, get_app_settings(db), now)


@router.post("/appointments/{appointment_id}/reschedule", response_model=AppointmentOut, tags=["appointments"])
def reschedule(appointment_id: uuid.UUID, body: RescheduleIn, user: CurrentUser, db: DB):
    now = timeutil.now_utc()
    appt = booking.reschedule_appointment(db, actor=user, appointment_id=appointment_id,
                                          new_starts_at=body.starts_at, now=now)
    return _with_permissions(appt, get_app_settings(db), now)
