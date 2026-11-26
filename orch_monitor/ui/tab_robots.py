"""Zakladka 1: statusy robotow."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from orch_monitor.clock import to_local
from orch_monitor.refresh.snapshot import Snapshot
from orch_monitor.services.robots import RobotStatus

COLUMNS = ["Robot", "Maszyna", "Status", "Folder", "Ostatni heartbeat", "Typ"]
ALL_FOLDERS = "Wszystkie foldery"
ALL_STATUSES = "Wszystkie statusy"
STATUS_ORDER = ["Available", "Busy", "Disconnected", "Unresponsive"]
_PROBLEM = {"Disconnected", "Unresponsive"}
_COLORS: dict[str, tuple[str, str]] = {
    "Available": ("#d7f2dc", "#14532d"),
    "Busy": ("#d6e6fb", "#0b3d91"),
    "Disconnected": ("#f8d7da", "#7f1d1d"),
    "Unresponsive": ("#f8d7da", "#7f1d1d"),
}
_Index = QModelIndex | QPersistentModelIndex


def _group(status: str) -> int:
    if status in _PROBLEM:
        return 0
    return {"Busy": 1, "Available": 2}.get(status, 3)


def status_colors(status: str) -> tuple[QColor, QColor] | None:
    pair = _COLORS.get(status)
    return (QColor(pair[0]), QColor(pair[1])) if pair else None


class RobotsModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._robots: list[RobotStatus] = []

    def set_robots(self, robots: list[RobotStatus]) -> None:
        ordered = sorted(robots, key=lambda r: (_group(r.status), r.name.casefold()))
        self.beginResetModel()
        self._robots = ordered
        self.endResetModel()

    def robot_at(self, row: int) -> RobotStatus:
        return self._robots[row]

    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._robots)

    def columnCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]
        return None

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        r = self._robots[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return [
                r.name,
                r.machine,
                r.status,
                ", ".join(r.folders),
                to_local(r.last_heartbeat).strftime("%H:%M:%S") if r.last_heartbeat else "–",
                r.robot_type,
            ][col]
        colors = status_colors(r.status)
        if colors and role == Qt.ItemDataRole.BackgroundRole:
            return QBrush(colors[0])
        if colors and role == Qt.ItemDataRole.ForegroundRole:
            return QBrush(colors[1])
        return None


class RobotsFilterProxy(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self.folder = ""
        self.status = ""
        self.search = ""

    def set_filters(self, folder: str, status: str, search: str) -> None:
        self.beginFilterChange()
        self.folder, self.status, self.search = folder, status, search.strip().casefold()
        self.endFilterChange()

    def filterAcceptsRow(self, source_row: int, source_parent: _Index) -> bool:
        model = self.sourceModel()
        assert isinstance(model, RobotsModel)
        r = model.robot_at(source_row)
        if self.folder and self.folder not in r.folders:
            return False
        if self.status and r.status != self.status:
            return False
        return not self.search or self.search in r.name.casefold()


def counter_text(summary: dict[str, int]) -> str:
    names = [s for s in STATUS_ORDER if summary.get(s)]
    names += sorted(s for s in summary if s not in STATUS_ORDER and summary[s])
    return " · ".join(f"{summary[s]} {s}" for s in names)


class RobotsTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = RobotsModel()
        self.proxy = RobotsFilterProxy()
        self.proxy.setSourceModel(self.model)
        self.counter = QLabel("")
        self.folder_combo = QComboBox()
        self.folder_combo.addItem(ALL_FOLDERS, "")
        self.status_combo = QComboBox()
        self.status_combo.addItem(ALL_STATUSES, "")
        for s in STATUS_ORDER:
            self.status_combo.addItem(s, s)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Szukaj po nazwie robota")
        self.search.setClearButtonEnabled(True)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)

        top = QHBoxLayout()
        top.addWidget(self.counter, 1)
        top.addWidget(self.folder_combo)
        top.addWidget(self.status_combo)
        top.addWidget(self.search)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table)
        self.folder_combo.currentIndexChanged.connect(self._filters_changed)
        self.status_combo.currentIndexChanged.connect(self._filters_changed)
        self.search.textChanged.connect(self._filters_changed)

    def _filters_changed(self) -> None:
        self.proxy.set_filters(
            str(self.folder_combo.currentData() or ""),
            str(self.status_combo.currentData() or ""),
            self.search.text(),
        )

    def selected_robot_id(self) -> int | None:
        idx = self.table.currentIndex()
        if not idx.isValid():
            return None
        return self.model.robot_at(self.proxy.mapToSource(idx).row()).robot_id

    def apply_snapshot(self, snapshot: Snapshot) -> None:
        robots = snapshot.robots.robots
        selected = self.selected_robot_id()
        self._update_folders(sorted({f for r in robots for f in r.folders}))
        self.model.set_robots(robots)
        self.counter.setText(counter_text(snapshot.robots.summary))
        if selected is not None:
            for row in range(self.proxy.rowCount()):
                src = self.proxy.mapToSource(self.proxy.index(row, 0)).row()
                if self.model.robot_at(src).robot_id == selected:
                    self.table.selectRow(row)
                    break

    def _update_folders(self, folders: list[str]) -> None:
        current = str(self.folder_combo.currentData() or "")
        existing = [self.folder_combo.itemData(i) for i in range(1, self.folder_combo.count())]
        if existing == folders:
            return
        self.folder_combo.blockSignals(True)
        self.folder_combo.clear()
        self.folder_combo.addItem(ALL_FOLDERS, "")
        for f in folders:
            self.folder_combo.addItem(f, f)
        idx = self.folder_combo.findData(current)
        self.folder_combo.setCurrentIndex(max(idx, 0))
        self.folder_combo.blockSignals(False)
        self._filters_changed()
