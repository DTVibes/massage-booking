"""Проверка Telegram Mini Apps initData и выпуск сессионных токенов приложения."""

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from app.errors import Unauthorized


@dataclass
class TelegramInitData:
    user_id: int
    first_name: str
    last_name: str | None
    username: str | None
    allows_write_to_pm: bool
    auth_date: int
    raw: dict


def _secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def compute_init_data_hash(fields: dict[str, str], bot_token: str) -> str:
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()) if k != "hash")
    return hmac.new(_secret_key(bot_token), data_check_string.encode(), hashlib.sha256).hexdigest()


def validate_init_data(init_data: str, bot_token: str, max_age_seconds: int, now: float | None = None) -> TelegramInitData:
    """Алгоритм из документации Telegram: HMAC-SHA256 с ключом HMAC("WebAppData", bot_token)."""
    if not init_data or not bot_token:
        raise Unauthorized("Нет данных авторизации Telegram")
    try:
        fields = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError as exc:
        raise Unauthorized("Некорректные данные авторизации Telegram") from exc

    received_hash = fields.get("hash")
    if not received_hash:
        raise Unauthorized("Отсутствует подпись данных Telegram")
    if not hmac.compare_digest(compute_init_data_hash(fields, bot_token), received_hash):
        raise Unauthorized("Подпись данных Telegram недействительна")

    try:
        auth_date = int(fields.get("auth_date", "0"))
    except ValueError as exc:
        raise Unauthorized("Некорректная дата авторизации") from exc
    now = time.time() if now is None else now
    if auth_date <= 0 or now - auth_date > max_age_seconds or auth_date - now > 300:
        raise Unauthorized("Данные авторизации устарели, откройте приложение заново", code="init_data_expired")

    try:
        user = json.loads(fields["user"])
        user_id = int(user["id"])
    except (KeyError, ValueError, TypeError) as exc:
        raise Unauthorized("В данных Telegram нет пользователя") from exc

    return TelegramInitData(
        user_id=user_id,
        first_name=str(user.get("first_name") or ""),
        last_name=user.get("last_name"),
        username=user.get("username"),
        allows_write_to_pm=bool(user.get("allows_write_to_pm", False)),
        auth_date=auth_date,
        raw=fields,
    )


def build_init_data(user: dict, bot_token: str, auth_date: int | None = None, extra: dict | None = None) -> str:
    """Формирует корректно подписанный initData (для тестов и локальной разработки)."""
    from urllib.parse import urlencode

    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAAdev",
        "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False),
        **(extra or {}),
    }
    fields["hash"] = compute_init_data_hash(fields, bot_token)
    return urlencode(fields)


# --- Сессионные токены приложения (HMAC-подпись, без хранения на сервере) ---

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def issue_session_token(user_id: str, secret_key: str, ttl_seconds: int, now: float | None = None) -> str:
    now = time.time() if now is None else now
    payload = _b64(json.dumps({"sub": user_id, "exp": int(now + ttl_seconds)}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def read_session_token(token: str, secret_key: str, now: float | None = None) -> str:
    try:
        payload, sig = token.split(".", 1)
        expected = _b64(hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, sig):
            raise ValueError("bad signature")
        data = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError) as exc:
        raise Unauthorized("Сессия недействительна, откройте приложение заново", code="invalid_session") from exc
    if (time.time() if now is None else now) > data.get("exp", 0):
        raise Unauthorized("Сессия истекла, откройте приложение заново", code="session_expired")
    return str(data["sub"])
