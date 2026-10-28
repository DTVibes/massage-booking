from sqlalchemy.orm import Session

from app.models import AdminAuditLog, Appointment, AppointmentHistory, User


def record_history(db: Session, appt: Appointment, action: str, actor: User | None, *, old_starts_at=None,
                   new_starts_at=None, old_status=None, new_status=None, details: dict | None = None) -> AppointmentHistory:
    h = AppointmentHistory(
        appointment_id=appt.id,
        action=action,
        actor_id=actor.id if actor else None,
        actor_role=actor.role.value if actor else "system",
        old_starts_at=old_starts_at,
        new_starts_at=new_starts_at,
        old_status=old_status,
        new_status=new_status,
        details=details,
    )
    db.add(h)
    db.flush()
    return h


def audit(db: Session, admin: User, action: str, entity_type: str, entity_id=None, details: dict | None = None) -> None:
    db.add(AdminAuditLog(admin_id=admin.id, action=action, entity_type=entity_type,
                         entity_id=str(entity_id) if entity_id is not None else None, details=details))
