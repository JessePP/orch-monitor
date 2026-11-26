"""Okno szczegolow kolejki: dzisiejsze elementy AE/BE."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from orch_monitor.clock import to_local
from orch_monitor.services.queue_details import DetailsResult, Kind
from orch_monitor.services.queues import QueueRow

DetailsProvider = Callable[[QueueRow, Kind], DetailsResult]
COLUMNS = ["Referencja", "Typ", "Treść błędu", "Godzina", "Robot"]
LIMIT = 500


class _Signals(QObject):
    done = Signal(int, object)
    failed = Signal(int, str)


class _Worker(QRunnable):
    def __init__(self, token: int, fn: Callable[[], DetailsResult]) -> None:
        super().__init__()
        self.token = token
        self.fn = fn
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(self.token, str(exc) or type(exc).__name__)
        else:
            self.signals.done.emit(self.token, result)


class QueueDetailsDialog(QDialog):
    """Pobieranie w QThreadPool (synchronous=True: w biezacym watku, dla testow)."""

    loaded = Signal()

    def __init__(
        self,
        queue: QueueRow,
        provider: DetailsProvider,
        parent: QWidget | None = None,
        synchronous: bool = False,
    ) -> None:
        super().__init__(parent)
        self.queue = queue
        self._provider = provider
        self._sync = synchronous
        self._token = 0
        self._workers: list[_Worker] = []
        self.setWindowTitle(f"Szczegóły kolejki: {queue.name}")
        self.resize(900, 450)
        self.kind_combo = QComboBox()
        self.kind_combo.addItem("AE i BE", "both")
        self.kind_combo.addItem("Tylko AE", "AE")
        self.kind_combo.addItem("Tylko BE", "BE")
        self.info_label = QLabel("")
        self.status_label = QLabel("")
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 160)
        self.table.setColumnWidth(1, 50)
        self.table.setColumnWidth(2, 380)
        self.table.verticalHeader().setVisible(False)
        top = QHBoxLayout()
        top.addWidget(QLabel(f"{queue.name} ({queue.folder})"), 1)
        top.addWidget(self.kind_combo)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.status_label)
        lay.addWidget(self.table)
        lay.addWidget(self.info_label)
        self.kind_combo.currentIndexChanged.connect(self.load)
        self.load()

    def kind(self) -> Kind:
        return str(self.kind_combo.currentData())  # type: ignore[return-value]

    def load(self) -> None:
        self._token += 1
        token = self._token
        kind = self.kind()
        self.status_label.setText("Ładowanie…")
        if self._sync:
            try:
                result = self._provider(self.queue, kind)
            except Exception as exc:  # noqa: BLE001
                self._on_failed(token, str(exc) or type(exc).__name__)
            else:
                self._on_done(token, result)
            return
        worker = _Worker(token, lambda: self._provider(self.queue, kind))
        worker.signals.done.connect(self._on_done)
        worker.signals.failed.connect(self._on_failed)
        self._workers.append(worker)
        QThreadPool.globalInstance().start(worker)

    def _on_failed(self, token: int, message: str) -> None:
        if token != self._token:
            return
        self.status_label.setText(f"Nie udało się pobrać szczegółów: {message}")
        self.loaded.emit()

    def _on_done(self, token: int, result: DetailsResult) -> None:
        if token != self._token:
            return
        self.status_label.setText("")
        self.table.setRowCount(len(result.items))
        for row, it in enumerate(result.items):
            when = to_local(it.end_processing).strftime("%H:%M:%S") if it.end_processing else "–"
            for col, text in enumerate(
                [it.reference, it.exception_type, it.reason, when, it.robot]
            ):
                self.table.setItem(row, col, QTableWidgetItem(text))
        self.info_label.setText(
            f"Pokazano pierwsze {LIMIT} elementów – lista obcięta."
            if result.truncated
            else f"Elementów: {len(result.items)}"
        )
        self.loaded.emit()
