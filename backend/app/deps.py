import uuid
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import Forbidden, Unauthorized
from app.models import User, UserRole
from app.security import read_session_token

DB = Annotated[Session, Depends(get_db)]


def current_user(db: DB, authorization: Annotated[str | None, Header()] = None) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise Unauthorized("Требуется авторизация через Telegram")
    user_id = read_session_token(authorization[7:], get_settings().secret_key)
    try:
        user = db.get(User, uuid.UUID(user_id))
    except ValueError as exc:
        raise Unauthorized("Сессия недействительна") from exc
    if user is None or not user.is_active:
        raise Unauthorized("Пользователь не найден или заблокирован")
    return user


def admin_user(user: Annotated[User, Depends(current_user)]) -> User:
    # Роль всегда читается из БД на каждый запрос — токен роль не содержит.
    if user.role != UserRole.admin:
        raise Forbidden("Недостаточно прав")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
AdminUser = Annotated[User, Depends(admin_user)]
