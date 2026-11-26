"""Composition root: sklada klienta, harmonogram, okno i zasobnik."""

from __future__ import annotations

import sys
import threading
from collections.abc import Sequence
from datetime import timedelta

import httpx
from PySide6.QtWidgets import QApplication

from orch_monitor.api.auth import TokenProvider
from orch_monitor.api.client import OrchestratorClient
from orch_monitor.api.folders import Folder, list_folders, resolve_folders
from orch_monitor.clock import Clock, utc_now
from orch_monitor.config.secret import get_secret
from orch_monitor.config.settings import Settings, SettingsError, load_settings
from orch_monitor.refresh.scheduler import RefreshScheduler
from orch_monitor.refresh.snapshot import DataFetcher, Snapshot
from orch_monitor.services.queue_details import DetailsResult, Kind, fetch_queue_details
from orch_monitor.services.queues import QueueRow
from orch_monitor.ui.bridge import SnapshotBridge
from orch_monitor.ui.main_window import MainWindow
from orch_monitor.ui.settings_dialog import SettingsDialog
from orch_monitor.ui.tray import TrayIcon


def is_configured(settings: Settings, secret: str | None) -> bool:
    return bool(settings.organization and settings.tenant and settings.client_id and secret)


def test_connection(org: str, tenant: str, client_id: str, secret: str) -> list[Folder]:
    """Probuje pobrac token i liste folderow (AuthError przy bledzie)."""
    with httpx.Client(timeout=20.0) as http:
        client = OrchestratorClient(org, tenant, TokenProvider(org, client_id, secret, http), http)
        return list_folders(client)


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
                    settings.organization, settings.tenant, tokens, http
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
        if fetcher is None:
            available = list_folders(client)
            folders, _warnings = resolve_folders(settings.folders, available)
            minutes = settings.long_job_threshold_min
            fetcher = DataFetcher(client, folders, self._clock, lambda: timedelta(minutes=minutes))
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

    def close(self) -> None:
        if self._http is not None:
            self._http.close()


class App:
    """Sklada calosc. Punkty rozszerzen dla kolejnych krokow:

    - powiadomienia (krok 17): podlacz `self.bridge.snapshot_ready.connect(...)`, a do tray
      dodaj wyciszenie przez `self.tray.add_menu_section(...)` i `self.tray.show_message(...)`;
    - okno raportu (krok 20) i „Otworz folder logow” (krok 21): `self.tray.add_menu_action(...)`.
    """

    def __init__(self, qapp: QApplication, settings: Settings, clock: Clock = utc_now) -> None:
        self.qapp = qapp
        self.clock = clock
        self.settings = settings
        self.backend = Backend(settings, clock)
        self.window = MainWindow(clock, details_provider=self.backend.details)
        self.bridge = SnapshotBridge()
        self.bridge.snapshot_ready.connect(self.window.apply_snapshot)
        self.scheduler = RefreshScheduler(self.backend.fetch, settings.refresh_interval_s, clock)
        self.scheduler.subscribe(self.bridge.publish)
        self.tray = TrayIcon(
            self.window.show_and_raise, self.open_settings, self.quit, parent=self.window
        )
        self.settings_dialog: SettingsDialog | None = None

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
    try:
        settings = load_settings()
    except SettingsError:
        settings = Settings()
    app = App(qapp, settings)
    app.start()
    return qapp.exec()
