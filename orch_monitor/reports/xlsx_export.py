"""Eksport raportu do Excela (openpyxl)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet

from orch_monitor.reports.csv_export import report_filename, verdict_text
from orch_monitor.reports.model import Report

__all__ = ["export_report_xlsx", "report_filename"]

RED = PatternFill("solid", start_color="FFC7CE", end_color="FFC7CE")
GREEN = PatternFill("solid", start_color="C6EFCE", end_color="C6EFCE")
DATE_FMT = "yyyy-mm-dd"
DATETIME_FMT = "yyyy-mm-dd hh:mm:ss"
DURATION_FMT = "[h]:mm:ss"
PCT_FMT = "0.0%"


def _naive(dt: datetime | None) -> datetime | None:
    """Excel nie obsluguje stref: czas lokalny PL bez tzinfo."""
    return dt.replace(tzinfo=None) if dt else None


def _header(ws: Worksheet, names: Sequence[str]) -> None:
    ws.append(list(names))
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for i, name in enumerate(names, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = max(14, len(name) + 4)


def _fmt(ws: Worksheet, col: int, fmt: str) -> None:
    for row in ws.iter_rows(min_row=2, min_col=col, max_col=col):
        row[0].number_format = fmt


def export_report_xlsx(report: Report, path: Path | str) -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Podsumowanie"
    s, p = report.summary, report.period
    _header(ws, ["Pozycja", "Wartość"])
    rows: list[list[Any]] = [
        ["Okres od", p.start_date],
        ["Okres do", p.end_date],
        ["Foldery", ", ".join(report.folders)],
        ["Werdykt", verdict_text(s.verdict_ok)],
        ["Uruchomienia procesów", s.jobs_total],
        ["Elementy kolejek", s.queue_items_total],
        ["AE", s.ae],
        ["BE", s.be],
        ["Faulted", s.faulted],
    ]
    for r in rows:
        ws.append(r)
    ws["B2"].number_format = ws["B3"].number_format = DATE_FMT
    ws["B5"].fill = GREEN if s.verdict_ok else RED
    ws["B5"].font = Font(bold=True)

    ws = wb.create_sheet("Procesy")
    _header(ws, ["Proces", "Uruchomienia", "Successful", "Faulted", "Stopped", "Średni czas"])
    for x in report.processes:
        ws.append([x.process, x.runs, x.successful, x.faulted, x.stopped, x.avg_duration])
    _fmt(ws, 6, DURATION_FMT)

    ws = wb.create_sheet("Kolejki")
    _header(ws, ["Kolejka", "Folder", "Sukcesy", "AE", "BE", "% sukcesu"])
    for q in report.queues:
        pct = None if q.success_pct is None else q.success_pct / 100.0
        ws.append([q.name, q.folder, q.successful, q.ae, q.be, pct])
    _fmt(ws, 6, PCT_FMT)

    ws = wb.create_sheet("Dni")
    _header(ws, ["Dzień", "Faulted", "AE", "BE", "Werdykt"])
    for d in report.days:
        ws.append([d.day, d.faulted, d.ae, d.be, verdict_text(d.verdict_ok)])
        ws.cell(row=ws.max_row, column=5).fill = GREEN if d.verdict_ok else RED
    _fmt(ws, 1, DATE_FMT)

    ws = wb.create_sheet("Błędy")
    _header(ws, ["Rodzaj", "Czas", "Proces/kolejka", "Folder", "Komunikat"])
    for e in report.errors:
        ws.append([e.kind, _naive(e.when), e.process_or_queue, e.folder, e.message])
    _fmt(ws, 2, DATETIME_FMT)

    wb.save(Path(path))
