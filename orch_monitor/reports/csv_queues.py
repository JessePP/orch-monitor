"""Eksport tabeli kolejek (zakladka 3) do CSV: UTF-8 z BOM, separator ';'. Bez Qt."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from orch_monitor.clock import to_local
from orch_monitor.services.queues import QueueRow

HEADER = [
    "Kolejka",
    "Folder",
    "Sukcesy",
    "AE",
    "BE",
    "% sukcesu",
    "vs wczoraj",
    "W toku",
    "Nowe",
    "Ostatnie przetworzenie",
]


def default_filename(day: date) -> str:
    return f"kolejki_{day.isoformat()}.csv"


def format_pct(value: float | None) -> str:
    return "–" if value is None else f"{value:.1f}%"


def format_change(value: float | None) -> str:
    if value is None:
        return ""
    rounded = round(value)
    if rounded > 0:
        return f"▲ {rounded} pp"
    if rounded < 0:
        return f"▼ {-rounded} pp"
    return "= 0 pp"


def format_last(row: QueueRow) -> str:
    if row.last_processed is None:
        return ""
    return to_local(row.last_processed).strftime("%H:%M:%S")


def export_queues_csv(rows: Sequence[QueueRow], path: Path | str) -> None:
    with Path(path).open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(HEADER)
        for r in rows:
            writer.writerow(
                [
                    r.name,
                    r.folder,
                    r.successful,
                    r.ae,
                    r.be,
                    format_pct(r.success_pct),
                    format_change(r.change_pp),
                    r.in_progress,
                    r.new,
                    format_last(r),
                ]
            )
