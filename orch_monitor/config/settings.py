"""Ustawienia aplikacji (TOML w profilu uzytkownika). Bez sekretu."""

from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError


class SettingsError(Exception):
    """Blad odczytu lub walidacji ustawien (komunikat po polsku)."""


class NotificationSettings(BaseModel):
    robot_down: bool = True
    queue_ae: bool = True
    queue_be: bool = False
    job_faulted: bool = True


class Settings(BaseModel):
    organization: str = ""
    tenant: str = ""
    client_id: str = ""
    folders: list[str] = Field(default_factory=list)
    refresh_interval_s: int = Field(default=30, gt=0)
    long_job_threshold_min: int = Field(default=120, gt=0)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)


def default_settings_path() -> Path:
    """Sciezka ustawien: %APPDATA%\\OrchMonitor (Windows) lub ~/.config/orch-monitor."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "OrchMonitor" / "settings.toml"
    return Path.home() / ".config" / "orch-monitor" / "settings.toml"


def _format_validation_error(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        field = ".".join(str(p) for p in err["loc"]) or "(ustawienia)"
        parts.append(f"{field}: {err['msg']}")
    return "Niepoprawne ustawienia: " + "; ".join(parts)


def parse_settings(data: dict[str, Any]) -> Settings:
    try:
        return Settings.model_validate(data)
    except ValidationError as exc:
        raise SettingsError(_format_validation_error(exc)) from exc


def load_settings(path: Path | None = None) -> Settings:
    """Wczytuje ustawienia; brak pliku = domyslne; blad = SettingsError."""
    p = path or default_settings_path()
    if not p.exists():
        return Settings()
    try:
        with p.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise SettingsError(f"Uszkodzony plik ustawien {p}: {exc}") from exc
    except OSError as exc:
        raise SettingsError(f"Nie mozna odczytac pliku ustawien {p}: {exc}") from exc
    return parse_settings(data)


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    raise TypeError(f"Nieobslugiwany typ TOML: {type(value)!r}")


def dumps_toml(data: dict[str, Any]) -> str:
    """Prosty serializer TOML: skalary i listy na gorze, potem tabele jednopoziomowe."""
    lines: list[str] = []
    tables: list[tuple[str, dict[str, Any]]] = []
    for key, value in data.items():
        if isinstance(value, dict):
            tables.append((key, value))
        else:
            lines.append(f"{key} = {_toml_value(value)}")
    for name, table in tables:
        lines.append("")
        lines.append(f"[{name}]")
        for key, value in table.items():
            lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines) + "\n"


def save_settings(settings: Settings, path: Path | None = None) -> None:
    """Zapisuje ustawienia atomowo. Sekretu tu nie ma."""
    p = path or default_settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(dumps_toml(settings.model_dump()), encoding="utf-8")
    tmp.replace(p)


def reset_to_defaults(path: Path | None = None) -> Settings:
    """Odkłada uszkodzony plik jako .bak i zapisuje ustawienia domyslne."""
    p = path or default_settings_path()
    if p.exists():
        p.replace(p.with_suffix(p.suffix + ".bak"))
    settings = Settings()
    save_settings(settings, p)
    return settings
