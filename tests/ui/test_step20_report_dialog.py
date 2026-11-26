import threading
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from pytestqt.qtbot import QtBot

from orch_monitor.clock import WARSAW
from orch_monitor.reports.builder import ReportCancelled
from orch_monitor.reports.model import (
    DayStats,
    ErrorEntry,
    ProcessStats,
    QueueStats,
    Report,
    Summary,
)
from orch_monitor.reports.periods import Period
from orch_monitor.ui.report_dialog import ReportDialog

NOW = datetime(2026, 11, 26, 11, 0, tzinfo=UTC)


def make_report(period: Period, ok: bool = False) -> Report:
    return Report(
        period=period,
        folders=["Finance"],
        summary=Summary(ok, 5, 10, 0 if ok else 1, 2, 0 if ok else 1),
        processes=[ProcessStats("Raport", 5, 4, 1, 0, timedelta(minutes=20))],
        queues=[QueueStats("Faktury_IN", "Finance", 8, 1, 1, 80.0)],
        days=[DayStats(period.days[0], 1, 1, 0, False)],
        errors=[
            ErrorEntry(
                "Faulted",
                datetime(2026, 11, 25, 10, 10, tzinfo=WARSAW),
                "Raport",
                "Finance",
                "Boom",
            )  # fmt: skip
        ],
    )


def ok_build(period: Period, folders: list[str], progress: Any, cancelled: Any) -> Report:
    progress(1, 2)
    progress(2, 2)
    return make_report(period)


def dialog(qtbot: QtBot, build: Any = ok_build, sync: bool = True) -> ReportDialog:
    d = ReportDialog(build, ["Finance"], ["Finance", "Invoices"], lambda: NOW, synchronous=sync)
    qtbot.addWidget(d)
    d.show()
    return d


def set_date(d: ReportDialog, day: date, to: bool = False) -> None:
    from PySide6.QtCore import QDate

    (d.to_edit if to else d.from_edit).setDate(QDate(day.year, day.month, day.day))


def test_TC_20_1_week_range_shown(qtbot: QtBot) -> None:
    d = dialog(qtbot)
    d.mode_combo.setCurrentText("Tydzień")
    set_date(d, date(2026, 11, 26))
    assert d.range_label.text() == "23.11.2026 – 29.11.2026"
    assert d.selected_folders() == ["Finance"]
    assert d.from_edit.calendarPopup()


def test_TC_20_2_generate_preview(qtbot: QtBot) -> None:
    d = dialog(qtbot)
    d.generate_button.click()
    assert d.verdict_label.text() == "Z błędami"
    assert "b71c1c" in d.verdict_label.styleSheet()
    assert [d.preview.tabText(i) for i in range(5)] == [
        "Podsumowanie", "Procesy", "Kolejki", "Dni", "Błędy"]  # fmt: skip
    assert d.tables["Procesy"].item(0, 0).text() == "Raport"
    assert d.tables["Błędy"].rowCount() == 1
    assert d.save_csv_button.isEnabled() and d.save_xlsx_button.isEnabled()


def test_TC_20_2_ok_verdict_green(qtbot: QtBot) -> None:
    d = dialog(qtbot, lambda p, f, pr, c: make_report(p, ok=True))
    d.generate_button.click()
    assert d.verdict_label.text() == "Bez błędów" and "1b5e20" in d.verdict_label.styleSheet()


def test_TC_20_3_progress_visible_and_ui_responsive(qtbot: QtBot) -> None:
    release = threading.Event()
    started = threading.Event()

    def slow(period: Period, folders: list[str], progress: Any, cancelled: Any) -> Report:
        started.set()
        progress(1, 3)
        release.wait(10)  # symuluje 5 s pracy
        return make_report(period)

    d = dialog(qtbot, slow, sync=False)
    d.generate_button.click()
    assert started.wait(5)
    qtbot.waitUntil(lambda: d.progress.value() == 1, timeout=3000)
    assert d.progress.isVisible() and d.cancel_button.isVisible()
    assert not d.generate_button.isEnabled()
    # okno reaguje: zdarzenia sa przetwarzane, zmiana kontrolek dziala w trakcie generowania
    d.mode_combo.setCurrentText("Miesiąc")
    qtbot.wait(50)
    assert d.range_label.text() == "01.11.2026 – 30.11.2026"
    release.set()
    qtbot.waitUntil(lambda: d.report is not None, timeout=5000)
    assert not d.progress.isVisible() and d.generate_button.isEnabled()


def test_TC_20_4_cancel(qtbot: QtBot) -> None:
    started = threading.Event()

    def cancellable(period: Period, folders: list[str], progress: Any, cancelled: Any) -> Report:
        started.set()
        while not cancelled():
            threading.Event().wait(0.01)
        raise ReportCancelled("Raport anulowany.")

    d = dialog(qtbot, cancellable, sync=False)
    d.generate_button.click()
    assert started.wait(5)
    d.cancel_button.click()
    qtbot.waitUntil(lambda: d.status_label.text() == "Anulowano", timeout=5000)
    assert d.report is None and not d.progress.isVisible()
    assert d.generate_button.isEnabled()
    assert "Nie udało się" not in d.status_label.text()


def test_TC_20_5_invalid_range(qtbot: QtBot) -> None:
    d = dialog(qtbot)
    d.mode_combo.setCurrentText("Zakres")
    set_date(d, date(2026, 11, 20))
    set_date(d, date(2026, 11, 10), to=True)
    assert not d.generate_button.isEnabled()
    assert "wcześniejsza" in d.status_label.text()
    set_date(d, date(2026, 11, 25), to=True)
    assert d.generate_button.isEnabled()
    assert d.range_label.text() == "20.11.2026 – 25.11.2026"


def test_TC_20_6_api_error_then_retry(qtbot: QtBot) -> None:
    calls = {"n": 0}

    def flaky(period: Period, folders: list[str], progress: Any, cancelled: Any) -> Report:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("HTTP 500 dla Jobs")
        return make_report(period)

    d = dialog(qtbot, flaky)
    d.generate_button.click()
    assert "HTTP 500 dla Jobs" in d.status_label.text()
    assert d.generate_button.isEnabled() and d.report is None
    d.generate_button.click()
    assert d.report is not None


def test_save_csv_and_xlsx(qtbot: QtBot, tmp_path: Path) -> None:
    d = dialog(qtbot)
    d.save_csv(str(tmp_path / "x.zip"))
    assert "Najpierw" in d.status_label.text()
    d.generate_button.click()
    d.save_csv(str(tmp_path / "r.zip"))
    d.save_xlsx(str(tmp_path / "r.xlsx"))
    assert len(zipfile.ZipFile(tmp_path / "r.zip").namelist()) == 5
    assert load_workbook(tmp_path / "r.xlsx").sheetnames == [
        "Podsumowanie", "Procesy", "Kolejki", "Dni", "Błędy"]  # fmt: skip
    d.save_xlsx(str(tmp_path / "brak" / "r.xlsx"))
    assert "Nie udało się zapisać" in d.status_label.text()
