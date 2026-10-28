from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация из переменных окружения. Секреты хранятся только здесь, не в БД."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str = ""
    admin_telegram_ids: Annotated[list[int], NoDecode] = []
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/massage"
    app_base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"
    timezone: str = "Europe/Moscow"
    secret_key: str = "change-me"
    # Если с сервера нет прямого доступа к api.telegram.org: прокси (socks5://… или http://…)
    # или адрес собственного зеркала / локального Bot API сервера.
    telegram_proxy: str = ""
    telegram_api_url: str = ""

    session_ttl_seconds: int = 24 * 3600
    init_data_max_age_seconds: int = 24 * 3600
    rate_limit_enabled: bool = True
    default_phone_region: str = "RU"
    log_level: str = "INFO"

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def _parse_ids(cls, v):
        if isinstance(v, str):
            return [int(x) for x in v.replace(";", ",").split(",") if x.strip()]
        if isinstance(v, int):
            return [v]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
