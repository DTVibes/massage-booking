"""Обработчик очереди уведомлений (отдельный процесс: python -m app.worker).

Задачи хранятся в PostgreSQL (notification_jobs), поэтому перезапуск не теряет напоминания.
Каждая задача обрабатывается в отдельной транзакции с блокировкой FOR UPDATE SKIP LOCKED,
что позволяет безопасно запускать несколько экземпляров обработчика.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import timeutil
from app.config import get_settings
from app.db import SessionLocal
from app.models import Appointment, AppointmentStatus, AppSettings, NotificationJob, NotificationStatus, User
from app.services.formatting import fmt_dt, fmt_price, fmt_time
from app.services.settings_service import get_app_settings

log = logging.getLogger("worker")

MAX_ATTEMPTS = 5
SEND_INTERVAL_SECONDS = 0.05  # ~20 сообщений в секунду — ниже лимита Bot API (30/с)


class SendError(Exception):
    pass


class PermanentSendError(SendError):
    """Повторять бессмысленно (бот заблокирован, чат не найден, некорректный запрос)."""

    def __init__(self, message: str, bot_blocked: bool = False):
        super().__init__(message)
        self.bot_blocked = bot_blocked


class RetryAfterError(SendError):
    def __init__(self, retry_after: float):
        super().__init__(f"Flood control: повтор через {retry_after} с")
        self.retry_after = retry_after


# (chat_id, текст, показывать ли кнопку открытия приложения)
Sender = Callable[[int, str, bool], Awaitable[None]]


def _visit_block(appt: Appointment, settings: AppSettings) -> str:
    lines = [
        f"💆 {appt.service_name_snapshot}",
        f"📅 {fmt_dt(appt.starts_at, settings.timezone)}–{fmt_time(appt.ends_at, settings.timezone)}",
    ]
    if settings.address:
        lines.append(f"📍 {settings.address}")
    return "\n".join(lines)


def render(job: NotificationJob, appt: Appointment, client: User, settings: AppSettings) -> str:
    t = job.notification_type
    visit = _visit_block(appt, settings)
    payload = job.payload or {}
    if t == "client_created":
        return (f"✅ Вы записаны!\n\n{visit}\n💳 {fmt_price(appt.price_minor_snapshot, appt.currency_snapshot)}\n\n"
                f"Отменить или перенести запись можно в приложении не позднее чем за "
                f"{settings.cancel_min_hours} ч до визита.")
    if t == "client_cancelled":
        reason = f"\nПричина: {payload['reason']}" if payload.get("reason") else ""
        who = "массажистом" if appt.status == AppointmentStatus.cancelled_by_admin else "вами"
        return f"❌ Запись отменена {who}.\n\n{visit}{reason}"
    if t == "client_rescheduled":
        old = datetime.fromisoformat(payload["old_starts_at"]) if payload.get("old_starts_at") else None
        was = f"\nБыло: {fmt_dt(old, settings.timezone)}" if old else ""
        return f"🔄 Запись перенесена.\n\n{visit}{was}"
    if t.startswith("reminder_"):
        hours = t.removeprefix("reminder_").removesuffix("h")
        when = "завтра" if hours == "24" else f"через {hours} ч"
        return f"⏰ Напоминание: {when} у вас визит.\n\n{visit}"
    if t.startswith("admin_"):
        title = {"admin_created": "🆕 Новая запись", "admin_cancelled": "❌ Клиент отменил запись",
                 "admin_rescheduled": "🔄 Клиент перенёс запись"}.get(t, "Событие")
        extra = ""
        if t == "admin_rescheduled" and payload.get("old_starts_at"):
            extra = f"\nБыло: {fmt_dt(datetime.fromisoformat(payload['old_starts_at']), settings.timezone)}"
        return (f"{title}\n\n👤 {client.name}\n📞 {client.phone or 'не указан'}\n"
                f"💆 {appt.service_name_snapshot}\n"
                f"📅 {fmt_dt(appt.starts_at, settings.timezone)}–{fmt_time(appt.ends_at, settings.timezone)}{extra}")
    return f"Уведомление по записи на {fmt_dt(appt.starts_at, settings.timezone)}"


def _skip_reason(db: Session, job: NotificationJob, appt: Appointment | None, client: User | None,
                 now: datetime) -> str | None:
    if appt is None or client is None:
        return "Запись не найдена"
    if job.notification_type.startswith("reminder_"):
        if appt.status != AppointmentStatus.booked:
            return "Запись не активна"
        if (job.payload or {}).get("starts_at") != appt.starts_at.isoformat():
            return "Время записи изменилось"
        if appt.starts_at <= now:
            return "Визит уже начался"
        if not client.notifications_enabled:
            return "Клиент отключил напоминания"
    recipient = db.scalar(select(User).where(User.telegram_id == job.recipient_telegram_id))
    if recipient is not None and not recipient.can_receive_messages:
        return "Пользователь не запускал бота или заблокировал его"
    return None


def _claim_next(db: Session, now: datetime) -> NotificationJob | None:
    return db.scalar(
        select(NotificationJob)
        .where(NotificationJob.status == NotificationStatus.pending, NotificationJob.scheduled_at <= now)
        .order_by(NotificationJob.scheduled_at, NotificationJob.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )


async def process_job(db: Session, job: NotificationJob, sender: Sender, now: datetime) -> None:
    appt = db.get(Appointment, job.appointment_id) if job.appointment_id else None
    client = db.get(User, appt.client_id) if appt else None
    reason = _skip_reason(db, job, appt, client, now)
    if reason:
        job.status = NotificationStatus.skipped
        job.last_error = reason
        return
    text = render(job, appt, client, get_app_settings(db))
    job.attempts += 1
    try:
        await sender(job.recipient_telegram_id, text, not job.notification_type.startswith("admin_"))
    except RetryAfterError as exc:
        job.attempts -= 1  # flood control не считается неудачной попыткой
        job.scheduled_at = now + timedelta(seconds=exc.retry_after + 1)
        job.last_error = str(exc)
    except PermanentSendError as exc:
        job.status = NotificationStatus.failed
        job.last_error = str(exc)[:1000]
        if exc.bot_blocked:
            recipient = db.scalar(select(User).where(User.telegram_id == job.recipient_telegram_id))
            if recipient:
                recipient.bot_blocked = True
    except Exception as exc:  # временная ошибка: сеть, 5xx и т.п.
        job.last_error = f"{type(exc).__name__}: {exc}"[:1000]
        if job.attempts >= MAX_ATTEMPTS:
            job.status = NotificationStatus.failed
        else:
            job.scheduled_at = now + timedelta(seconds=30 * 2 ** (job.attempts - 1))
    else:
        job.status = NotificationStatus.sent
        job.sent_at = now
        job.last_error = None


async def process_due_jobs(sender: Sender, limit: int = 100, throttle: float = 0.0) -> int:
    processed = 0
    while processed < limit:
        with SessionLocal() as db:
            now = timeutil.now_utc()
            job = _claim_next(db, now)
            if job is None:
                break
            await process_job(db, job, sender, now)
            db.commit()  # ошибки отправки фиксируются в задаче и не влияют на саму запись
        processed += 1
        if throttle:
            await asyncio.sleep(throttle)
    return processed


def make_telegram_sender(bot) -> Sender:
    from aiogram.exceptions import (
        TelegramBadRequest,
        TelegramForbiddenError,
        TelegramNotFound,
        TelegramRetryAfter,
    )
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    url = get_settings().frontend_url

    async def send(chat_id: int, text: str, with_button: bool) -> None:
        markup = None
        if with_button and url.startswith("https://"):
            markup = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Открыть приложение", web_app=WebAppInfo(url=url))]])
        try:
            await bot.send_message(chat_id, text, reply_markup=markup)
        except TelegramRetryAfter as exc:
            raise RetryAfterError(exc.retry_after) from exc
        except TelegramForbiddenError as exc:
            raise PermanentSendError(f"Бот заблокирован пользователем: {exc.message}", bot_blocked=True) from exc
        except (TelegramBadRequest, TelegramNotFound) as exc:
            raise PermanentSendError(f"Telegram отклонил сообщение: {exc.message}") from exc

    return send


async def run_forever(poll_interval: float = 5.0) -> None:
    from aiogram import Bot

    cfg = get_settings()
    if not cfg.bot_token:
        raise SystemExit("BOT_TOKEN не задан")
    bot = Bot(cfg.bot_token)
    sender = make_telegram_sender(bot)
    log.info("Обработчик уведомлений запущен")
    try:
        while True:
            try:
                n = await process_due_jobs(sender, throttle=SEND_INTERVAL_SECONDS)
                if n:
                    log.info("Обработано задач: %s", n)
            except Exception:
                log.exception("Ошибка обработки очереди уведомлений")
            await asyncio.sleep(poll_interval)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(level=get_settings().log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run_forever())
