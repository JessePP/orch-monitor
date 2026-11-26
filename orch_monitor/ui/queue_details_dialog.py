"""Okno szczegolow kolejki: dzisiejsze elementy AE/BE."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from orch_monitor.clock import Clock, to_local, utc_now
from orch_monitor.config.dismissed import DismissedStore
from orch_monitor.services.queue_details import DetailsResult, Kind, QueueItemDetail
from orch_monitor.services.queues import QueueRow

DetailsProvider = Callable[[QueueRow, Kind], DetailsResult]
COLUMNS = ["Referencja", "Typ", "Treść błędu", "Godzina", "Robot"]
LIMIT = 500
GREY = QColor("#8a8a8a")


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
    """Pobieranie w QThreadPool (synchronous=True: w biezacym watku, dla testow).

    Z `store` mozna lokalnie „zamknac” element (ukryc go na liscie). Zamkniecie dotyczy
    tylko tej listy: liczniki AE/BE w zakladce Kolejki i powiadomienia pochodza z
    Orchestratora i pozostaja bez zmian. Ostatni wynik jest trzymany w cache, wiec
    zamykanie i przywracanie nie odpytuje API ponownie.
    """

    loaded = Signal()

    def __init__(
        self,
        queue: QueueRow,
        provider: DetailsProvider,
        parent: QWidget | None = None,
        synchronous: bool = False,
        store: DismissedStore | None = None,
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(parent)
        self.queue = queue
        self._store = store
        self._clock = clock
        self._result: DetailsResult | None = None
        self._shown: list[QueueItemDetail] = []
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
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setColumnWidth(0, 160)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 380)
        self.table.verticalHeader().setVisible(False)
        top = QHBoxLayout()
        top.addWidget(QLabel(f"{queue.name} ({queue.folder})"), 1)
        top.addWidget(self.kind_combo)
        self.show_dismissed_check = QCheckBox("Pokaż zamknięte")
        self.dismiss_button = QPushButton("Zamknij zaznaczone")
        self.clear_button = QPushButton("Wyczyść widok")
        self.clear_button.setToolTip(
            "Ukrywa wszystkie widoczne błędy; potem pojawią się tylko nowe"
        )
        self.restore_button = QPushButton("Przywróć zaznaczone")
        bottom = QHBoxLayout()
        bottom.addWidget(self.info_label, 1)
        bottom.addWidget(self.show_dismissed_check)
        bottom.addWidget(self.dismiss_button)
        bottom.addWidget(self.clear_button)
        bottom.addWidget(self.restore_button)
        for w in (
            self.show_dismissed_check,
            self.dismiss_button,
            self.clear_button,
            self.restore_button,
        ):
            w.setVisible(store is not None)
        self.restore_button.setVisible(False)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.status_label)
        lay.addWidget(self.table)
        lay.addLayout(bottom)
        self.kind_combo.currentIndexChanged.connect(self.load)
        self.show_dismissed_check.toggled.connect(self._on_show_toggled)
        self.dismiss_button.clicked.connect(self.dismiss_selected)
        self.clear_button.clicked.connect(self.clear_view)
        self.restore_button.clicked.connect(self.restore_selected)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self._update_buttons()
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
        self._result = result
        self._render()
        self.loaded.emit()

    def _is_dismissed(self, item_id: int) -> bool:
        return self._store is not None and self._store.is_dismissed(item_id)

    def _render(self) -> None:
        result = self._result
        if result is None:
            return
        show_all = self.show_dismissed_check.isChecked()
        hidden = sum(1 for it in result.items if self._is_dismissed(it.item_id))
        self._shown = [it for it in result.items if show_all or not self._is_dismissed(it.item_id)]
        self.table.setRowCount(len(self._shown))
        for row, it in enumerate(self._shown):
            closed = self._is_dismissed(it.item_id)
            when = to_local(it.end_processing).strftime("%H:%M:%S") if it.end_processing else "–"
            kind = f"{it.exception_type} (zamknięty)" if closed else it.exception_type
            for col, text in enumerate([it.reference, kind, it.reason, when, it.robot]):
                cell = QTableWidgetItem(text)
                if closed:
                    cell.setForeground(QBrush(GREY))
                self.table.setItem(row, col, cell)
        if result.truncated:
            text = f"Pokazano pierwsze {LIMIT} elementów – lista obcięta."
        else:
            text = f"Elementów: {len(self._shown)}"
        if hidden and not self._shown:
            text = "Widok wyczyszczony – nowe błędy pojawią się tutaj"
        if hidden:
            label = "zamkniętych" if show_all else "zamkniętych ukrytych"
            text += f" · {label}: {hidden}"
        self.info_label.setText(text)
        self._update_buttons()

    def _selected_items(self) -> list[QueueItemDetail]:
        rows = {i.row() for i in self.table.selectionModel().selectedRows()}
        return [self._shown[r] for r in sorted(rows) if 0 <= r < len(self._shown)]

    def _update_buttons(self) -> None:
        if self._store is None:
            return
        selected = self._selected_items()
        closed = [it for it in selected if self._is_dismissed(it.item_id)]
        self.dismiss_button.setEnabled(len(selected) > len(closed))
        self.clear_button.setEnabled(any(not self._is_dismissed(it.item_id) for it in self._shown))
        self.restore_button.setVisible(self.show_dismissed_check.isChecked())
        self.restore_button.setEnabled(bool(closed))

    def _on_show_toggled(self, _checked: bool) -> None:
        self._render()

    def dismiss_selected(self) -> None:
        if self._store is None:
            return
        ids = [it.item_id for it in self._selected_items() if not self._is_dismissed(it.item_id)]
        if ids:
            self._store.dismiss(ids, self._clock())
            self._render()

    def clear_view(self) -> None:
        """Zamyka wszystkie widoczne (niezamkniete) elementy naraz."""
        if self._store is None:
            return
        ids = [it.item_id for it in self._shown if not self._is_dismissed(it.item_id)]
        if ids:
            self._store.dismiss(ids, self._clock())
            self._render()

    def restore_selected(self) -> None:
        if self._store is None:
            return
        ids = [it.item_id for it in self._selected_items() if self._is_dismissed(it.item_id)]
        if ids:
            self._store.restore(ids)
            self._render()
