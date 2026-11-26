"""Wyswietlanie powiadomien w zasobniku i menu wyciszenia."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap

from orch_monitor.clock import Clock
from orch_monitor.notify.engine import NotificationEngine, Tab, mute_options
from orch_monitor.refresh.snapshot import Snapshot
from orch_monitor.ui.main_window import MainWindow
from orch_monitor.ui.tray import TrayIcon, default_icon

TAB_FOR_TARGET: dict[Tab, str] = {"robots": "Roboty", "jobs": "Działające", "queues": "Kolejki"}
UNMUTE_TEXT = "Włącz powiadomienia"
MUTED_TOOLTIP = "Orchestrator Monitor (powiadomienia wyciszone)"
NORMAL_TOOLTIP = "Orchestrator Monitor"


def muted_icon() -> QIcon:
    """Ikona zasobnika przy wyciszeniu: szara z przekreslona tarcza."""
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#9e9e9e"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, 28, 28)
    p.setPen(QColor("#b71c1c"))
    p.drawLine(7, 25, 25, 7)
    p.end()
    return QIcon(pm)


class Notifier:
    def __init__(
        self, tray: TrayIcon, window: MainWindow, engine: NotificationEngine, clock: Clock
    ) -> None:
        self._tray = tray
        self._window = window
        self._engine = engine
        self._clock = clock
        self._target: Tab | None = None
        self._normal_icon = default_icon()
        self._muted_icon = muted_icon()
        self._icon_muted: bool | None = None
        self.mute_actions: list[QAction] = []
        menu = tray.add_menu_section("Wycisz powiadomienia")
        self.mute_menu = menu
        for label, _until in mute_options(clock()):
            action = menu.addAction(label.removeprefix("Wycisz "))
            action.triggered.connect(lambda _c=False, t=label: self._mute(t))
            self.mute_actions.append(action)
        menu.addSeparator()
        self.unmute_action = menu.addAction(UNMUTE_TEXT)
        self.unmute_action.triggered.connect(lambda _c=False: self.unmute())
        tray.icon.messageClicked.connect(self.on_message_clicked)
        self.refresh_icon()

    def _mute(self, label: str) -> None:
        for text, until in mute_options(self._clock()):
            if text == label:
                self._engine.mute_until(until)
        self.refresh_icon()

    def unmute(self) -> None:
        self._engine.mute_until(None)
        self.refresh_icon()

    def refresh_icon(self) -> None:
        muted = self._engine.is_muted()
        if muted == self._icon_muted:
            return
        self._icon_muted = muted
        self._tray.icon.setIcon(self._muted_icon if muted else self._normal_icon)
        self._tray.icon.setToolTip(MUTED_TOOLTIP if muted else NORMAL_TOOLTIP)

    def on_snapshot(self, snapshot: Snapshot) -> None:
        for n in self._engine.process(snapshot):
            self._tray.show_message(n.title, n.message)
            self._target = n.target_tab
        self.refresh_icon()

    def on_message_clicked(self) -> None:
        self._window.show_and_raise()
        if self._target is not None:
            self._window.show_tab(TAB_FOR_TARGET[self._target])
