from datetime import UTC, datetime, timedelta

from helpers import NOW, make_running, make_snapshot
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from orch_monitor.clock import to_local
from orch_monitor.services.jobs import PendingJob
from orch_monitor.ui.tab_jobs import JobsTab, format_duration


def _pending() -> PendingJob:
    return PendingJob(9, "ProcP", to_local(NOW - timedelta(minutes=5)), timedelta(minutes=5), "F")


class Clk:
    def __init__(self) -> None:
        self.now: datetime = NOW

    def __call__(self) -> datetime:
        return self.now


def test_TC_13_1_counts_and_tables(qtbot: QtBot) -> None:
    t = JobsTab(Clk())
    qtbot.addWidget(t)
    t.apply_snapshot(
        make_snapshot(running=[make_running(jid=1), make_running(jid=2)], pending=[_pending()])
    )
    assert t.running_table.rowCount() == 2
    assert t.pending_table.rowCount() == 1
    assert t.counter.text() == "2 działa · 1 czeka"
    assert t.running_table.horizontalHeaderItem(4).text() == "Czas trwania"
    assert t.pending_header.text() == "Oczekujące (Pending)"
    assert t.pending_table.item(0, 2).text() == "0:05:00"


def test_TC_13_2_long_job_highlighted(qtbot: QtBot) -> None:
    t = JobsTab(Clk())
    qtbot.addWidget(t)
    t.apply_snapshot(make_snapshot(running=[make_running(True, jid=1), make_running(False, jid=2)]))
    long_bg = t.running_table.item(0, 0).background().color()
    normal_bg = t.running_table.item(1, 0).background()
    assert long_bg.red() > 240 and long_bg.blue() < 220
    assert normal_bg.style() == Qt.BrushStyle.NoBrush


def test_TC_13_3_duration_ticks_every_second(qtbot: QtBot) -> None:
    clk = Clk()
    t = JobsTab(clk)
    qtbot.addWidget(t)
    t.apply_snapshot(make_snapshot(running=[make_running(start_ago_s=60)]))
    assert t.running_table.item(0, 4).text() == "0:01:00"
    clk.now = NOW + timedelta(seconds=1)
    t.tick()
    assert t.running_table.item(0, 4).text() == "0:01:01"
    assert t._timer.interval() == 1000
    assert format_duration(timedelta(hours=2, minutes=3, seconds=4)) == "2:03:04"
    assert datetime.now(UTC)


def test_TC_13_4_empty_message(qtbot: QtBot) -> None:
    t = JobsTab(Clk())
    qtbot.addWidget(t)
    t.apply_snapshot(make_snapshot())
    assert t.stack.currentWidget() is t.empty_label
    assert t.empty_label.text() == "Nic teraz nie działa"
    t.apply_snapshot(make_snapshot(running=[make_running()]))
    assert t.stack.currentWidget() is not t.empty_label
