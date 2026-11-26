from pathlib import Path
from unittest.mock import MagicMock

import pytest
from helpers import make_snapshot
from pytestqt.qtbot import QtBot

import orch_monitor.app as app_mod
from orch_monitor.app import App
from orch_monitor.config.settings import Settings
from orch_monitor.logging_setup import default_log_dir


@pytest.fixture
def app(qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> App:
    monkeypatch.setenv("HOME", str(tmp_path))
    from PySide6.QtWidgets import QApplication

    qapp = QApplication.instance()
    assert isinstance(qapp, QApplication)
    a = App(qapp, Settings())
    qtbot.addWidget(a.window)
    return a


def test_TC_21_menu_open_logs_folder(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    opened = MagicMock()
    monkeypatch.setattr(app_mod.QDesktopServices, "openUrl", opened)
    action = next(a for a in app.tray.menu.actions() if a.text() == "Otwórz folder logów")
    action.trigger()
    opened.assert_called_once()
    url = opened.call_args.args[0]
    assert url.toLocalFile() == str(default_log_dir())


def test_app_has_reports_entry_and_notifier(app: App) -> None:
    texts = [a.text() for a in app.tray.menu.actions()]
    assert "Raporty…" in texts and "Otwórz folder logów" in texts
    assert app.window.reports_button.text() == "Raporty…"
    # ustawienia powiadomien czytane z biezacych ustawien aplikacji
    app.bridge.snapshot_ready.emit(make_snapshot())
    assert app.engine.muted_until is None
