"""Okno ustawien."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from orch_monitor.api.auth import AuthError
from orch_monitor.api.folders import Folder
from orch_monitor.config.secret import get_secret, set_secret
from orch_monitor.config.settings import NotificationSettings, Settings, save_settings

SECRET_MASK = "••••••••"
TestConnection = Callable[[str, str, str, str], list[Folder]]


class _Signals(QObject):
    done = Signal(int, object)
    failed = Signal(int, str, str)  # token, kind, message


class _Worker(QRunnable):
    def __init__(self, token: int, fn: Callable[[], list[Folder]]) -> None:
        super().__init__()
        self.token = token
        self.fn = fn
        self.signals = _Signals()

    def run(self) -> None:
        try:
            folders = self.fn()
        except AuthError as exc:
            self.signals.failed.emit(self.token, exc.kind, str(exc))
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(self.token, "network", type(exc).__name__)
        else:
            self.signals.done.emit(self.token, folders)


class SettingsDialog(QDialog):
    connection_tested = Signal()

    def __init__(
        self,
        settings: Settings,
        test_connection: TestConnection,
        on_saved: Callable[[Settings], None],
        secret_exists: bool | None = None,
        settings_path: Path | None = None,
        load_secret: Callable[[str], str | None] = get_secret,
        store_secret: Callable[[str, str], None] = set_secret,
        parent: QWidget | None = None,
        synchronous: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ustawienia")
        self.resize(480, 600)
        self._test_connection = test_connection
        self._on_saved = on_saved
        self._path = settings_path
        self._load_secret = load_secret
        self._store_secret = store_secret
        self._sync = synchronous
        self._token = 0
        self._workers: list[_Worker] = []
        self._orig_client_id = settings.client_id
        if secret_exists is None:
            try:
                secret_exists = bool(settings.client_id and load_secret(settings.client_id))
            except Exception:  # noqa: BLE001
                secret_exists = False
        self._secret_stored = secret_exists

        self.org_edit = QLineEdit(settings.organization)
        self.tenant_edit = QLineEdit(settings.tenant)
        self.client_id_edit = QLineEdit(settings.client_id)
        self.secret_edit = QLineEdit(SECRET_MASK if secret_exists else "")
        self.secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.test_button = QPushButton("Testuj połączenie")
        self.connection_label = QLabel("")
        self.connection_label.setWordWrap(True)
        self.folders_list = QListWidget()
        for name in settings.folders:
            self._add_folder(name, True)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(0, 86400)
        self.interval_spin.setSuffix(" s")
        self.interval_spin.setValue(settings.refresh_interval_s)
        self.interval_error = QLabel("")
        self.interval_error.setStyleSheet("color: #b71c1c;")
        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(0, 100000)
        self.threshold_spin.setSuffix(" min")
        self.threshold_spin.setValue(settings.long_job_threshold_min)
        self.threshold_error = QLabel("")
        self.threshold_error.setStyleSheet("color: #b71c1c;")
        n = settings.notifications
        self.cb_robot_down = QCheckBox("Robot przestał odpowiadać")
        self.cb_robot_down.setChecked(n.robot_down)
        self.cb_queue_ae = QCheckBox("Nowe AE w kolejce")
        self.cb_queue_ae.setChecked(n.queue_ae)
        self.cb_queue_be = QCheckBox("Nowe BE w kolejce")
        self.cb_queue_be.setChecked(n.queue_be)
        self.cb_job_faulted = QCheckBox("Job zakończony błędem (Faulted)")
        self.cb_job_faulted.setChecked(n.job_faulted)
        self.notes_edit = QLineEdit(settings.notes_folder)
        self.notes_edit.setPlaceholderText(r"np. \\serwer\zespol\OrchMonitor; pusty = lokalnie")
        self.notes_edit.setToolTip(
            "Wspólny folder sieciowy, w którym cały zespół trzyma notatki do błędów"
        )
        self.notes_browse = QPushButton("Wybierz…")
        self.save_status = QLabel("")
        self.save_status.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Organizacja", self.org_edit)
        form.addRow("Tenant", self.tenant_edit)
        form.addRow("Client ID", self.client_id_edit)
        form.addRow("Client secret", self.secret_edit)
        form.addRow("Interwał odświeżania", self.interval_spin)
        form.addRow("", self.interval_error)
        form.addRow("Próg długiego joba", self.threshold_spin)
        form.addRow("", self.threshold_error)
        notes_row = QHBoxLayout()
        notes_row.addWidget(self.notes_edit, 1)
        notes_row.addWidget(self.notes_browse)
        form.addRow("Folder notatek zespołu", notes_row)
        test_row = QHBoxLayout()
        test_row.addWidget(self.test_button)
        test_row.addWidget(self.connection_label, 1)
        self.buttons = QDialogButtonBox()
        self.save_button = self.buttons.addButton("Zapisz", QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel_button = self.buttons.addButton(
            "Anuluj", QDialogButtonBox.ButtonRole.RejectRole
        )
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addLayout(test_row)
        lay.addWidget(QLabel("Monitorowane foldery"))
        lay.addWidget(self.folders_list, 1)
        lay.addWidget(QLabel("Powiadomienia"))
        for cb in (self.cb_robot_down, self.cb_queue_ae, self.cb_queue_be, self.cb_job_faulted):
            lay.addWidget(cb)
        lay.addWidget(self.save_status)
        lay.addWidget(self.buttons)

        self.test_button.clicked.connect(self.test_connection)
        self.notes_browse.clicked.connect(self._browse_notes)
        self.save_button.clicked.connect(self.save)
        self.cancel_button.clicked.connect(self.reject)
        self.interval_spin.valueChanged.connect(self._validate)
        self.threshold_spin.valueChanged.connect(self._validate)
        self._validate()

    def _browse_notes(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Folder notatek zespołu", self.notes_edit.text()
        )
        if path:
            self.notes_edit.setText(path)

    # --- foldery ---
    def _add_folder(self, name: str, checked: bool) -> None:
        item = QListWidgetItem(name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.folders_list.addItem(item)

    def folder_items(self) -> list[tuple[str, bool]]:
        out: list[tuple[str, bool]] = []
        for i in range(self.folders_list.count()):
            it = self.folders_list.item(i)
            out.append((it.text(), it.checkState() == Qt.CheckState.Checked))
        return out

    def selected_folders(self) -> list[str]:
        return [name for name, on in self.folder_items() if on]

    def _load_folders(self, folders: list[Folder]) -> None:
        checked = {n.casefold() for n in self.selected_folders()}
        known = {f.full_path.casefold() for f in folders} | {f.name.casefold() for f in folders}
        self.folders_list.clear()
        for f in folders:
            on = f.full_path.casefold() in checked or f.name.casefold() in checked
            self._add_folder(f.full_path, on)
        for name in sorted(c for c in checked if c not in known):
            self._add_folder(name, True)

    # --- test polaczenia ---
    def _current_secret(self) -> str:
        text = self.secret_edit.text()
        if text == SECRET_MASK and self._secret_stored:
            try:
                return self._load_secret(self._orig_client_id) or ""
            except Exception:  # noqa: BLE001
                return ""
        return text

    def test_connection(self) -> None:
        self._token += 1
        token = self._token
        org = self.org_edit.text().strip()
        tenant = self.tenant_edit.text().strip()
        cid = self.client_id_edit.text().strip()
        secret = self._current_secret()
        self.connection_label.setText("Łączenie…")
        self.test_button.setEnabled(False)
        if self._sync:
            try:
                folders = self._test_connection(org, tenant, cid, secret)
            except AuthError as exc:
                self._on_failed(token, exc.kind, str(exc))
            except Exception as exc:  # noqa: BLE001
                self._on_failed(token, "network", type(exc).__name__)
            else:
                self._on_done(token, folders)
            return
        worker = _Worker(token, lambda: self._test_connection(org, tenant, cid, secret))
        worker.signals.done.connect(self._on_done)
        worker.signals.failed.connect(self._on_failed)
        self._workers.append(worker)
        QThreadPool.globalInstance().start(worker)

    def _on_done(self, token: int, folders: list[Folder]) -> None:
        if token != self._token:
            return
        self._load_folders(folders)
        self.connection_label.setText(f"Połączono (foldery: {len(folders)})")
        self.test_button.setEnabled(True)
        self.connection_tested.emit()

    def _on_failed(self, token: int, kind: str, message: str) -> None:
        if token != self._token:
            return
        if kind == "credentials":
            self.connection_label.setText("Błędne dane logowania")
        else:
            self.connection_label.setText(f"Błąd sieci: {message}")
        self.test_button.setEnabled(True)
        self.connection_tested.emit()

    # --- walidacja i zapis ---
    def _validate(self) -> bool:
        ok = True
        if self.interval_spin.value() <= 0:
            self.interval_error.setText("Interwał musi być większy niż 0 s")
            ok = False
        else:
            self.interval_error.setText("")
        if self.threshold_spin.value() <= 0:
            self.threshold_error.setText("Próg musi być większy niż 0 min")
            ok = False
        else:
            self.threshold_error.setText("")
        self.save_button.setEnabled(ok)
        return ok

    def build_settings(self) -> Settings:
        return Settings(
            organization=self.org_edit.text().strip(),
            tenant=self.tenant_edit.text().strip(),
            client_id=self.client_id_edit.text().strip(),
            folders=self.selected_folders(),
            refresh_interval_s=self.interval_spin.value(),
            long_job_threshold_min=self.threshold_spin.value(),
            notes_folder=self.notes_edit.text().strip(),
            notifications=NotificationSettings(
                robot_down=self.cb_robot_down.isChecked(),
                queue_ae=self.cb_queue_ae.isChecked(),
                queue_be=self.cb_queue_be.isChecked(),
                job_faulted=self.cb_job_faulted.isChecked(),
            ),
        )

    def save(self) -> bool:
        if not self._validate():
            return False
        settings = self.build_settings()
        text = self.secret_edit.text()
        secret_changed = bool(text) and text != SECRET_MASK
        try:
            save_settings(settings, self._path)
            if secret_changed:
                self._store_secret(settings.client_id, text)
            elif (
                self._secret_stored
                and text == SECRET_MASK
                and settings.client_id != self._orig_client_id
            ):
                # zmieniono client_id: przenosimy zapisany sekret pod nowy klucz
                old = self._load_secret(self._orig_client_id)
                if old:
                    self._store_secret(settings.client_id, old)
        except Exception as exc:  # noqa: BLE001
            self.save_status.setText(f"Nie udało się zapisać ustawień: {type(exc).__name__}")
            return False
        self._on_saved(settings)
        self.accept()
        return True
