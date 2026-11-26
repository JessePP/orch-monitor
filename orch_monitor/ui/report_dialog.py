"""Okno raportu: wybor okresu i folderow, generowanie w tle, podglad i zapis."""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from datetime import date

from PySide6.QtCore import QDate, QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from orch_monitor.clock import Clock, to_local, utc_now
from orch_monitor.reports.builder import Cancelled, Progress, ReportCancelled
from orch_monitor.reports.csv_export import (
    export_report_csv_zip,
    report_filename,
    report_tables,
    verdict_text,
)
from orch_monitor.reports.model import Report
from orch_monitor.reports.periods import (
    Period,
    period_custom,
    period_day,
    period_month,
    period_week,
)
from orch_monitor.reports.xlsx_export import export_report_xlsx

BuildFn = Callable[[Period, list[str], Progress, Cancelled], Report]

MODES = ("Dzień", "Tydzień", "Miesiąc", "Zakres")
SECTION_TABS = {
    "podsumowanie.csv": "Podsumowanie",
    "procesy.csv": "Procesy",
    "kolejki.csv": "Kolejki",
    "dni.csv": "Dni",
    "bledy.csv": "Błędy",
}
RANGE_ERROR = "Data „do” jest wcześniejsza niż „od”."
CANCELLED_TEXT = "Anulowano"
OK_STYLE = "color: #1b5e20; font-weight: bold;"
BAD_STYLE = "color: #b71c1c; font-weight: bold;"


class _Signals(QObject):
    progress = Signal(int, int)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()


class _Worker(QRunnable):
    def __init__(
        self, build_fn: BuildFn, period: Period, folders: list[str], cancel: threading.Event
    ) -> None:
        super().__init__()
        self.signals = _Signals()
        self._args = (build_fn, period, folders)
        self._cancel = cancel

    def run(self) -> None:
        run_build(self.signals, *self._args, self._cancel)


def run_build(
    signals: _Signals,
    build_fn: BuildFn,
    period: Period,
    folders: list[str],
    cancel: threading.Event,
) -> None:
    try:
        report = build_fn(period, folders, signals.progress.emit, cancel.is_set)
    except ReportCancelled:
        signals.cancelled.emit()
    except Exception as exc:  # noqa: BLE001 - kazdy blad API ma trafic do etykiety
        signals.failed.emit(str(exc) or exc.__class__.__name__)
    else:
        if cancel.is_set():
            signals.cancelled.emit()
        else:
            signals.finished.emit(report)


def _py(q: QDate) -> date:
    return date(q.year(), q.month(), q.day())


def _fmt(d: date) -> str:
    return d.strftime("%d.%m.%Y")


