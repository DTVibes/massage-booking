import uuid
from datetime import date, datetime, time, timedelta
from typing import Generic, Literal, TypeVar
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import AppointmentStatus, ExceptionType, UserRole

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


# --- Авторизация и профиль ---

class TelegramAuthIn(BaseModel):
    init_data: str = Field(min_length=10, max_length=4096)


class UserOut(ORM):
    id: uuid.UUID
    telegram_id: int | None
    name: str
    username: str | None
    phone: str | None
    role: UserRole
    created_at: datetime
    notifications_enabled: bool
    privacy_accepted_at: datetime | None = None


class AuthOut(BaseModel):
    token: str
    expires_in: int
    user: UserOut


class ProfileUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=32)
    notifications_enabled: bool | None = None


class PublicInfoOut(ORM):
    studio_name: str
    master_name: str
    welcome_text: str
    address: str
    contact_phone: str
    contact_telegram: str
    operator_name: str
    operator_inn: str
    privacy_email: str
    timezone: str
    currency: str
    booking_horizon_days: int
    cancel_min_hours: int
    allow_client_reschedule: bool


# --- Услуги ---

class ServiceOut(ORM):
    id: uuid.UUID
    name: str
    description: str
    duration_minutes: int
    price_minor: int
    currency: str


class AdminServiceOut(ServiceOut):
    is_active: bool
    sort_order: int
    buffer_minutes: int | None
    created_at: datetime
    updated_at: datetime


class ServiceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    duration_minutes: int = Field(ge=5, le=720)
    price_minor: int = Field(ge=0, le=10**10)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    is_active: bool = True
    sort_order: int = 0
    buffer_minutes: int | None = Field(default=None, ge=0, le=240)


class ServicePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    duration_minutes: int | None = Field(default=None, ge=5, le=720)
    price_minor: int | None = Field(default=None, ge=0, le=10**10)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    is_active: bool | None = None
    sort_order: int | None = None
    buffer_minutes: int | None = Field(default=None, ge=0, le=240)


# --- Доступность ---

class DateAvailabilityOut(BaseModel):
    date: date
    status: Literal["available", "full", "closed"]
    free_slots: int


class SlotOut(BaseModel):
    starts_at: datetime
    ends_at: datetime
    local_time: str


# --- Записи ---

class AppointmentCreateIn(BaseModel):
    service_id: uuid.UUID
    starts_at: datetime
    comment: str | None = Field(default=None, max_length=500)
    # Галочка «Согласен с политикой конфиденциальности» — нужна при первой записи.
    accept_privacy: bool = False


class RescheduleIn(BaseModel):
    starts_at: datetime


class CancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class AppointmentOut(ORM):
    id: uuid.UUID
    service_id: uuid.UUID | None
    service_name: str = Field(validation_alias="service_name_snapshot")
    duration_minutes: int
    price_minor: int = Field(validation_alias="price_minor_snapshot")
    currency: str = Field(validation_alias="currency_snapshot")
    starts_at: datetime
    ends_at: datetime
    status: AppointmentStatus
    comment: str | None
    created_at: datetime
    cancelled_at: datetime | None
    can_cancel: bool = False
    can_reschedule: bool = False


class MyAppointmentsOut(BaseModel):
    upcoming: list[AppointmentOut]
    history: list[AppointmentOut]
    cancelled: list[AppointmentOut]


class ClientBrief(ORM):
    id: uuid.UUID
    name: str
    phone: str | None
    telegram_id: int | None
    username: str | None


class AdminAppointmentOut(AppointmentOut):
    buffer_minutes: int
    blocked_until: datetime
    client: ClientBrief
    cancelled_by: uuid.UUID | None


class HistoryOut(ORM):
    id: int
    action: str
    actor_role: str | None
    old_starts_at: datetime | None
    new_starts_at: datetime | None
    old_status: str | None
    new_status: str | None
    details: dict | None
    created_at: datetime


class AdminAppointmentDetailOut(AdminAppointmentOut):
    history: list[HistoryOut]


class NewClientIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(max_length=32)


class AdminAppointmentCreateIn(BaseModel):
    client_id: uuid.UUID | None = None
    new_client: NewClientIn | None = None
    service_id: uuid.UUID
    starts_at: datetime
    comment: str | None = Field(default=None, max_length=1000)
    ignore_schedule: bool = False

    @model_validator(mode="after")
    def _client(self):
        if (self.client_id is None) == (self.new_client is None):
            raise ValueError("Укажите либо client_id, либо new_client")
        return self


class AdminAppointmentPatch(BaseModel):
    starts_at: datetime | None = None
    status: Literal["cancelled_by_admin", "completed", "no_show"] | None = None
    comment: str | None = Field(default=None, max_length=1000)
    reason: str | None = Field(default=None, max_length=500)
    ignore_schedule: bool = False
    notify_client: bool = True


# --- Клиенты ---

