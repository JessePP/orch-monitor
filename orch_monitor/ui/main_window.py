"""Okno glowne: trzy zakladki i pasek stanu."""

from __future__ import annotations

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QLabel, QMainWindow, QPushButton, QTabWidget, QWidget

from orch_monitor.clock import Clock, to_local, utc_now
from orch_monitor.refresh.snapshot import Snapshot
from orch_monitor.ui.queue_details_dialog import DetailsProvider
from orch_monitor.ui.tab_jobs import JobsTab
from orch_monitor.ui.tab_queues import QueuesTab
from orch_monitor.ui.tab_robots import RobotsTab

TAB_NAMES = ("Roboty", "Działające", "Kolejki")
STALE_TEXT = "Brak połączenia z Orchestratorem – pokazuję ostatnie dane"
PARTIAL_TEXT = "Część danych niedostępna (szczegóły w podpowiedzi)"


class MainWindow(QMainWindow):
    def __init__(
        self,
        clock: Clock = utc_now,
        details_provider: DetailsProvider | None = None,
        synchronous_details: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Orchestrator Monitor")
        self.resize(1100, 650)
        self.allow_close = False  # True: closeEvent naprawde zamyka okno
        self.robots_tab = RobotsTab()
        self.jobs_tab = JobsTab(clock)
        self.queues_tab = QueuesTab(details_provider, synchronous_details=synchronous_details)
        self.tabs = QTabWidget()
        for name, tab in zip(
            TAB_NAMES, (self.robots_tab, self.jobs_tab, self.queues_tab), strict=True
        ):
            self.tabs.addTab(tab, name)
        self.setCentralWidget(self.tabs)
        self.updated_label = QLabel("Ostatnia aktualizacja: –")
        self.warning_label = QLabel(STALE_TEXT)
        self.warning_label.setStyleSheet("color: #b71c1c; font-weight: bold;")
        self.warning_label.setVisible(False)
        self.reports_button = QPushButton("Raporty…")
        bar = self.statusBar()
        bar.addPermanentWidget(self.reports_button)
        bar.addWidget(self.updated_label)
        bar.addPermanentWidget(self.warning_label)

    def apply_snapshot(self, snapshot: Snapshot) -> None:
        self.robots_tab.apply_snapshot(snapshot)
        self.jobs_tab.apply_snapshot(snapshot)
        self.queues_tab.apply_snapshot(snapshot)
        stamp = to_local(snapshot.fetched_at).strftime("%H:%M:%S")
        self.updated_label.setText(f"Ostatnia aktualizacja: {stamp}")
        if snapshot.stale:
            self._set_warning(STALE_TEXT, snapshot.errors)
        elif snapshot.errors:
            self._set_warning(PARTIAL_TEXT, snapshot.errors)
        else:
            self.warning_label.setVisible(False)

    def show_error(self, message: str) -> None:
        """Blad pobrania, zanim przyszly jakiekolwiek dane (np. bledne dane logowania)."""
        self.warning_label.setText(f"Brak danych z Orchestratora: {message}")
        self.warning_label.setToolTip(message)
        self.warning_label.setVisible(True)

    def _set_warning(self, text: str, errors: dict[str, str]) -> None:
        self.warning_label.setText(text)
        self.warning_label.setToolTip("\n".join(f"{k}: {v}" for k, v in errors.items()))
        self.warning_label.setVisible(True)

    def show_tab(self, name: str) -> None:
        if name not in TAB_NAMES:
            raise ValueError(f"Nieznana zakladka: {name}")
        self.tabs.setCurrentIndex(TAB_NAMES.index(name))

    def show_and_raise(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self.allow_close:
            event.accept()
            return
        event.ignore()
        self.hide()
