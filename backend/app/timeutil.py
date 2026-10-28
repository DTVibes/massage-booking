from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def now_utc() -> datetime:
    """Единая точка получения текущего времени (подменяется в тестах)."""
    return datetime.now(UTC)


def tz(name: str) -> ZoneInfo:
    return ZoneInfo(name)
