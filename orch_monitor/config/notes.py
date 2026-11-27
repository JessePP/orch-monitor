"""Wspolne notatki do bledow (element kolejki AE/BE, job Faulted). Bez Qt.

Notatki leza w folderze (domyslnie lokalnym, zwykle wspolnym folderze sieciowym zespolu):

    <folder>/<tenant>/<klucz bledu>/<czas>_<autor>_<losowe>.json

Kazda notatka to osobny plik, wiec dwie osoby piszace jednoczesnie nigdy nie nadpisza sobie
tekstu (brak odczytu-modyfikacji-zapisu wspolnego pliku). Aplikacja dalej tylko czyta
z Orchestratora: notatki nie trafiaja do Orchestratora.
"""

from __future__ import annotations

import getpass
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from orch_monitor.clock import Clock, utc_now
from orch_monitor.config.settings import default_settings_path

ErrorKind = Literal["queue_item", "job"]
_PREFIX: dict[ErrorKind, str] = {"queue_item": "qi", "job": "job"}
MAX_TEXT = 10_000
_UNSAFE = re.compile(r"[^0-9A-Za-z._-]+")


class NotesError(Exception):
    """Blad dostepu do notatek (komunikat po polsku)."""


def safe_name(text: str, fallback: str = "x") -> str:
    """Nazwa bezpieczna jako fragment sciezki (bez separatorow, kropek na poczatku itp.)."""
    cleaned = _UNSAFE.sub("_", text).strip("._")
    return cleaned[:60] or fallback


def current_user() -> str:
    """Login Windows (lub systemu) jako autor notatek; aplikacja nie ma jeszcze logowania."""
    try:
        return getpass.getuser() or "nieznany"
    except Exception:  # noqa: BLE001
        return "nieznany"


def default_notes_dir() -> Path:
    """Lokalny folder notatek obok ustawien (gdy nie ustawiono folderu wspolnego)."""
    return default_settings_path().parent / "notes"


@dataclass(frozen=True)
class ErrorRef:
    """Blad, ktorego dotycza notatki. `title` i `detail` tylko do wyswietlenia i kontekstu."""

    kind: ErrorKind
    error_id: int
    title: str
    detail: str = ""

    @property
    def key(self) -> str:
        return f"{_PREFIX[self.kind]}-{self.error_id}"


@dataclass(frozen=True)
class Note:
    note_id: str  # nazwa pliku bez .json
    author: str
    created_at: datetime
    text: str


class NotesStore:
    """Notatki w folderze `base / <tenant>`. `base=None` = folder lokalny."""

    def __init__(
        self,
        base: Path | None = None,
        tenant: str = "",
        author: str | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self.author = author or current_user()
        self._clock = clock
        self.shared = False
        self.base = default_notes_dir()
        self.root = self.base
        self.configure(base, tenant)

    def configure(self, base: Path | None, tenant: str = "") -> None:
        """Zmiana folderu (po zapisie ustawien) bez tworzenia nowego obiektu."""
        self.shared = base is not None
        self.base = base if base is not None else default_notes_dir()
        self.root = self.base / safe_name(tenant, "domyslny")

    @property
    def location(self) -> str:
        return str(self.base)

    def _dir(self, key: str) -> Path:
        return self.root / safe_name(key)

    def _fail(self, action: str, exc: OSError) -> NotesError:
        reason = exc.strerror or type(exc).__name__
        return NotesError(f"Nie udało się {action} notatek w folderze {self.base}: {reason}")

    def notes_for(self, key: str) -> list[Note]:
        """Notatki do bledu, od najstarszej. Brak folderu = brak notatek; zle pliki pomijane."""
        folder = self._dir(key)
        try:
            files = sorted(folder.glob("*.json")) if folder.is_dir() else []
        except OSError as exc:
            raise self._fail("odczytać", exc) from exc
        notes: list[Note] = []
        for path in files:
            note = _read_note(path)
            if note is not None:
                notes.append(note)
        notes.sort(key=lambda n: (n.created_at, n.note_id))
        return notes

    def add(self, ref: ErrorRef, text: str) -> Note:
        text = text.strip()
        if not text:
            raise NotesError("Notatka jest pusta")
        if len(text) > MAX_TEXT:
            raise NotesError(f"Notatka jest za długa (maks. {MAX_TEXT} znaków)")
        when = self._clock()
        note_id = (
            f"{when.strftime('%Y%m%dT%H%M%S')}_{safe_name(self.author)}_{uuid.uuid4().hex[:8]}"
        )
        payload = {
            "version": 1,
            "author": self.author,
            "created_at": when.isoformat(),
            "text": text,
            "error": {
                "kind": ref.kind,
                "id": ref.error_id,
                "title": ref.title,
                "detail": ref.detail,
            },
        }
        folder = self._dir(ref.key)
        path = folder / f"{note_id}.json"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            tmp = folder / f".{note_id}.tmp"
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            raise self._fail("zapisać", exc) from exc
        return Note(note_id, self.author, when, text)

    def can_delete(self, note: Note) -> bool:
        return note.author.casefold() == self.author.casefold()

    def delete(self, key: str, note: Note) -> None:
        """Usuwa wlasna notatke; cudzej nie (NotesError)."""
        if not self.can_delete(note):
            raise NotesError("Można usunąć tylko własną notatkę")
        try:
            (self._dir(key) / f"{safe_name(note.note_id)}.json").unlink(missing_ok=True)
        except OSError as exc:
            raise self._fail("usunąć", exc) from exc

    def counts(self) -> dict[str, int]:
        """Liczba notatek dla kazdego bledu, ktory je ma (jedno przejscie po folderze)."""
        try:
            if not self.root.is_dir():
                return {}
            out: dict[str, int] = {}
            for sub in self.root.iterdir():
                if sub.is_dir():
                    n = sum(1 for _ in sub.glob("*.json"))
                    if n:
                        out[sub.name] = n
            return out
        except OSError as exc:
            raise self._fail("odczytać", exc) from exc


def _read_note(path: Path) -> Note | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        when = datetime.fromisoformat(str(data["created_at"]))
        if when.tzinfo is None:
            return None
        return Note(path.stem, str(data["author"]), when, str(data["text"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None
