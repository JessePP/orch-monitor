"""Ikona w zasobniku systemowym z menu."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget


def default_icon() -> QIcon:
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#1565c0"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, 28, 28)
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(11, 11, 10, 10)
    p.end()
    return QIcon(pm)


class TrayIcon:
    """Menu: Pokaż, Ustawienia…, [pozycje dodatkowe], separator, Zakończ."""

    def __init__(
        self,
        on_show: Callable[[], None],
        on_settings: Callable[[], None],
        on_quit: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        self.icon = QSystemTrayIcon(default_icon(), parent)
        self.icon.setToolTip("Orchestrator Monitor")
        self.menu = QMenu(parent)
        self.show_action = self.menu.addAction("Pokaż")
        self.settings_action = self.menu.addAction("Ustawienia…")
        self._tail = self.menu.addSeparator()
        self.quit_action = self.menu.addAction("Zakończ")
        self.show_action.triggered.connect(lambda _c=False: on_show())
        self.settings_action.triggered.connect(lambda _c=False: on_settings())
        self.quit_action.triggered.connect(lambda _c=False: on_quit())
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(
            lambda reason: (
                on_show()
                if reason
                in (
                    QSystemTrayIcon.ActivationReason.Trigger,
                    QSystemTrayIcon.ActivationReason.DoubleClick,
                )
                else None
            )
        )

    def add_menu_action(self, text: str, callback: Callable[[], None]) -> QAction:
        """Dodaje pozycje przed separatorem i „Zakończ”."""
        action = QAction(text, self.menu)
        action.triggered.connect(lambda _c=False: callback())
        self.menu.insertAction(self._tail, action)
        return action

    def add_menu_section(self, title: str) -> QMenu:
        """Dodaje podmenu (np. wyciszenie) przed separatorem; zwraca QMenu do wypelnienia."""
        sub = QMenu(title, self.menu)
        self.menu.insertMenu(self._tail, sub)
        return sub

    def show(self) -> None:
        self.icon.show()

    def hide(self) -> None:
        self.icon.hide()

    def show_message(self, title: str, text: str, timeout_ms: int = 8000) -> None:
        self.icon.showMessage(title, text, QSystemTrayIcon.MessageIcon.Warning, timeout_ms)
