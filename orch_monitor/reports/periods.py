"""Okresy raportow: doba, tydzien (pon-niedz), miesiac i zakres wlasny w Europe/Warsaw."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from orch_monitor.clock import day_window


@dataclass(frozen=True)
class Period:
    start_date: date
    end_date: date  # wlacznie
    start_utc: datetime
    end_utc: datetime  # poczatek doby po end_date (wylacznie)
    days: list[date]


def period_custom(d_from: date, d_to: date) -> Period:
    if d_to < d_from:
        raise ValueError("Data końcowa jest wcześniejsza niż początkowa.")
    days = [d_from + timedelta(days=i) for i in range((d_to - d_from).days + 1)]
    return Period(d_from, d_to, day_window(d_from)[0], day_window(d_to)[1], days)


def period_day(d: date) -> Period:
    return period_custom(d, d)


def period_week(d: date) -> Period:
    monday = d - timedelta(days=d.weekday())
    return period_custom(monday, monday + timedelta(days=6))


def period_month(d: date) -> Period:
    last = calendar.monthrange(d.year, d.month)[1]
    return period_custom(d.replace(day=1), d.replace(day=last))
