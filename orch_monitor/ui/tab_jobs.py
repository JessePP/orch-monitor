"""Zakladka 2: dzialajace i oczekujace joby oraz dzisiejsze Faulted (z notatkami)."""

from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QModelIndex, Qt, QTimer
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from orch_monitor.clock import Clock, to_local, utc_now
from orch_monitor.config.notes import ErrorRef, NotesError, NotesStore
from orch_monitor.refresh.snapshot import Snapshot
from orch_monitor.services.jobs import FaultedJob, PendingJob, RunningJob
from orch_monitor.ui.notes_dialog import NotesDialog, note_count_text

RUNNING_COLUMNS = ["Robot", "Proces", "Maszyna", "Start", "Czas trwania", "Źródło", "Folder"]
PENDING_COLUMNS = ["Proces", "Dodany", "Czas oczekiwania", "Folder"]
FAULTED_COLUMNS = ["Proces", "Robot", "Koniec", "Informacja", "Folder", "Notatki"]
FAULTED_NOTES_COL = 5
DURATION_COL = 4
WAITING_COL = 2
LONG_BG = QColor("#ffe0b2")
LONG_FG = QColor("#7a3b00")


def format_duration(delta: timedelta) -> str:
    total = max(0, int(delta.total_seconds()))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def _table(columns: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(columns))
    t.setHorizontalHeaderLabels(columns)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    return t


def _item(text: str) -> QTableWidgetItem:
    return QTableWidgetItem(text)


def _clock_time(dt: datetime | None) -> str:
    return to_local(dt).strftime("%H:%M:%S") if dt is not None else "–"


def _job_ref(j: FaultedJob) -> ErrorRef:
    return ErrorRef("job", j.job_id, f"Job {j.process} ({j.folder}) · Faulted", j.info)


class JobsTab(QWidget):
    def __init__(
        self,
        clock: Clock = utc_now,
        parent: QWidget | None = None,
        notes: NotesStore | None = None,
    ) -> None:
        super().__init__(parent)
        self._clock = clock
        self._notes = notes
        self._running: list[RunningJob] = []
        self._pending: list[PendingJob] = []
        self._faulted: list[FaultedJob] = []
        self.notes_dialog: NotesDialog | None = None
        self.counter = QLabel("")
        self.running_table = _table(RUNNING_COLUMNS)
        self.pending_table = _table(PENDING_COLUMNS)
        self.pending_header = QLabel("Oczekujące (Pending)")
        self.pending_header.setStyleSheet("font-weight: bold;")
        self.faulted_table = _table(FAULTED_COLUMNS)
        self.faulted_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        for col in (0, 1, 2, 4, 5):
            self.faulted_table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        self.faulted_table.setColumnHidden(FAULTED_NOTES_COL, notes is None)
        self.faulted_table.setToolTip("Dwuklik na wierszu otwiera notatki do błędu")
        self.faulted_header = QLabel("Dziś zakończone błędem (Faulted)")
        self.faulted_header.setStyleSheet("font-weight: bold;")
        self.faulted_status = QLabel("")
        self.faulted_status.setStyleSheet("color: #b71c1c;")
        self.faulted_status.setVisible(False)
        self.empty_label = QLabel("Nic teraz nie działa")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(self.running_table, 3)
        cl.addWidget(self.pending_header)
        cl.addWidget(self.pending_table, 2)
        cl.addWidget(self.faulted_header)
        cl.addWidget(self.faulted_status)
        cl.addWidget(self.faulted_table, 2)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty_label)  # 0
        self.stack.addWidget(content)  # 1
        lay = QVBoxLayout(self)
        lay.addWidget(self.counter)
        lay.addWidget(self.stack)

        self.faulted_table.doubleClicked.connect(self._on_faulted_double_click)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.tick)
        self._timer.start()

    def apply_snapshot(self, snapshot: Snapshot) -> None:
        self._running = list(snapshot.running)
        self._pending = list(snapshot.pending)
        self._faulted = list(snapshot.faulted_today)
        text = f"{len(self._running)} działa · {len(self._pending)} czeka"
        if self._faulted:
            text += f" · {len(self._faulted)} Faulted dziś"
        self.counter.setText(text)
        self.stack.setCurrentIndex(1 if self._running or self._pending or self._faulted else 0)
        self._fill_running()
        self._fill_pending()
        self._fill_faulted()

    def _fill_running(self) -> None:
        t = self.running_table
        t.setRowCount(len(self._running))
        for row, j in enumerate(self._running):
            cells = [
                j.robot,
                j.process,
                j.machine,
                _clock_time(j.start),
                self._duration_text(j),
                j.source,
                j.folder,
            ]
            for col, text in enumerate(cells):
                it = _item(text)
                if j.is_long:
                    it.setBackground(QBrush(LONG_BG))
                    it.setForeground(QBrush(LONG_FG))
                t.setItem(row, col, it)

    def _fill_pending(self) -> None:
        t = self.pending_table
        t.setRowCount(len(self._pending))
        for row, p in enumerate(self._pending):
            cells = [p.process, _clock_time(p.created), self._waiting_text(p), p.folder]
            for col, text in enumerate(cells):
                t.setItem(row, col, _item(text))

    def _fill_faulted(self) -> None:
        counts: dict[str, int] = {}
        self.faulted_status.setVisible(False)
        if self._notes is not None and self._faulted:
            try:
                counts = self._notes.counts()
            except NotesError as exc:
                self.faulted_status.setText(str(exc))
                self.faulted_status.setVisible(True)
        t = self.faulted_table
        t.setRowCount(len(self._faulted))
        for row, j in enumerate(self._faulted):
            notes = note_count_text(counts.get(_job_ref(j).key, 0))
            cells = [j.process, j.robot, _clock_time(j.end_time), j.info, j.folder, notes]
            for col, text in enumerate(cells):
                it = _item(text)
                if col == 3:
                    it.setToolTip(j.info)
                t.setItem(row, col, it)

    def open_notes(self, row: int) -> NotesDialog | None:
        if self._notes is None or not 0 <= row < len(self._faulted):
            return None
        dlg = NotesDialog(_job_ref(self._faulted[row]), self._notes, parent=self)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.changed.connect(self._fill_faulted)
        self.notes_dialog = dlg
        dlg.show()
        return dlg

    def _on_faulted_double_click(self, index: QModelIndex) -> None:
        self.open_notes(index.row())

    def _duration_text(self, j: RunningJob) -> str:
        if j.start is None:
            return format_duration(j.duration)
        return format_duration(self._clock() - j.start)

    def _waiting_text(self, p: PendingJob) -> str:
        if p.created is None:
            return format_duration(p.waiting)
        return format_duration(self._clock() - p.created)

    def tick(self) -> None:
        """Przelicza czas trwania i oczekiwania z zegara (bez API)."""
        for row, j in enumerate(self._running):
            it = self.running_table.item(row, DURATION_COL)
            if it is not None:
                it.setText(self._duration_text(j))
        for row, p in enumerate(self._pending):
            it = self.pending_table.item(row, WAITING_COL)
            if it is not None:
                it.setText(self._waiting_text(p))
