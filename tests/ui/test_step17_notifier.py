from datetime import UTC, datetime, timedelta

from helpers import make_snapshot
from PySide6.QtGui import QAction
from pytestqt.qtbot import QtBot

from orch_monitor.clock import WARSAW
from orch_monitor.config.settings import NotificationSettings
from orch_monitor.notify.engine import NotificationEngine
from orch_monitor.services.queues import QueueRow
from orch_monitor.services.robots import RobotStatus
from orch_monitor.ui.main_window import MainWindow
from orch_monitor.ui.notifier import MUTED_TOOLTIP, Notifier
from orch_monitor.ui.tray import TrayIcon

T0 = datetime(2026, 11, 26, 9, 0, 0, tzinfo=UTC)  # 10:00 w Warszawie


class Env:
    def __init__(self, qtbot: QtBot, now: datetime = T0, cfg: NotificationSettings | None = None):
        self.now = now
        self.cfg = cfg or NotificationSettings()
        self.shown: list[tuple[str, str]] = []
        self.window = MainWindow()
        qtbot.addWidget(self.window)
        self.tray = TrayIcon(lambda: None, lambda: None, lambda: None, parent=self.window)
        self.tray.show_message = lambda t, m, timeout_ms=0: self.shown.append((t, m))  # type: ignore[method-assign]
        self.engine = NotificationEngine(lambda: self.cfg, lambda: self.now)
        self.notifier = Notifier(self.tray, self.window, self.engine, lambda: self.now)

    def action(self, text: str) -> QAction:
        return next(a for a in self.notifier.mute_menu.actions() if a.text() == text)

    def icon_key(self) -> int:
        return self.tray.icon.icon().cacheKey()


def _q(ae: int) -> QueueRow:
    return QueueRow(7, "Faktury_IN", "Finance", 9, ae, 0, 90.0, None, 0, 0, None)


def _robot(status: str) -> RobotStatus:
    return RobotStatus(1, "BOT01", "M1", status, ("Finance",), None, "Unattended")


def _feed_ae(env: Env) -> None:
    env.notifier.on_snapshot(make_snapshot(queues=[_q(0)]))
    env.notifier.on_snapshot(make_snapshot(queues=[_q(2)]))


def _feed_robot_down(env: Env) -> None:
    env.notifier.on_snapshot(make_snapshot(robots=[_robot("Available")]))
    env.notifier.on_snapshot(make_snapshot(robots=[_robot("Disconnected")]))


def test_TC_17_1_ae_message_shown(qtbot: QtBot) -> None:
    env = Env(qtbot)
    _feed_ae(env)
    assert env.shown == [("Kolejka Faktury_IN", "Faktury_IN: 2 nowe AE")]


def test_TC_17_2_click_ae_opens_queues(qtbot: QtBot) -> None:
    env = Env(qtbot)
    _feed_ae(env)
    env.window.show_tab("Roboty")
    env.window.hide()
    env.tray.icon.messageClicked.emit()
    assert env.window.isVisible()
    assert env.window.tabs.currentIndex() == 2


def test_TC_17_3_click_robot_opens_robots(qtbot: QtBot) -> None:
    env = Env(qtbot)
    env.window.show_tab("Kolejki")
    _feed_robot_down(env)
    assert env.shown and env.shown[0][1] == "Robot BOT01 rozłączony"
    env.tray.icon.messageClicked.emit()
    assert env.window.tabs.currentIndex() == 0


def test_TC_17_4_mute_one_hour(qtbot: QtBot) -> None:
    env = Env(qtbot)
    normal = env.icon_key()
    env.action("na 1 h").trigger()
    assert env.engine.muted_until == datetime(2026, 11, 26, 10, 0, 0, tzinfo=UTC)  # 11:00 PL
    assert env.icon_key() != normal
    assert env.tray.icon.toolTip() == MUTED_TOOLTIP
    _feed_ae(env)
    assert env.shown == []
    # wygasniecie: ikona wraca przy kolejnym snapshocie
    env.now = T0 + timedelta(hours=1, minutes=1)
    env.notifier.on_snapshot(make_snapshot(queues=[_q(2)]))
    assert env.icon_key() == normal


def test_TC_17_5_mute_until_end_of_day(qtbot: QtBot) -> None:
    env = Env(qtbot, now=datetime(2026, 11, 26, 14, 20, tzinfo=UTC))  # 15:20 PL
    env.action("do końca dnia").trigger()
    assert env.engine.muted_until == datetime(2026, 11, 26, 23, 59, 59, tzinfo=WARSAW)


def test_TC_17_6_unmute(qtbot: QtBot) -> None:
    env = Env(qtbot)
    normal = env.icon_key()
    env.action("na 30 min").trigger()
    assert env.engine.is_muted() and env.icon_key() != normal
    env.action("Włącz powiadomienia").trigger()
    assert env.engine.muted_until is None and not env.engine.is_muted()
    assert env.icon_key() == normal
    _feed_ae(env)
    assert len(env.shown) == 1


def test_mute_menu_entries_and_settings_respected(qtbot: QtBot) -> None:
    env = Env(qtbot, cfg=NotificationSettings(queue_ae=False))
    texts = [a.text() for a in env.notifier.mute_menu.actions() if a.text()]
    assert texts == ["na 30 min", "na 1 h", "na 4 h", "do końca dnia", "Włącz powiadomienia"]
    _feed_ae(env)
    assert env.shown == []
    env.cfg = NotificationSettings(queue_ae=True)  # zmiana ustawien dziala od razu
    env.notifier.on_snapshot(make_snapshot(queues=[_q(5)]))
    assert len(env.shown) == 1
