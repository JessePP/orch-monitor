"""Model danych raportu."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal

from orch_monitor.reports.periods import Period


@dataclass(frozen=True)
class Summary:
    verdict_ok: bool
    jobs_total: int
    queue_items_total: int
    ae: int
    be: int
    faulted: int


@dataclass(frozen=True)
class ProcessStats:
    process: str
    runs: int
    successful: int
    faulted: int
    stopped: int
    avg_duration: timedelta | None


@dataclass(frozen=True)
class QueueStats:
    name: str
    folder: str
    successful: int
    ae: int
    be: int
    success_pct: float | None


@dataclass(frozen=True)
class DayStats:
    day: date
    faulted: int
    ae: int
    be: int
    verdict_ok: bool


@dataclass(frozen=True)
class ErrorEntry:
    kind: Literal["Faulted", "AE"]
    when: datetime | None
    process_or_queue: str
    folder: str
    message: str


@dataclass(frozen=True)
class Report:
    period: Period
    folders: list[str]
    summary: Summary
    processes: list[ProcessStats] = field(default_factory=list)
    queues: list[QueueStats] = field(default_factory=list)
    days: list[DayStats] = field(default_factory=list)
    errors: list[ErrorEntry] = field(default_factory=list)
