"""Composition root: sklada klienta, harmonogram, okno i zasobnik."""

from __future__ import annotations

import sys
import threading
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

import httpx
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from orch_monitor.api.auth import AuthError, TokenProvider
from orch_monitor.api.client import OrchestratorClient
from orch_monitor.api.folders import Folder, list_folders, resolve_folders
from orch_monitor.clock import Clock, utc_now
from orch_monitor.config.dismissed import DismissedStore
from orch_monitor.config.notes import NotesStore
from orch_monitor.config.secret import get_secret
from orch_monitor.config.settings import Settings, SettingsError, load_settings
from orch_monitor.logging_setup import (
    default_log_dir,
    log_auth_error,
    make_api_logger,
    setup_logging,
)
from orch_monitor.notify.engine import NotificationEngine
from orch_monitor.refresh.scheduler import RefreshScheduler
from orch_monitor.refresh.snapshot import DataFetcher, Snapshot
from orch_monitor.reports.builder import Cancelled, Progress, build_report
from orch_monitor.reports.model import Report
from orch_monitor.reports.periods import Period
from orch_monitor.services.queue_details import DetailsResult, Kind, fetch_queue_details
from orch_monitor.services.queues import QueueRow
from orch_monitor.ui.bridge import SnapshotBridge
from orch_monitor.ui.main_window import MainWindow
from orch_monitor.ui.notifier import Notifier
from orch_monitor.ui.report_dialog import ReportDialog
from orch_monitor.ui.settings_dialog import SettingsDialog
from orch_monitor.ui.tray import TrayIcon


def is_configured(settings: Settings, secret: str | None) -> bool:
    return bool(settings.organization and settings.tenant and settings.client_id and secret)


def test_connection(org: str, tenant: str, client_id: str, secret: str) -> list[Folder]:
    """Probuje pobrac token i liste folderow (AuthError przy bledzie)."""
    with httpx.Client(timeout=20.0) as http:
        client = OrchestratorClient(org, tenant, TokenProvider(org, client_id, secret, http), http)
        return list_folders(client)


def notes_store_for(settings: Settings, store: NotesStore | None = None) -> NotesStore:
    """Magazyn notatek wg ustawien: wspolny folder albo lokalny (pusty `notes_folder`)."""
    base = Path(settings.notes_folder) if settings.notes_folder.strip() else None
    if store is None:
        return NotesStore(base, settings.tenant)
    store.configure(base, settings.tenant)
    return store


def _safe_secret(client_id: str) -> str | None:
    if not client_id:
        return None
    try:
        return get_secret(client_id)
    except Exception:  # noqa: BLE001 - brak backendu keyring nie moze zabic aplikacji
        return None


class Backend:
    """Klient + fetcher przebudowywane po zapisie ustawien (bez restartu)."""

    def __init__(self, settings: Settings, clock: Clock = utc_now) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._http: httpx.Client | None = None
        self._client: OrchestratorClient | None = None
        self._fetcher: DataFetcher | None = None
        self._folders: list[Folder] = []
        self.settings = settings
        self.configure(settings)

    def configure(self, settings: Settings) -> None:
        secret = _safe_secret(settings.client_id)
        with self._lock:
            old = self._http
            self.settings = settings
            self._fetcher = None
            self._folders = []
            if is_configured(settings, secret):
                assert secret is not None
                http = httpx.Client(timeout=30.0)
                tokens = TokenProvider(
                    settings.organization, settings.client_id, secret, http, clock=self._clock
                )
                self._http = http
                self._client = OrchestratorClient(
                    settings.organization,
                    settings.tenant,
                    tokens,
                    http,
                    on_request=make_api_logger(),
                )
            else:
                self._http = None
                self._client = None
        if old is not None:
            old.close()

    def fetch(self) -> Snapshot:
        with self._lock:
            client, fetcher, settings = self._client, self._fetcher, self.settings
        if client is None:
            raise RuntimeError("Brak konfiguracji połączenia z Orchestratorem")
        try:
            return self._fetch(client, fetcher, settings)
        except AuthError as exc:
            log_auth_error(exc)
            raise

    def _fetch(
        self, client: OrchestratorClient, fetcher: DataFetcher | None, settings: Settings
    ) -> Snapshot:
        if fetcher is None:
            available = list_folders(client)
            if settings.folders:
                folders, missing = resolve_folders(settings.folders, available)
            else:  # brak wyboru w ustawieniach = wszystkie foldery
                folders, missing = list(available), []
            warnings = {"foldery": "; ".join(missing)} if missing else {}
            minutes = settings.long_job_threshold_min
            fetcher = DataFetcher(
                client,
                folders,
                self._clock,
                lambda: timedelta(minutes=minutes),
                warnings,
                track_faulted_today=True,
            )
            with self._lock:
                if self._client is client:
                    self._fetcher, self._folders = fetcher, folders
        return fetcher.fetch()

    def details(self, row: QueueRow, kind: Kind) -> DetailsResult:
        with self._lock:
            client, folders = self._client, list(self._folders)
        folder = next((f for f in folders if f.name == row.folder), None)
        if client is None or folder is None:
            raise RuntimeError("Brak połączenia lub folder nie jest monitorowany")
        return fetch_queue_details(client, row.queue_id, folder.id, self._clock, kind)

    def folder_names(self) -> list[str]:
        with self._lock:
            return [f.name for f in self._folders]

    def build_report(
        self, period: Period, names: list[str], progress: Progress, cancelled: Cancelled
    ) -> Report:
        """Raport dla biezacego klienta; foldery rozwiazywane po nazwach z okna raportu."""
        with self._lock:
            client = self._client
        if client is None:
            raise RuntimeError("Brak konfiguracji połączenia z Orchestratorem")
        try:
            folders, _warnings = resolve_folders(names, list_folders(client))
            return build_report(client, period, folders, progress, cancelled)
        except AuthError as exc:
            log_auth_error(exc)
            raise

    def close(self) -> None:
        if self._http is not None:
            self._http.close()


