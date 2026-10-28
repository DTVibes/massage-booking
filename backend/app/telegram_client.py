from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import PRODUCTION, TelegramAPIServer

from app.config import get_settings


def make_bot() -> Bot:
    """Создаёт Bot с учётом TELEGRAM_PROXY и TELEGRAM_API_URL."""
    cfg = get_settings()
    if not cfg.bot_token:
        raise SystemExit("BOT_TOKEN не задан")
    api = TelegramAPIServer.from_base(cfg.telegram_api_url.rstrip("/")) if cfg.telegram_api_url else PRODUCTION
    session = AiohttpSession(proxy=cfg.telegram_proxy or None, api=api)
    return Bot(cfg.bot_token, session=session)