class ReportDialog(QDialog):
    def __init__(
        self,
        build_fn: BuildFn,
        folders_default: Sequence[str],
        available_folders: Sequence[str],
        clock: Clock = utc_now,
        synchronous: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Raporty")
        self.resize(900, 650)
        self._build_fn = build_fn
        self._synchronous = synchronous
        self._clock = clock
        self._report: Report | None = None
        self._cancel = threading.Event()
        self._worker: _Worker | None = None
        self._running = False

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(MODES)
        today = to_local(clock()).date()
        self.from_edit = self._date_edit(today)
        self.to_edit = self._date_edit(today)
        self.from_label = QLabel("Data:")
        self.to_label = QLabel("do:")
        self.range_label = QLabel()
        self.folder_boxes: list[QCheckBox] = []
        names = list(available_folders) or list(folders_default)
        for extra in folders_default:
            if extra not in names:
                names.append(extra)
        for name in names:
            cb = QCheckBox(name)
            cb.setChecked(name in folders_default)
            cb.toggled.connect(self._update_state)
            self.folder_boxes.append(cb)

        self.generate_button = QPushButton("Generuj")
        self.cancel_button = QPushButton("Anuluj")
        self.cancel_button.setVisible(False)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.verdict_label = QLabel("")
        self.preview = QTabWidget()
        self.tables: dict[str, QTableWidget] = {}
        for title in SECTION_TABS.values():
            table = QTableWidget()
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            self.tables[title] = table
            self.preview.addTab(table, title)
        self.save_csv_button = QPushButton("Zapisz CSV")
        self.save_xlsx_button = QPushButton("Zapisz Excel")
        self.save_csv_button.setEnabled(False)
        self.save_xlsx_button.setEnabled(False)

        top = QHBoxLayout()
        for w in (
            QLabel("Okres:"), self.mode_combo, self.from_label, self.from_edit,
            self.to_label, self.to_edit, self.range_label,
        ):  # fmt: skip
            top.addWidget(w)
        top.addStretch(1)
        folder_box = QGroupBox("Foldery")
        fl = QHBoxLayout(folder_box)
        for cb in self.folder_boxes:
            fl.addWidget(cb)
        fl.addStretch(1)
        actions = QHBoxLayout()
        actions.addWidget(self.generate_button)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.progress, 1)
        save = QHBoxLayout()
        save.addWidget(self.save_csv_button)
        save.addWidget(self.save_xlsx_button)
        save.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(folder_box)
        layout.addLayout(actions)
        layout.addWidget(self.status_label)
        layout.addWidget(self.verdict_label)
        layout.addWidget(self.preview, 1)
        layout.addLayout(save)

        self.mode_combo.currentIndexChanged.connect(self._update_state)
        self.from_edit.dateChanged.connect(self._update_state)
        self.to_edit.dateChanged.connect(self._update_state)
        self.generate_button.clicked.connect(self.generate)
        self.cancel_button.clicked.connect(self.cancel)
        self.save_csv_button.clicked.connect(self._choose_csv)
        self.save_xlsx_button.clicked.connect(self._choose_xlsx)
        self._update_state()

    @staticmethod
    def _date_edit(d: date) -> QDateEdit:
        edit = QDateEdit(QDate(d.year, d.month, d.day))
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("dd.MM.yyyy")
        return edit

    # --- okres ---
    def _from_date(self) -> date:
        return _py(self.from_edit.date())

    def _to_date(self) -> date:
        return _py(self.to_edit.date())

    def selected_folders(self) -> list[str]:
        return [cb.text() for cb in self.folder_boxes if cb.isChecked()]

    def current_period(self) -> Period | None:
        """Okres wg wyboru; None gdy zakres jest bledny."""
        mode, d = self.mode_combo.currentText(), self._from_date()
        if mode == "Dzień":
            return period_day(d)
        if mode == "Tydzień":
            return period_week(d)
        if mode == "Miesiąc":
            return period_month(d)
        if self._to_date() < d:
            return None
        return period_custom(d, self._to_date())

    def _update_state(self) -> None:
        custom = self.mode_combo.currentText() == "Zakres"
        self.to_label.setVisible(custom)
        self.to_edit.setVisible(custom)
        self.from_label.setText("Od:" if custom else "Data:")
        period = self.current_period()
        if period is None:
            self.range_label.setText("")
            self.status_label.setText(RANGE_ERROR)
        else:
            self.range_label.setText(f"{_fmt(period.start_date)} – {_fmt(period.end_date)}")
            if self.status_label.text() == RANGE_ERROR:
                self.status_label.setText("")
        self.generate_button.setEnabled(
            period is not None and not self._running and bool(self.selected_folders())
        )

    # --- generowanie ---
    @property
    def report(self) -> Report | None:
        return self._report

    def generate(self) -> None:
        period = self.current_period()
        if period is None or self._running:
            return
        self._running = True
        self._cancel.clear()
        self._report = None
        self.verdict_label.setText("")
        self.save_csv_button.setEnabled(False)
        self.save_xlsx_button.setEnabled(False)
        self.status_label.setText("Generowanie raportu…")
        self.progress.setRange(0, 0)
        self.progress.setVisible(True)
        self.cancel_button.setVisible(True)
        self.generate_button.setEnabled(False)
        worker = _Worker(self._build_fn, period, self.selected_folders(), self._cancel)
        self._worker = worker
        s = worker.signals
        s.progress.connect(self._on_progress)
        s.finished.connect(self._on_finished)
        s.failed.connect(self._on_failed)
        s.cancelled.connect(self._on_cancelled)
        if self._synchronous:
            worker.run()
        else:
            QThreadPool.globalInstance().start(worker)

    def cancel(self) -> None:
        self._cancel.set()
        self.cancel_button.setEnabled(False)
        self.status_label.setText("Anulowanie…")

    def _end_run(self) -> None:
        self._running = False
        self._worker = None
        self.progress.setVisible(False)
        self.cancel_button.setVisible(False)
        self.cancel_button.setEnabled(True)
        self._update_state()

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)

    def _on_failed(self, message: str) -> None:
        self._end_run()
        self.status_label.setText(f"Nie udało się wygenerować raportu: {message}")

    def _on_cancelled(self) -> None:
        self._end_run()
        self.status_label.setText(CANCELLED_TEXT)

    def _on_finished(self, report: Report) -> None:
        self._end_run()
        self._report = report
        self.status_label.setText("Raport gotowy.")
        ok = report.summary.verdict_ok
        self.verdict_label.setText(verdict_text(ok))
        self.verdict_label.setStyleSheet(OK_STYLE if ok else BAD_STYLE)
        for fname, (header, rows) in report_tables(report).items():
            table = self.tables[SECTION_TABS[fname]]
            table.clear()
            table.setColumnCount(len(header))
            table.setHorizontalHeaderLabels(header)
            table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                for c, value in enumerate(row):
                    table.setItem(r, c, QTableWidgetItem("" if value is None else str(value)))
            table.resizeColumnsToContents()
        self.save_csv_button.setEnabled(True)
        self.save_xlsx_button.setEnabled(True)

    # --- zapis ---
    def _choose_csv(self) -> None:
        self._choose("csv", "Archiwum ZIP (*.zip)", self.save_csv)

    def _choose_xlsx(self) -> None:
        self._choose("xlsx", "Excel (*.xlsx)", self.save_xlsx)

    def _choose(self, ext: str, flt: str, saver: Callable[[str], None]) -> None:
        if self._report is None:
            return
        name = report_filename(self._report.period, "zip" if ext == "csv" else ext)
        path, _ = QFileDialog.getSaveFileName(self, "Zapisz raport", name, flt)
        if path:
            saver(path)

    def save_csv(self, path: str) -> None:
        """Zapisuje ZIP z 5 plikami CSV."""
        self._save(path, export_report_csv_zip)

    def save_xlsx(self, path: str) -> None:
        self._save(path, export_report_xlsx)

    def _save(self, path: str, exporter: Callable[[Report, str], None]) -> None:
        if self._report is None:
            self.status_label.setText("Najpierw wygeneruj raport.")
            return
        try:
            exporter(self._report, path)
        except OSError as exc:
            self.status_label.setText(f"Nie udało się zapisać pliku: {exc}")
        else:
            self.status_label.setText(f"Zapisano: {path}")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._cancel.set()
        super().closeEvent(event)
