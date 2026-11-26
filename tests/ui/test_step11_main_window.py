from helpers import NOW, make_snapshot
from PySide6.QtCore import QEvent
from PySide6.QtGui import QCloseEvent
from pytestqt.qtbot import QtBot

from orch_monitor.ui.main_window import STALE_TEXT, TAB_NAMES, MainWindow
from orch_monitor.ui.tray import TrayIcon


def _win(qtbot: QtBot) -> MainWindow:
    w = MainWindow(clock=lambda: NOW)
    qtbot.addWidget(w)
    return w


def test_TC_11_1_three_tabs_in_order(qtbot: QtBot) -> None:
    w = _win(qtbot)
    assert [w.tabs.tabText(i) for i in range(w.tabs.count())] == ["Roboty", "Działające", "Kolejki"]
    assert TAB_NAMES == ("Roboty", "Działające", "Kolejki")
    w.show_tab("Kolejki")
    assert w.tabs.currentIndex() == 2


def test_TC_11_2_status_bar_time(qtbot: QtBot) -> None:
    w = _win(qtbot)
    w.apply_snapshot(make_snapshot())
    assert w.updated_label.text() == "Ostatnia aktualizacja: 12:00:05"
    assert w.warning_label.isHidden()


def test_TC_11_3_stale_warning_keeps_data(qtbot: QtBot) -> None:
    w = _win(qtbot)
    w.apply_snapshot(make_snapshot(stale=True))
    assert not w.warning_label.isHidden()
    assert w.warning_label.text() == STALE_TEXT
    assert w.robots_tab.model.rowCount() == 5


def test_TC_11_4_close_hides_window(qtbot: QtBot) -> None:
    w = _win(qtbot)
    w.show()
    ev = QCloseEvent()
    w.closeEvent(ev)
    assert not ev.isAccepted()
    assert w.isHidden()
    assert ev.type() == QEvent.Type.Close


def test_TC_11_5_quit_menu_calls_callback(qtbot: QtBot) -> None:
    calls: list[str] = []
    tray = TrayIcon(lambda: calls.append("show"), lambda: calls.append("settings"),
                    lambda: calls.append("quit"))  # fmt: skip
    assert [a.text() for a in tray.menu.actions() if a.text()] == [
        "Pokaż", "Ustawienia…", "Zakończ",
    ]  # fmt: skip
    extra = tray.add_menu_action("Dodatkowa", lambda: calls.append("extra"))
    texts = [a.text() for a in tray.menu.actions()]
    assert texts.index("Dodatkowa") < texts.index("Zakończ")
    extra.trigger()
    tray.quit_action.trigger()
    assert calls == ["extra", "quit"]


def test_TC_11_5_app_quit_stops_scheduler(qtbot: QtBot) -> None:
    from PySide6.QtWidgets import QApplication

    from orch_monitor.app import App
    from orch_monitor.config.settings import Settings

    qapp = QApplication.instance()
    assert isinstance(qapp, QApplication)
    app = App(qapp, Settings())
    stopped: list[bool] = []
    app.scheduler.stop = lambda timeout=2.0: stopped.append(True)  # type: ignore[method-assign]
    quits: list[bool] = []
    app.qapp = type("Q", (), {"quit": lambda self: quits.append(True)})()  # type: ignore[assignment]
    app.tray.quit_action.trigger()
    assert stopped == [True] and quits == [True]
    qtbot.addWidget(app.window)


def test_bridge_delivers_snapshot(qtbot: QtBot) -> None:
    from orch_monitor.ui.bridge import SnapshotBridge

    b = SnapshotBridge()
    got: list[object] = []
    b.snapshot_ready.connect(got.append)
    snap = make_snapshot()
    b.publish(snap)
    assert got == [snap]


def test_TC_11_6_partial_errors_and_error_without_data(qtbot: QtBot) -> None:
    import dataclasses

    from orch_monitor.ui.main_window import PARTIAL_TEXT

    w = _win(qtbot)
    w.show_error("Błędne dane logowania")
    assert not w.warning_label.isHidden()
    assert "Błędne dane logowania" in w.warning_label.text()
    w.apply_snapshot(dataclasses.replace(make_snapshot(), errors={"robots": "Finance: 500"}))
    assert w.warning_label.text() == PARTIAL_TEXT
    assert "Finance: 500" in w.warning_label.toolTip()
    w.apply_snapshot(make_snapshot())
    assert w.warning_label.isHidden()