class AdminClientOut(ORM):
    id: uuid.UUID
    name: str
    username: str | None
    telegram_id: int | None
    phone: str | None
    created_at: datetime
    completed_count: int = 0
    cancelled_count: int = 0
    no_show_count: int = 0
    last_visit_at: datetime | None = None
    upcoming_at: datetime | None = None
    privacy_accepted_at: datetime | None = None
    anonymized_at: datetime | None = None


class AdminClientDetailOut(AdminClientOut):
    admin_notes: str | None
    is_active: bool
    appointments: list[AdminAppointmentOut]


class AdminClientPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=32)
    admin_notes: str | None = Field(default=None, max_length=5000)
    is_active: bool | None = None


# --- График ---

class TimeInterval(BaseModel):
    start: time
    end: time

    @model_validator(mode="after")
    def _order(self):
        if self.end <= self.start:
            raise ValueError("Окончание интервала должно быть позже начала")
        return self


class DaySchedule(BaseModel):
    weekday: int = Field(ge=0, le=6)
    is_working_day: bool
    intervals: list[TimeInterval] = []

    @model_validator(mode="after")
    def _check(self):
        if self.is_working_day and not self.intervals:
            raise ValueError("Для рабочего дня нужен хотя бы один интервал")
        ivs = sorted(self.intervals, key=lambda i: i.start)
        for a, b in zip(ivs, ivs[1:], strict=False):
            if b.start < a.end:
                raise ValueError("Интервалы рабочего времени пересекаются")
        self.intervals = ivs
        return self


class ScheduleExceptionOut(ORM):
    conflicts: list[dict] = []
    id: int
    starts_at: datetime
    ends_at: datetime
    exception_type: ExceptionType
    reason: str | None
    created_at: datetime


class ScheduleOut(BaseModel):
    days: list[DaySchedule]
    exceptions: list[ScheduleExceptionOut]
    timezone: str
    conflicts: list[dict] = []


class ScheduleIn(BaseModel):
    days: list[DaySchedule]
    force: bool = False

    @field_validator("days")
    @classmethod
    def _unique(cls, v: list[DaySchedule]):
        if len({d.weekday for d in v}) != len(v):
            raise ValueError("Дни недели повторяются")
        return v


class ScheduleExceptionIn(BaseModel):
    starts_at: datetime
    ends_at: datetime
    exception_type: ExceptionType
    reason: str | None = Field(default=None, max_length=500)
    force: bool = False

    @model_validator(mode="after")
    def _order(self):
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("Время должно содержать часовой пояс")
        if self.ends_at <= self.starts_at:
            raise ValueError("Окончание должно быть позже начала")
        if self.ends_at - self.starts_at > timedelta(days=366):
            raise ValueError("Слишком длинный интервал")
        return self


# --- Настройки ---

class AdminSettingsOut(PublicInfoOut):
    default_duration_minutes: int
    slot_step_minutes: int
    buffer_minutes: int
    min_lead_minutes: int
    max_active_bookings_per_client: int
    reminder_hours: list[int]
    notify_admin_new: bool
    notify_admin_cancel: bool
    notify_admin_reschedule: bool


class AdminSettingsPatch(BaseModel):
    studio_name: str | None = Field(default=None, max_length=200)
    master_name: str | None = Field(default=None, max_length=200)
    welcome_text: str | None = Field(default=None, max_length=2000)
    address: str | None = Field(default=None, max_length=500)
    contact_phone: str | None = Field(default=None, max_length=32)
    contact_telegram: str | None = Field(default=None, max_length=64)
    operator_name: str | None = Field(default=None, max_length=300)
    operator_inn: str | None = Field(default=None, pattern=r"^(\d{10}|\d{12})?$")
    privacy_email: str | None = Field(default=None, max_length=200)
    timezone: str | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    default_duration_minutes: int | None = Field(default=None, ge=5, le=720)
    slot_step_minutes: int | None = Field(default=None, ge=5, le=240)
    buffer_minutes: int | None = Field(default=None, ge=0, le=240)
    booking_horizon_days: int | None = Field(default=None, ge=1, le=365)
    min_lead_minutes: int | None = Field(default=None, ge=0, le=7 * 24 * 60)
    cancel_min_hours: int | None = Field(default=None, ge=0, le=24 * 14)
    allow_client_reschedule: bool | None = None
    max_active_bookings_per_client: int | None = Field(default=None, ge=1, le=50)
    reminder_hours: list[int] | None = Field(default=None, max_length=5)
    notify_admin_new: bool | None = None
    notify_admin_cancel: bool | None = None
    notify_admin_reschedule: bool | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v):
        if v is not None and v not in available_timezones():
            raise ValueError("Неизвестный часовой пояс")
        return v

    @field_validator("reminder_hours")
    @classmethod
    def _rem(cls, v):
        if v is not None and any(h < 1 or h > 168 for h in v):
            raise ValueError("Напоминание: от 1 до 168 часов")
        return sorted(set(v), reverse=True) if v is not None else v


class AuditOut(ORM):
    id: int
    admin_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    details: dict | None
    created_at: datetime
