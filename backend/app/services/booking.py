"""Бизнес-логика записей: создание, отмена, перенос, смена статуса.

Защита от двойного бронирования двухуровневая:
1. Предварительная проверка по рассчитанным слотам (понятные сообщения об ошибках).
2. Exclusion constraint ex_appointments_no_overlap в PostgreSQL — окончательная гарантия
   при параллельных транзакциях: вторая пересекающаяся вставка/изменение получает ошибку,
   которая превращается в 409 Conflict.
"""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.models import Appointment, AppointmentStatus, AppSettings, Service, User, UserRole
from app.services import notifications
from app.services.audit import record_history
from app.services.availability import ScheduleContext, earliest_start, horizon_dates, service_buffer
from app.services.settings_service import get_app_settings

OVERLAP_CONSTRAINT = "ex_appointments_no_overlap"
IDEMPOTENCY_CONSTRAINT = "uq_appointments_idempotency"

SLOT_TAKEN_MSG = "Это время только что заняли. Пожалуйста, выберите другое время."


def _constraint_name(exc: IntegrityError) -> str | None:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


def _normalize_start(starts_at: datetime) -> datetime:
    if starts_at.tzinfo is None:
        raise ValidationFailed("Время должно содержать часовой пояс", code="naive_datetime")
    return starts_at.replace(second=0, microsecond=0)


def validate_client_slot(db: Session, settings: AppSettings, service: Service, starts_at: datetime,
                         now: datetime, exclude_appointment_id: uuid.UUID | None = None) -> None:
    """Повторяет на сервере все правила расчёта слотов для выбранного времени."""
    if starts_at <= now:
        raise ValidationFailed("Нельзя записаться на прошедшее время", code="past_time")
    local_date = starts_at.astimezone(ZoneInfo(settings.timezone)).date()
    if local_date not in horizon_dates(settings, now):
        raise ValidationFailed(
            f"Запись доступна только на ближайшие {settings.booking_horizon_days} дн.", code="outside_horizon"
        )
    if starts_at < earliest_start(settings, now):
        raise ValidationFailed("Слишком мало времени до начала визита, выберите время позже", code="too_soon")
    ctx = ScheduleContext(db, settings, local_date, local_date, exclude_appointment_id)
    buffer = service_buffer(settings, service)
    if starts_at not in {s.starts_at for s in ctx.candidates(local_date, service.duration_minutes, buffer)}:
        raise ValidationFailed("Выбранное время вне рабочего графика", code="outside_schedule")
    if ctx.is_busy(starts_at, service.duration_minutes, buffer):
        raise Conflict(SLOT_TAKEN_MSG, code="slot_taken")


def _get_service(db: Session, service_id: uuid.UUID, require_active: bool) -> Service:
    service = db.get(Service, service_id)
    if service is None or (require_active and not service.is_active):
        raise NotFound("Услуга не найдена или недоступна", code="service_not_found")
    return service


def _commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _constraint_name(exc) == OVERLAP_CONSTRAINT:
            raise Conflict(SLOT_TAKEN_MSG, code="slot_taken") from exc
        raise


