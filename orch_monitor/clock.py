"""Czas: wstrzykiwany zegar i granice doby w Europe/Warsaw."""

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

Clock = Callable[[], datetime]

WARSAW = ZoneInfo("Europe/Warsaw")


def utc_now() -> datetime:
    """Biezacy czas jako aware UTC."""
    return datetime.now(UTC)


def to_local(dt: datetime) -> datetime:
    """Konwertuje aware datetime do Europe/Warsaw (naiwne traktuje jako UTC)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(WARSAW)


def day_window(d: date) -> tuple[datetime, datetime]:
    """Poczatek doby d (00:00 Warszawa) i poczatek nastepnej doby, oba w UTC."""
    start = datetime.combine(d, time.min, tzinfo=WARSAW)
    end = datetime.combine(d + timedelta(days=1), time.min, tzinfo=WARSAW)
    return start.astimezone(UTC), end.astimezone(UTC)
