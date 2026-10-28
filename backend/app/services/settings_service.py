from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppSettings


def get_app_settings(db: Session) -> AppSettings:
    s = db.get(AppSettings, 1)
    if s is None:
        # Безопасный фолбэк: если команда init ещё не запускалась, создаём настройки по умолчанию.
        s = AppSettings(id=1, timezone=get_settings().timezone, reminder_hours=[24, 2])
        db.add(s)
        db.flush()
    return s
