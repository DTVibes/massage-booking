"""Персональные данные клиентов (152-ФЗ): согласие и удаление (обезличивание) по запросу."""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.errors import ValidationFailed
from app.models import (
    AdminAuditLog,
    Appointment,
    AppointmentStatus,
    NotificationJob,
    NotificationStatus,
    User,
    UserRole,
)
from app.services import notifications
from app.services.audit import record_history
from app.services.settings_service import get_app_settings

ANONYMIZED_NAME = "Клиент удалён"


def anonymize_client(db: Session, *, client: User, actor: User, now: datetime) -> User:
    """Удаляет персональные данные клиента, оставляя обезличенную историю визитов.

    Будущие записи отменяются, неотправленные уведомления снимаются, имя/телефон/Telegram,
    заметки и комментарии к записям стираются. Записи остаются без привязки к личности —
    чтобы не сломать расписание и статистику. Коммит делает вызывающий код.
    """
    if client.role == UserRole.admin:
        raise ValidationFailed("Данные администратора так удалить нельзя", code="admin_cannot_be_anonymized")
    if client.anonymized_at is not None:
        return client

    settings = get_app_settings(db)
    by_admin = actor.role == UserRole.admin and actor.id != client.id
    appts = db.scalars(select(Appointment).where(Appointment.client_id == client.id).with_for_update()).all()
    for appt in appts:
        if appt.status == AppointmentStatus.booked and appt.starts_at > now:
            old = appt.status
            appt.status = AppointmentStatus.cancelled_by_admin if by_admin else AppointmentStatus.cancelled_by_client
            appt.cancelled_at = now
            appt.cancelled_by = actor.id
            h = record_history(db, appt, "cancelled", actor, old_status=old.value, new_status=appt.status.value,
                               details={"reason": "Удаление персональных данных"})
            # Мастеру сообщаем, что время освободилось; клиенту писать уже не нужно.
            notifications.notify_event(db, settings, appt, client, "cancelled", by_admin=by_admin, now=now,
                                       event_id=str(h.id), notify_client=False)
        appt.comment = None

    if client.telegram_id is not None:
        # Снимаем неотправленные сообщения клиенту (напоминания и т.п.) и стираем их содержимое.
        db.execute(update(NotificationJob)
                   .where(NotificationJob.recipient_telegram_id == client.telegram_id,
                          NotificationJob.status == NotificationStatus.pending)
                   .values(status=NotificationStatus.cancelled, last_error="Данные клиента удалены"))
        db.execute(update(NotificationJob).where(NotificationJob.recipient_telegram_id == client.telegram_id)
                   .values(payload=None))
    db.execute(update(AdminAuditLog).where(AdminAuditLog.entity_type == "user",
                                           AdminAuditLog.entity_id == str(client.id)).values(details=None))

    client.name = ANONYMIZED_NAME
    client.phone = None
    client.telegram_id = None
    client.username = None
    client.admin_notes = None
    client.is_active = False
    client.notifications_enabled = False
    client.allows_write_to_pm = False
    client.bot_started_at = None
    client.privacy_accepted_at = None
    client.anonymized_at = now
    db.flush()
    return client

