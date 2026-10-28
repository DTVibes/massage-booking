from datetime import datetime
from zoneinfo import ZoneInfo

MONTHS_GEN = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
WEEKDAYS_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def fmt_dt(dt: datetime, tz_name: str) -> str:
    local = dt.astimezone(ZoneInfo(tz_name))
    return f"{WEEKDAYS_SHORT[local.weekday()]}, {local.day} {MONTHS_GEN[local.month - 1]}, {local:%H:%M}"


def fmt_time(dt: datetime, tz_name: str) -> str:
    return dt.astimezone(ZoneInfo(tz_name)).strftime("%H:%M")


def fmt_price(price_minor: int, currency: str) -> str:
    if price_minor <= 0:
        return "по договорённости"
    major, minor = divmod(price_minor, 100)
    amount = f"{major:,}".replace(",", " ") + (f",{minor:02d}" if minor else "")
    symbol = {"RUB": "₽", "USD": "$", "EUR": "€", "KZT": "₸", "BYN": "Br", "UAH": "₴"}.get(currency, currency)
    return f"{amount} {symbol}"
