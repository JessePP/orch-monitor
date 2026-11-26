"""Eksport raportu do ZIP z 5 plikami CSV (UTF-8 z BOM, separator ';')."""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, TextIO

from orch_monitor.reports.model import Report
from orch_monitor.reports.periods import Period

DELIMITER = ";"
VERDICT_OK = "Bez błędów"
VERDICT_BAD = "Z błędami"


def verdict_text(ok: bool) -> str:
    return VERDICT_OK if ok else VERDICT_BAD


def report_filename(period: Period, ext: str) -> str:
    """np. raport_2026-11-23_2026-11-29.xlsx"""
    return f"raport_{period.start_date.isoformat()}_{period.end_date.isoformat()}.{ext.lstrip('.')}"


def write_csv(
    rows: Iterable[Sequence[Any]], header: Sequence[str], target: TextIO | Path | str
) -> None:
    """Zapisuje CSV (separator ';'). Dla sciezki: UTF-8 z BOM; dla obiektu pliku tekstowego
    wywolujacy odpowiada za kodowanie."""
    if isinstance(target, (str, Path)):
        with Path(target).open("w", encoding="utf-8-sig", newline="") as fh:
            write_csv(rows, header, fh)
        return
    writer = csv.writer(target, delimiter=DELIMITER, lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)


def _dt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def _dur(value: timedelta | None) -> str:
    if value is None:
        return ""
    secs = int(value.total_seconds())
    return f"{secs // 3600}:{secs % 3600 // 60:02d}:{secs % 60:02d}"


def _pct(value: float | None) -> str:
    return "" if value is None else f"{value:.1f}".replace(".", ",")


def report_tables(report: Report) -> dict[str, tuple[list[str], list[list[Any]]]]:
    """Nazwa pliku CSV -> (naglowek, wiersze)."""
    s = report.summary
    p = report.period
    summary: list[list[Any]] = [
        ["Okres od", p.start_date.isoformat()],
        ["Okres do", p.end_date.isoformat()],
        ["Foldery", ", ".join(report.folders)],
        ["Werdykt", verdict_text(s.verdict_ok)],
        ["Uruchomienia procesów", s.jobs_total],
        ["Elementy kolejek", s.queue_items_total],
        ["AE", s.ae],
        ["BE", s.be],
        ["Faulted", s.faulted],
    ]
    return {
        "podsumowanie.csv": (["Pozycja", "Wartość"], summary),
        "procesy.csv": (
            ["Proces", "Uruchomienia", "Successful", "Faulted", "Stopped", "Średni czas"],
            [
                [x.process, x.runs, x.successful, x.faulted, x.stopped, _dur(x.avg_duration)]
                for x in report.processes
            ],
        ),
        "kolejki.csv": (
            ["Kolejka", "Folder", "Sukcesy", "AE", "BE", "% sukcesu"],
            [
                [q.name, q.folder, q.successful, q.ae, q.be, _pct(q.success_pct)]
                for q in report.queues
            ],
        ),
        "dni.csv": (
            ["Dzień", "Faulted", "AE", "BE", "Werdykt"],
            [
                [d.day.isoformat(), d.faulted, d.ae, d.be, verdict_text(d.verdict_ok)]
                for d in report.days
            ],
        ),
        "bledy.csv": (
            ["Rodzaj", "Czas", "Proces/kolejka", "Folder", "Komunikat"],
            [[e.kind, _dt(e.when), e.process_or_queue, e.folder, e.message] for e in report.errors],
        ),
    }


def export_report_csv_zip(report: Report, path: Path | str) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, (header, rows) in report_tables(report).items():
            buf = io.StringIO()
            write_csv(rows, header, buf)
            zf.writestr(name, buf.getvalue().encode("utf-8-sig"))
