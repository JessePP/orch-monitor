from pathlib import Path

from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from orch_monitor.api.auth import AuthError
from orch_monitor.api.folders import Folder
from orch_monitor.config.settings import NotificationSettings, Settings, load_settings
from orch_monitor.ui.settings_dialog import SECRET_MASK, SettingsDialog

FOLDERS = [Folder(1, "Finance", "Finance"), Folder(2, "Invoices", "Finance/Invoices")]


def _settings() -> Settings:
    return Settings(
        organization="acme", tenant="Default", client_id="cid", folders=["Finance"],
        refresh_interval_s=30, long_job_threshold_min=90,
        notifications=NotificationSettings(robot_down=False, queue_ae=True, queue_be=True,
                                           job_faulted=False),
    )  # fmt: skip


def _dlg(qtbot: QtBot, tmp_path: Path, test_fn=None, saved=None, secret=True, stored=None):  # type: ignore[no-untyped-def]
    store = stored if stored is not None else {}
    d = SettingsDialog(
        _settings(),
        test_fn or (lambda *a: FOLDERS),
        saved or (lambda s: None),
        secret_exists=secret,
        settings_path=tmp_path / "s.toml",
        load_secret=lambda cid: "TAJNE",
        store_secret=lambda cid, sec: store.__setitem__(cid, sec),
        synchronous=True,
    )
    qtbot.addWidget(d)
    return d


def test_TC_15_1_fields_filled_secret_masked(qtbot: QtBot, tmp_path: Path) -> None:
    d = _dlg(qtbot, tmp_path)
    assert (d.org_edit.text(), d.tenant_edit.text(), d.client_id_edit.text()) == (
        "acme", "Default", "cid")  # fmt: skip
    assert d.interval_spin.value() == 30 and d.threshold_spin.value() == 90
    assert d.secret_edit.text() == SECRET_MASK and "TAJNE" not in d.secret_edit.text()
    assert d.secret_edit.echoMode().name == "Password"
    assert d.selected_folders() == ["Finance"]
    assert not d.cb_robot_down.isChecked() and d.cb_queue_be.isChecked()


def test_TC_15_2_test_connection_success(qtbot: QtBot, tmp_path: Path) -> None:
    seen: list[tuple[str, ...]] = []

    def ok(*a: str) -> list[Folder]:
        seen.append(a)
        return FOLDERS

    d = _dlg(qtbot, tmp_path, ok)
    d.test_button.click()
    assert d.connection_label.text().startswith("Połączono")
    assert seen == [("acme", "Default", "cid", "TAJNE")]  # maska -> prawdziwy sekret z magazynu
    items = d.folder_items()
    assert items == [("Finance", True), ("Finance/Invoices", False)]
    assert d.folders_list.item(0).checkState() == Qt.CheckState.Checked


def test_TC_15_3_test_connection_401(qtbot: QtBot, tmp_path: Path) -> None:
    def bad(*a: str) -> list[Folder]:
        raise AuthError("Logowanie odrzucone (HTTP 401).", "credentials")

    d = _dlg(qtbot, tmp_path, bad)
    d.secret_edit.setText("SUPERSEKRET")
    d.test_button.click()
    assert d.connection_label.text() == "Błędne dane logowania"
    assert "SUPERSEKRET" not in d.connection_label.text()

    def net(*a: str) -> list[Folder]:
        raise AuthError("Blad polaczenia", "network")

    d2 = _dlg(qtbot, tmp_path, net)
    d2.test_button.click()
    assert d2.connection_label.text().startswith("Błąd sieci")


def test_TC_15_4_save_new_interval(qtbot: QtBot, tmp_path: Path) -> None:
    saved: list[Settings] = []
    store: dict[str, str] = {}
    d = _dlg(qtbot, tmp_path, saved=saved.append, stored=store)
    d.interval_spin.setValue(60)
    d.save_button.click()
    assert saved[0].refresh_interval_s == 60
    assert load_settings(tmp_path / "s.toml").refresh_interval_s == 60
    assert store == {}  # sekret niezmieniony
    assert "TAJNE" not in (tmp_path / "s.toml").read_text()


def test_TC_15_4_changed_secret_stored(qtbot: QtBot, tmp_path: Path) -> None:
    store: dict[str, str] = {}
    d = _dlg(qtbot, tmp_path, stored=store)
    d.secret_edit.setText("NOWY")
    d.save()
    assert store == {"cid": "NOWY"}
    assert "NOWY" not in (tmp_path / "s.toml").read_text()


def test_TC_15_5_zero_interval_disables_save(qtbot: QtBot, tmp_path: Path) -> None:
    d = _dlg(qtbot, tmp_path)
    d.interval_spin.setValue(0)
    assert not d.save_button.isEnabled()
    assert d.interval_error.text() != ""
    assert d.save() is False
    d.interval_spin.setValue(10)
    assert d.save_button.isEnabled() and d.interval_error.text() == ""
