from helpers import make_robots, make_snapshot
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from orch_monitor.services.robots import RobotStatus
from orch_monitor.ui.tab_robots import RobotsTab, counter_text


def _tab(qtbot: QtBot, robots: list[RobotStatus] | None = None) -> RobotsTab:
    t = RobotsTab()
    qtbot.addWidget(t)
    t.apply_snapshot(make_snapshot(robots))
    return t


def test_TC_12_1_five_rows_and_columns(qtbot: QtBot) -> None:
    t = _tab(qtbot)
    assert t.proxy.rowCount() == 5
    cols = [t.model.headerData(i, Qt.Orientation.Horizontal) for i in range(6)]
    assert cols == ["Robot", "Maszyna", "Status", "Folder", "Ostatni heartbeat", "Typ"]


def test_TC_12_2_disconnected_on_top_red(qtbot: QtBot) -> None:
    t = _tab(qtbot)
    idx = t.proxy.index(0, 2)
    assert idx.data() == "Disconnected"
    assert idx.data(Qt.ItemDataRole.BackgroundRole).color().red() > 200
    busy = next(t.proxy.index(r, 2) for r in range(5) if t.proxy.index(r, 2).data() == "Busy")
    assert busy.data(Qt.ItemDataRole.BackgroundRole).color().blue() > 200


def test_TC_12_3_search_by_name(qtbot: QtBot) -> None:
    t = _tab(qtbot)
    t.search.setText("BOT0")
    assert t.proxy.rowCount() == 4  # bez AAA05
    t.search.setText("bot03")
    assert t.proxy.rowCount() == 1


def test_TC_12_4_filter_and_selection_survive_snapshot(qtbot: QtBot) -> None:
    t = _tab(qtbot)
    t.status_combo.setCurrentIndex(t.status_combo.findData("Available"))
    assert t.proxy.rowCount() == 3
    t.table.selectRow(1)
    sel = t.selected_robot_id()
    assert sel is not None
    t.apply_snapshot(make_snapshot())
    assert t.status_combo.currentData() == "Available"
    assert t.proxy.rowCount() == 3
    assert t.selected_robot_id() == sel


def test_TC_12_4_folder_filter(qtbot: QtBot) -> None:
    t = _tab(qtbot)
    t.folder_combo.setCurrentIndex(t.folder_combo.findData("Invoices"))
    assert t.proxy.rowCount() == 2
    t.apply_snapshot(make_snapshot())
    assert t.proxy.rowCount() == 2
    assert t.folder_combo.itemText(0) == "Wszystkie foldery"


def test_TC_12_5_counters(qtbot: QtBot) -> None:
    t = _tab(qtbot)
    assert t.counter.text() == "3 Available · 1 Busy · 1 Disconnected"
    assert counter_text({"Available": 2, "Busy": 0}) == "2 Available"
    assert len(make_robots()) == 5
