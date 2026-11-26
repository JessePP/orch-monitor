from pathlib import Path

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

from orch_monitor.config import secret
from orch_monitor.config.settings import (
    NotificationSettings,
    Settings,
    SettingsError,
    default_settings_path,
    load_settings,
    reset_to_defaults,
    save_settings,
)


class MemoryKeyring(KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if (service, username) not in self.store:
            raise PasswordDeleteError("brak")
        del self.store[(service, username)]


@pytest.fixture
def mem_keyring() -> MemoryKeyring:
    backend = MemoryKeyring()
    previous = keyring.get_keyring()
    keyring.set_keyring(backend)
    yield backend  # type: ignore[misc]
    keyring.set_keyring(previous)


def test_TC_02_1_missing_file_defaults(tmp_path: Path) -> None:
    s = load_settings(tmp_path / "nie-ma.toml")
    assert s.refresh_interval_s == 30
    assert s.long_job_threshold_min == 120
    assert s.notifications == NotificationSettings()
    assert s.notifications.queue_be is False


def test_TC_02_2_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "sub" / "settings.toml"
    s = Settings(
        organization="acme",
        tenant='Default "Tenant"',
        client_id="abc-123",
        folders=["Finance", "Finance/Invoices", "Zażółć"],
        refresh_interval_s=45,
        long_job_threshold_min=90,
        notifications=NotificationSettings(robot_down=False, queue_be=True),
    )
    save_settings(s, p)
    assert load_settings(p) == s


@pytest.mark.parametrize("field", ["refresh_interval_s", "long_job_threshold_min"])
@pytest.mark.parametrize("value", [0, -5])
def test_TC_02_3_invalid_interval(tmp_path: Path, field: str, value: int) -> None:
    p = tmp_path / "s.toml"
    p.write_text(f"{field} = {value}\n", encoding="utf-8")
    with pytest.raises(SettingsError) as exc:
        load_settings(p)
    assert field in str(exc.value)


def test_TC_02_4_secret_in_keyring_not_in_file(tmp_path: Path, mem_keyring: MemoryKeyring) -> None:
    secret.set_secret("client-1", "TAJNE-HASLO")
    assert mem_keyring.store[("OrchMonitor", "client-1")] == "TAJNE-HASLO"
    assert secret.get_secret("client-1") == "TAJNE-HASLO"
    p = tmp_path / "s.toml"
    save_settings(Settings(client_id="client-1"), p)
    assert "TAJNE-HASLO" not in p.read_text("utf-8")
    assert secret.delete_secret("client-1") is True
    assert secret.get_secret("client-1") is None
    assert secret.delete_secret("client-1") is False


def test_TC_02_5_corrupt_toml(tmp_path: Path) -> None:
    p = tmp_path / "s.toml"
    p.write_text("to nie jest = = toml [[[", encoding="utf-8")
    with pytest.raises(SettingsError) as exc:
        load_settings(p)
    assert "Uszkodzony" in str(exc.value)
    s = reset_to_defaults(p)
    assert s == Settings()
    assert load_settings(p) == Settings()
    assert p.with_suffix(".toml.bak").exists()


def test_default_path_platform(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    assert default_settings_path().parts[-2:] == ("orch-monitor", "settings.toml")
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert default_settings_path() == tmp_path / "OrchMonitor" / "settings.toml"


def test_load_default_path_and_unreadable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "orch_monitor.config.settings.default_settings_path", lambda: tmp_path / "x"
    )
    assert load_settings() == Settings()
    with pytest.raises(SettingsError):
        load_settings(tmp_path)  # katalog zamiast pliku
