import enum
import uuid
from datetime import datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID, ExcludeConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserRole(str, enum.Enum):
    client = "client"
    admin = "admin"


class AppointmentStatus(str, enum.Enum):
    booked = "booked"
    cancelled_by_client = "cancelled_by_client"
    cancelled_by_admin = "cancelled_by_admin"
    completed = "completed"
    no_show = "no_show"


class ExceptionType(str, enum.Enum):
    closed = "closed"
    open = "open"
    break_ = "break"


class NotificationStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
    skipped = "skipped"
    cancelled = "cancelled"


def _enum(e: type[enum.Enum], name: str) -> Enum:
    return Enum(e, name=name, values_callable=lambda x: [m.value for m in x])


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # NULL допускается для клиентов, добавленных администратором вручную (без Telegram).
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    name: Mapped[str] = mapped_column(String(200))
    username: Mapped[str | None] = mapped_column(String(64))
    phone: Mapped[str | None] = mapped_column(String(20))
    role: Mapped[UserRole] = mapped_column(_enum(UserRole, "user_role"), default=UserRole.client)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    # Можно ли писать пользователю в личку от имени бота.
    allows_write_to_pm: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    bot_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bot_blocked: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    admin_notes: Mapped[str | None] = mapped_column(Text)
    # Когда клиент согласился с политикой конфиденциальности (152-ФЗ). NULL — ещё не соглашался.
    privacy_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Когда персональные данные клиента удалены (обезличены) по запросу.
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    appointments: Mapped[list["Appointment"]] = relationship(
        back_populates="client", foreign_keys="Appointment.client_id"
    )

    @property
    def can_receive_messages(self) -> bool:
        return (
            self.telegram_id is not None
            and not self.bot_blocked
            and (self.allows_write_to_pm or self.bot_started_at is not None)
        )