class App:
    """Sklada calosc. Punkty rozszerzen dla kolejnych krokow:

    - powiadomienia (krok 17): `Notifier` podpiety do `bridge.snapshot_ready`, ustawienia
      powiadomien czytane na biezaco z `self.settings` (zmiana po zapisie obowiazuje od razu);
    - okno raportu (krok 20): pozycja „Raporty…” w trayu i przycisk w oknie glownym;
    - „Otworz folder logow” (krok 21): pozycja w trayu.
    """

    def __init__(self, qapp: QApplication, settings: Settings, clock: Clock = utc_now) -> None:
        self.qapp = qapp
        self.clock = clock
        self.settings = settings
        self.backend = Backend(settings, clock)
        self.dismissed = DismissedStore(clock=clock)
        self.notes = notes_store_for(settings)
        self.window = MainWindow(
            clock, details_provider=self.backend.details, store=self.dismissed, notes=self.notes
        )
        self.bridge = SnapshotBridge()
        self.bridge.snapshot_ready.connect(self.window.apply_snapshot)
        self.scheduler = RefreshScheduler(self.backend.fetch, settings.refresh_interval_s, clock)
        self.scheduler.subscribe(self.bridge.publish)
        self.scheduler.subscribe_error(self.bridge.publish_error)
        self.bridge.error_ready.connect(self.window.show_error)
        self.tray = TrayIcon(
            self.window.show_and_raise, self.open_settings, self.quit, parent=self.window
        )
        self.settings_dialog: SettingsDialog | None = None
        self.report_dialog: ReportDialog | None = None
        self.engine = NotificationEngine(lambda: self.settings.notifications, clock)
        self.notifier = Notifier(self.tray, self.window, self.engine, clock)
        self.bridge.snapshot_ready.connect(self.notifier.on_snapshot)
        self.tray.add_menu_action("Raporty…", self.open_reports)
        self.tray.add_menu_action("Otwórz folder logów", self.open_logs)
        self.window.reports_button.clicked.connect(lambda _c=False: self.open_reports())

    def open_logs(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(default_log_dir())))

    def open_reports(self) -> None:
        names = self.backend.folder_names() or list(self.settings.folders)
        dlg = ReportDialog(
            self.backend.build_report,
            list(self.settings.folders) or names,
            names,
            self.clock,
            parent=self.window,
        )
        self.report_dialog = dlg
        dlg.open()

    def start(self) -> None:
        self.tray.show()
        self.scheduler.start()
        secret = _safe_secret(self.settings.client_id)
        if is_configured(self.settings, secret):
            self.window.show()
        else:
            self.window.show()
            self.open_settings()

    def open_settings(self) -> None:
        dlg = SettingsDialog(
            self.settings, test_connection, self.on_settings_saved, parent=self.window
        )
        self.settings_dialog = dlg
        dlg.open()

    def on_settings_saved(self, settings: Settings) -> None:
        self.settings = settings
        notes_store_for(settings, self.notes)
        self.backend.configure(settings)
        self.scheduler.set_interval(settings.refresh_interval_s)
        self.scheduler.refresh_now()

    def quit(self) -> None:
        self.scheduler.stop()
        self.backend.close()
        self.tray.hide()
        self.window.allow_close = True
        self.qapp.quit()


def run_app(argv: Sequence[str] | None = None) -> int:
    qapp = QApplication.instance() or QApplication(list(argv if argv is not None else sys.argv))
    assert isinstance(qapp, QApplication)
    qapp.setQuitOnLastWindowClosed(False)
    setup_logging()
    try:
        settings = load_settings()
    except SettingsError:
        settings = Settings()
    app = App(qapp, settings)
    app.start()
    return qapp.exec()
