"""Zakladka 3: dzisiejsze kolejki."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from orch_monitor.refresh.snapshot import Snapshot
from orch_monitor.reports.csv_queues import (
    default_filename,
    export_queues_csv,
    format_change,
    format_last,
    format_pct,
)
from orch_monitor.services.queues import QueueRow
from orch_monitor.ui.queue_details_dialog import DetailsProvider, QueueDetailsDialog

COLUMNS = [
    "Kolejka",
    "Folder",
    "Sukcesy",
    "AE",
    "BE",
    "% sukcesu",
    "vs wczoraj",
    "W toku / Nowe",
    "Ostatnie przetworzenie",
]
RED = QColor("#c62828")
GREY = QColor("#8a8a8a")
GREEN = QColor("#2e7d32")


def _counter_item(label: str, value: int) -> QTableWidgetItem:
    it = QTableWidgetItem(f"{label}: {value}")
    it.setForeground(QBrush(RED if value > 0 else GREY))
    if value > 0:
        font = it.font()
        font.setBold(True)
        it.setFont(font)
    return it


class QueuesTab(QWidget):
    def __init__(
        self,
        details_provider: DetailsProvider | None = None,
        parent: QWidget | None = None,
        synchronous_details: bool = False,
    ) -> None:
        super().__init__(parent)
        self._provider = details_provider
        self._sync = synchronous_details
        self._rows: list[QueueRow] = []
        self._day: date | None = None
        self._dialogs: list[QueueDetailsDialog] = []
        self.last_dialog: QueueDetailsDialog | None = None
        self.status_label = QLabel("")
        self.export_button = QPushButton("Eksport CSV")
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        top = QHBoxLayout()
        top.addWidget(self.status_label, 1)
        top.addWidget(self.export_button)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table)
        self.export_button.clicked.connect(self._choose_and_export)
        self.table.doubleClicked.connect(self._on_double_click)

    def apply_snapshot(self, snapshot: Snapshot) -> None:
        self._rows = list(snapshot.queues)
        self._day = snapshot.day
        t = self.table
        t.setRowCount(len(self._rows))
        for i, r in enumerate(self._rows):
            change = QTableWidgetItem(format_change(r.change_pp))
            if r.change_pp is not None and round(r.change_pp) != 0:
                change.setForeground(QBrush(GREEN if r.change_pp > 0 else RED))
            pct = QTableWidgetItem(format_pct(r.success_pct))
            if r.success_pct is None:
                pct.setForeground(QBrush(GREY))
            values = [
                QTableWidgetItem(r.name),
                QTableWidgetItem(r.folder),
                QTableWidgetItem(str(r.successful)),
                _counter_item("AE", r.ae),
                _counter_item("BE", r.be),
                pct,
                change,
                QTableWidgetItem(f"{r.in_progress} / {r.new}"),
                QTableWidgetItem(format_last(r)),
            ]
            for col, item in enumerate(values):
                t.setItem(i, col, item)

    def open_details(self, row: int) -> QueueDetailsDialog | None:
        if self._provider is None or not 0 <= row < len(self._rows):
            return None
        dlg = QueueDetailsDialog(
            self._rows[row], self._provider, parent=self, synchronous=self._sync
        )
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.finished.connect(
            lambda _r, d=dlg: self._dialogs.remove(d) if d in self._dialogs else None
        )
        self._dialogs.append(dlg)
        self.last_dialog = dlg
        dlg.show()
        return dlg

    def _on_double_click(self, index: QModelIndex) -> None:
        self.open_details(index.row())

    def _choose_and_export(self) -> None:
        name = default_filename(self._day) if self._day else "kolejki.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Eksport CSV", name, "CSV (*.csv)")
        if path:
            self.export_csv(Path(path))

    def export_csv(self, path: Path | str) -> None:
        try:
            export_queues_csv(self._rows, path)
        except OSError as exc:
            self.status_label.setText(f"Nie udało się zapisać pliku: {exc}")
            return
        self.status_label.setText(f"Zapisano: {path}")