class Service(TimestampMixin, Base):
    __tablename__ = "services"
    __table_args__ = (
        CheckConstraint("duration_minutes > 0 AND duration_minutes <= 720", name="ck_services_duration"),
        CheckConstraint("price_minor >= 0", name="ck_services_price"),
        CheckConstraint("buffer_minutes IS NULL OR buffer_minutes >= 0", name="ck_services_buffer"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    duration_minutes: Mapped[int] = mapped_column(Integer)
    price_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[str] = mapped_column(String(3))
    # NULL — использовать общий буфер из настроек (задел на индивидуальный буфер услуги).
    buffer_minutes: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class Appointment(TimestampMixin, Base):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_appointments_time"),
        CheckConstraint("blocked_until >= ends_at", name="ck_appointments_blocked"),
        # Ключевая защита от двойного бронирования: активные записи (с учётом буфера)
        # не могут пересекаться на уровне PostgreSQL.
        ExcludeConstraint(
            (text("tstzrange(starts_at, blocked_until, '[)')"), "&&"),
            name="ex_appointments_no_overlap",
            using="gist",
            where=text("status = 'booked'"),
        ),
        UniqueConstraint("client_id", "idempotency_key", name="uq_appointments_idempotency"),
        Index("ix_appointments_starts_at", "starts_at"),
        Index("ix_appointments_client", "client_id", "starts_at"),
        Index("ix_appointments_status_starts", "status", "starts_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    service_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("services.id", ondelete="SET NULL"))
    service_name_snapshot: Mapped[str] = mapped_column(String(200))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    price_minor_snapshot: Mapped[int] = mapped_column(BigInteger)
    currency_snapshot: Mapped[str] = mapped_column(String(3))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    buffer_minutes: Mapped[int] = mapped_column(Integer)
    # starts_at + duration + buffer: конец блокировки времени массажиста.
    blocked_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[AppointmentStatus] = mapped_column(
        _enum(AppointmentStatus, "appointment_status"), default=AppointmentStatus.booked
    )
    comment: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    idempotency_key: Mapped[str | None] = mapped_column(String(64))

    client: Mapped[User] = relationship(back_populates="appointments", foreign_keys=[client_id])


class AppointmentHistory(Base):
    __tablename__ = "appointment_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(32))  # created, cancelled, rescheduled, status_changed, updated
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_role: Mapped[str | None] = mapped_column(String(16))
    old_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    new_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    old_status: Mapped[str | None] = mapped_column(String(32))
    new_status: Mapped[str | None] = mapped_column(String(32))
    details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    admin_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class WorkingHours(TimestampMixin, Base):
    __tablename__ = "working_hours"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_working_hours_weekday"),
        CheckConstraint(
            "(is_working_day AND start_time IS NOT NULL AND end_time IS NOT NULL AND end_time > start_time)"
            " OR (NOT is_working_day)",
            name="ck_working_hours_interval",
        ),
        Index("ix_working_hours_weekday", "weekday"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    weekday: Mapped[int] = mapped_column(SmallInteger)  # 0 = понедельник
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    is_working_day: Mapped[bool] = mapped_column(Boolean, default=True)


class ScheduleException(Base):
    __tablename__ = "schedule_exceptions"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_schedule_exceptions_time"),
        Index("ix_schedule_exceptions_range", "starts_at", "ends_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exception_type: Mapped[ExceptionType] = mapped_column(_enum(ExceptionType, "schedule_exception_type"))
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppSettings(TimestampMixin, Base):
    """Единственная строка (id = 1) с бизнес-настройками. Секреты здесь не хранятся."""

    __tablename__ = "settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_settings_singleton"),
        CheckConstraint("slot_step_minutes BETWEEN 5 AND 240", name="ck_settings_step"),
        CheckConstraint("buffer_minutes BETWEEN 0 AND 240", name="ck_settings_buffer"),
        CheckConstraint("booking_horizon_days BETWEEN 1 AND 365", name="ck_settings_horizon"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    studio_name: Mapped[str] = mapped_column(String(200), default="Массаж")
    master_name: Mapped[str] = mapped_column(String(200), default="")
    welcome_text: Mapped[str] = mapped_column(Text, default="")
    address: Mapped[str] = mapped_column(String(500), default="")
    contact_phone: Mapped[str] = mapped_column(String(32), default="")
    contact_telegram: Mapped[str] = mapped_column(String(64), default="")
    # Оператор персональных данных для политики конфиденциальности.
    operator_name: Mapped[str] = mapped_column(String(300), default="", server_default="")
    operator_inn: Mapped[str] = mapped_column(String(12), default="", server_default="")
    privacy_email: Mapped[str] = mapped_column(String(200), default="", server_default="")
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    default_duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    slot_step_minutes: Mapped[int] = mapped_column(Integer, default=30)
    buffer_minutes: Mapped[int] = mapped_column(Integer, default=10)
    booking_horizon_days: Mapped[int] = mapped_column(Integer, default=14)
    min_lead_minutes: Mapped[int] = mapped_column(Integer, default=60)
    cancel_min_hours: Mapped[int] = mapped_column(Integer, default=6)
    allow_client_reschedule: Mapped[bool] = mapped_column(Boolean, default=True)
    max_active_bookings_per_client: Mapped[int] = mapped_column(Integer, default=3)
    reminder_hours: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=lambda: [24, 2])
    notify_admin_new: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_admin_cancel: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_admin_reschedule: Mapped[bool] = mapped_column(Boolean, default=True)


class NotificationJob(Base):
    __tablename__ = "notification_jobs"
    __table_args__ = (
        # Одна задача на событие и получателя — защита от дублей.
        UniqueConstraint("dedup_key", "recipient_telegram_id", name="uq_notification_jobs_dedup"),
        Index("ix_notification_jobs_due", "status", "scheduled_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), index=True
    )
    recipient_telegram_id: Mapped[int] = mapped_column(BigInteger)
    notification_type: Mapped[str] = mapped_column(String(48))
    dedup_key: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[NotificationStatus] = mapped_column(
        _enum(NotificationStatus, "notification_status"), default=NotificationStatus.pending
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
