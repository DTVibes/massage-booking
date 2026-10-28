from fastapi import APIRouter
from sqlalchemy import select

from app.config import get_settings
from app.deps import DB
from app.models import User, UserRole
from app.schemas import AuthOut, TelegramAuthIn, UserOut
from app.security import issue_session_token, validate_init_data

router = APIRouter(tags=["auth"])


@router.post("/auth/telegram", response_model=AuthOut)
def auth_telegram(body: TelegramAuthIn, db: DB):
    cfg = get_settings()
    data = validate_init_data(body.init_data, cfg.bot_token, cfg.init_data_max_age_seconds)
    name = " ".join(x for x in (data.first_name, data.last_name) if x).strip() or (data.username or "Клиент")

    user = db.scalar(select(User).where(User.telegram_id == data.user_id).with_for_update())
    if user is None:
        user = User(telegram_id=data.user_id, name=name[:200], role=UserRole.client)
        db.add(user)
    user.username = data.username
    if data.allows_write_to_pm:
        user.allows_write_to_pm = True
    # Роль администратора выдаётся только конфигурацией сервера (ADMIN_TELEGRAM_IDS)
    # или командой CLI create-admin; данные от клиента на роль не влияют.
    if data.user_id in cfg.admin_telegram_ids:
        user.role = UserRole.admin
    db.commit()
    db.refresh(user)
    if not user.is_active:
        from app.errors import Forbidden

        raise Forbidden("Доступ ограничен. Свяжитесь с массажистом.")
    token = issue_session_token(str(user.id), cfg.secret_key, cfg.session_ttl_seconds)
    return AuthOut(token=token, expires_in=cfg.session_ttl_seconds, user=UserOut.model_validate(user))