def create_appointment(db: Session, *, actor: User, client: User, service_id: uuid.UUID, starts_at: datetime,
                       now: datetime, idempotency_key: str | None = None, comment: str | None = None,
                       ignore_schedule: bool = False, as_admin: bool = False) -> tuple[Appointment, bool]:
    """Возвращает (запись, создана_ли_новая). Повтор с тем же Idempotency-Key возвращает существующую."""
    is_admin = as_admin and actor.role == UserRole.admin
    if idempotency_key:
        existing = db.scalar(
            select(Appointment).where(Appointment.client_id == client.id, Appointment.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing, False

    settings = get_app_settings(db)
    service = _get_service(db, service_id, require_active=not is_admin)
    starts_at = _normalize_start(starts_at)

    if not client.is_active:
        raise Forbidden("Клиент заблокирован", code="client_inactive")
    if not is_admin:
        if not client.phone:
            raise ValidationFailed("Укажите номер телефона в профиле, чтобы завершить запись", code="phone_required")
        active = db.scalar(
            select(func.count()).select_from(Appointment).where(
                Appointment.client_id == client.id,
                Appointment.status == AppointmentStatus.booked,
                Appointment.starts_at > now,
            )
        )
        if active >= settings.max_active_bookings_per_client:
            raise Conflict(
                f"У вас уже {active} активн. записи. Новую запись можно создать после визита или отмены.",
                code="too_many_active_bookings",
            )

    if is_admin and ignore_schedule:
        if starts_at <= now - timedelta(days=1):
            raise ValidationFailed("Нельзя создать запись в прошлом", code="past_time")
    else:
        validate_client_slot(db, settings, service, starts_at, now)

    buffer = service_buffer(settings, service)
    appt = Appointment(
        id=uuid.uuid4(),
        client_id=client.id,
        service_id=service.id,
        service_name_snapshot=service.name,
        duration_minutes=service.duration_minutes,
        price_minor_snapshot=service.price_minor,
        currency_snapshot=service.currency,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=service.duration_minutes),
        buffer_minutes=buffer,
        blocked_until=starts_at + timedelta(minutes=service.duration_minutes + buffer),
        status=AppointmentStatus.booked,
        comment=comment,
        created_by=actor.id,
        idempotency_key=idempotency_key,
    )
    db.add(appt)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        name = _constraint_name(exc)
        if name == OVERLAP_CONSTRAINT:
            raise Conflict(SLOT_TAKEN_MSG, code="slot_taken") from exc
        if name == IDEMPOTENCY_CONSTRAINT and idempotency_key:
            existing = db.scalar(
                select(Appointment).where(Appointment.client_id == client.id, Appointment.idempotency_key == idempotency_key)
            )
            if existing is not None:
                return existing, False
        raise

    record_history(db, appt, "created", actor, new_starts_at=starts_at, new_status=appt.status.value)
    notifications.notify_event(db, settings, appt, client, "created", by_admin=is_admin, now=now, event_id="1")
    notifications.schedule_reminders(db, settings, appt, client, now)
    _commit_or_conflict(db)
    return appt, True


def get_appointment_for_update(db: Session, appointment_id: uuid.UUID) -> Appointment:
    appt = db.scalar(select(Appointment).where(Appointment.id == appointment_id).with_for_update())
    if appt is None:
        raise NotFound("Запись не найдена")
    return appt


def _check_owner(appt: Appointment, user: User) -> None:
    if appt.client_id != user.id:
        # 404, а не 403 — не раскрываем существование чужих записей.
        raise NotFound("Запись не найдена")


def _check_client_change_window(settings: AppSettings, appt: Appointment, now: datetime, verb: str) -> None:
    if appt.status != AppointmentStatus.booked:
        raise Conflict("Запись уже не активна", code="not_active")
    if appt.starts_at - now < timedelta(hours=settings.cancel_min_hours):
        contact = settings.contact_phone or settings.contact_telegram
        tail = f" Свяжитесь с массажистом: {contact}." if contact else " Пожалуйста, свяжитесь с массажистом."
        raise Conflict(
            f"{verb} возможна не позднее чем за {settings.cancel_min_hours} ч до визита.{tail}",
            code="too_late_to_change",
        )


def cancel_appointment(db: Session, *, actor: User, appointment_id: uuid.UUID, now: datetime,
                       reason: str | None = None, notify_client: bool = True, as_admin: bool = False) -> Appointment:
    settings = get_app_settings(db)
    appt = get_appointment_for_update(db, appointment_id)
    is_admin = as_admin and actor.role == UserRole.admin
    if not is_admin:
        _check_owner(appt, actor)
        _check_client_change_window(settings, appt, now, "Самостоятельная отмена")
    elif appt.status != AppointmentStatus.booked:
        raise Conflict("Отменить можно только активную запись", code="not_active")

    old_status = appt.status
    appt.status = AppointmentStatus.cancelled_by_admin if is_admin else AppointmentStatus.cancelled_by_client
    appt.cancelled_at = now
    appt.cancelled_by = actor.id
    h = record_history(db, appt, "cancelled", actor, old_status=old_status.value, new_status=appt.status.value,
                       details={"reason": reason} if reason else None)
    notifications.cancel_pending_reminders(db, appt.id)
    client = db.get(User, appt.client_id)
    notifications.notify_event(db, settings, appt, client, "cancelled", by_admin=is_admin, now=now,
                               event_id=str(h.id), payload={"reason": reason} if reason else None,
                               notify_client=notify_client)
    db.commit()
    return appt


def reschedule_appointment(db: Session, *, actor: User, appointment_id: uuid.UUID, new_starts_at: datetime,
                           now: datetime, ignore_schedule: bool = False, notify_client: bool = True,
                           as_admin: bool = False) -> Appointment:
    """Атомарный перенос: запись меняется в одной транзакции. Если новый слот занят,
    транзакция откатывается и исходная запись остаётся активной без изменений."""
    settings = get_app_settings(db)
    appt = get_appointment_for_update(db, appointment_id)
    is_admin = as_admin and actor.role == UserRole.admin
    if not is_admin:
        _check_owner(appt, actor)
        if not settings.allow_client_reschedule:
            raise Forbidden("Перенос записи доступен только через массажиста", code="reschedule_disabled")
        _check_client_change_window(settings, appt, now, "Самостоятельный перенос")
    elif appt.status != AppointmentStatus.booked:
        raise Conflict("Перенести можно только активную запись", code="not_active")

    new_starts_at = _normalize_start(new_starts_at)
    if new_starts_at == appt.starts_at:
        raise ValidationFailed("Новое время совпадает с текущим", code="same_time")

    # Валидируем по параметрам, зафиксированным в записи (снимок услуги), а не текущей услуги.
    snapshot = Service(duration_minutes=appt.duration_minutes, buffer_minutes=appt.buffer_minutes)
    if is_admin and ignore_schedule:
        if new_starts_at <= now - timedelta(days=1):
            raise ValidationFailed("Нельзя перенести запись в прошлое", code="past_time")
    else:
        validate_client_slot(db, settings, snapshot, new_starts_at, now, exclude_appointment_id=appt.id)

    old_starts_at = appt.starts_at
    appt.starts_at = new_starts_at
    appt.ends_at = new_starts_at + timedelta(minutes=appt.duration_minutes)
    appt.blocked_until = appt.ends_at + timedelta(minutes=appt.buffer_minutes)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if _constraint_name(exc) == OVERLAP_CONSTRAINT:
            raise Conflict(SLOT_TAKEN_MSG, code="slot_taken") from exc
        raise

    h = record_history(db, appt, "rescheduled", actor, old_starts_at=old_starts_at, new_starts_at=new_starts_at)
    client = db.get(User, appt.client_id)
    notifications.cancel_pending_reminders(db, appt.id)
    notifications.schedule_reminders(db, settings, appt, client, now)
    notifications.notify_event(db, settings, appt, client, "rescheduled", by_admin=is_admin, now=now,
                               event_id=str(h.id), payload={"old_starts_at": old_starts_at.isoformat()},
                               notify_client=notify_client)
    _commit_or_conflict(db)
    return appt


def set_visit_status(db: Session, *, actor: User, appointment_id: uuid.UUID, status: AppointmentStatus,
                     now: datetime) -> Appointment:
    if status not in (AppointmentStatus.completed, AppointmentStatus.no_show):
        raise ValidationFailed("Недопустимый статус", code="bad_status")
    appt = get_appointment_for_update(db, appointment_id)
    if appt.status not in (AppointmentStatus.booked, AppointmentStatus.completed, AppointmentStatus.no_show):
        raise Conflict("Нельзя изменить статус отменённой записи", code="not_active")
    if appt.starts_at > now:
        raise Conflict("Визит ещё не начался", code="visit_not_started")
    old = appt.status
    appt.status = status
    notifications.cancel_pending_reminders(db, appt.id)
    record_history(db, appt, "status_changed", actor, old_status=old.value, new_status=status.value)
    db.commit()
    return appt
