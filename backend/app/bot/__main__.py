"""Telegram-бот (отдельный процесс: python -m app.bot)."""

import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)
from sqlalchemy import select

from app import timeutil
from app.config import get_settings
from app.db import SessionLocal
from app.models import Appointment, AppointmentStatus, User, UserRole
from app.services.formatting import fmt_dt, fmt_time
from app.services.settings_service import get_app_settings
from app.telegram_client import make_bot

log = logging.getLogger("bot")
router = Router()


def app_keyboard(text: str = "💆 Записаться на массаж") -> InlineKeyboardMarkup | None:
    url = get_settings().frontend_url
    if not url.startswith("https://"):
        return None  # Telegram принимает Mini App только по HTTPS
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))]])


def touch_user(message: Message) -> User:
    """Отмечает, что пользователь запускал бота — значит, ему можно отправлять уведомления."""
    tg = message.from_user
    cfg = get_settings()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == tg.id))
        if user is None:
            user = User(telegram_id=tg.id, name=tg.full_name[:200] or "Клиент", username=tg.username,
                        role=UserRole.admin if tg.id in cfg.admin_telegram_ids else UserRole.client)
            db.add(user)
        if user.bot_started_at is None:
            user.bot_started_at = timeutil.now_utc()
        user.bot_blocked = False
        db.commit()
        return user


@router.message(CommandStart())
async def cmd_start(message: Message):
    touch_user(message)
    with SessionLocal() as db:
        s = get_app_settings(db)
        title = s.studio_name or "Массаж"
        greeting = s.welcome_text or "Здесь можно записаться на массаж, выбрав удобные дату и время."
    kb = app_keyboard()
    tail = "" if kb else "\n\n(Mini App ещё не настроено: FRONTEND_URL должен начинаться с https://)"
    await message.answer(f"Здравствуйте! Это {title}.\n\n{greeting}{tail}", reply_markup=kb)


@router.message(Command("book"))
async def cmd_book(message: Message):
    touch_user(message)
    await message.answer("Откройте приложение, чтобы выбрать услугу, дату и время:", reply_markup=app_keyboard())


@router.message(Command("mybookings"))
async def cmd_mybookings(message: Message):
    user = touch_user(message)
    with SessionLocal() as db:
        s = get_app_settings(db)
        appts = db.scalars(
            select(Appointment)
            .where(Appointment.client_id == user.id, Appointment.status == AppointmentStatus.booked,
                   Appointment.starts_at > timeutil.now_utc())
            .order_by(Appointment.starts_at).limit(5)
        ).all()
        if not appts:
            text = "У вас нет предстоящих записей."
        else:
            lines = [f"• {fmt_dt(a.starts_at, s.timezone)}–{fmt_time(a.ends_at, s.timezone)}, {a.service_name_snapshot}"
                     for a in appts]
            text = "Ваши ближайшие записи:\n\n" + "\n".join(lines)
    await message.answer(text, reply_markup=app_keyboard("Управлять записями"))


@router.message(Command("help"))
async def cmd_help(message: Message):
    touch_user(message)
    with SessionLocal() as db:
        s = get_app_settings(db)
        contacts = [x for x in (
            f"📍 {s.address}" if s.address else "",
            f"📞 {s.contact_phone}" if s.contact_phone else "",
            f"✈️ {s.contact_telegram}" if s.contact_telegram else "",
        ) if x]
        cancel_hours = s.cancel_min_hours
    text = (
        "Как записаться:\n"
        "1. Нажмите «Записаться на массаж» или /book.\n"
        "2. Выберите услугу, дату и свободное время.\n"
        "3. Укажите телефон и подтвердите запись.\n\n"
        f"Отменить или перенести запись можно в приложении не позднее чем за {cancel_hours} ч до визита.\n\n"
        "Команды: /book — записаться, /mybookings — мои записи, /help — помощь."
    )
    if contacts:
        text += "\n\nКонтакты:\n" + "\n".join(contacts)
    await message.answer(text, reply_markup=app_keyboard())


@router.my_chat_member(F.chat.type == "private")
async def on_member_update(event: ChatMemberUpdated):
    blocked = event.new_chat_member.status in ("kicked", "left")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == event.from_user.id))
        if user:
            user.bot_blocked = blocked
            db.commit()


async def main() -> None:
    cfg = get_settings()
    bot = make_bot()
    dp = Dispatcher()
    dp.include_router(router)
    try:
        await setup_and_poll(bot, dp, cfg)
    finally:
        await bot.session.close()


async def setup_and_poll(bot: Bot, dp: Dispatcher, cfg) -> None:
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать"),
        BotCommand(command="book", description="Записаться"),
        BotCommand(command="mybookings", description="Мои записи"),
        BotCommand(command="help", description="Помощь и контакты"),
    ])
    if cfg.frontend_url.startswith("https://"):
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Записаться", web_app=WebAppInfo(url=cfg.frontend_url)))
    log.info("Бот запущен (long polling)")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    logging.basicConfig(level=get_settings().log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(main())
