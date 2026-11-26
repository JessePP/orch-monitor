"""Wspolne pomocnicze funkcje serwisow danych (bez Qt)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from orch_monitor.clock import to_local

_FRACTION = re.compile(r"\.(\d+)")


def parse_dt(value: Any) -> datetime | None:
    """Parsuje czas z API (ISO, zwykle UTC z 'Z') do aware datetime w Europe/Warsaw."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    text = _FRACTION.sub(lambda m: "." + m.group(1)[:6].ljust(6, "0"), text, count=1)
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return to_local(dt)


def iso_z(dt: datetime) -> str:
    """Format czasu do filtra OData: 2026-11-26T12:00:00Z (bez cudzyslowow)."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
