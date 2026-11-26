"""Lokalnie zamkniete bledy kolejek (dismissed.json obok ustawien). Bez Qt.

Aplikacja tylko czyta z Orchestratora, wiec „zamkniecie” elementu AE/BE jest lokalne dla
uzytkownika i nie wspoldzielone miedzy developerami.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path

from orch_monitor.clock import Clock, utc_now
from orch_monitor.config.settings import default_settings_path

RETENTION = timedelta(days=60)


class DismissedStore:
    """Zbior item_id zamknietych elementow; plik JSON {"version": 1, "items": {id: ISO}}."""

    def __init__(self, path: Path | None = None, clock: Clock = utc_now) -> None:
        self.path = path or default_settings_path().parent / "dismissed.json"
        self._items: dict[int, datetime] = {}
        self._load()
        self.prune(clock() - RETENTION)

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            raw = data["items"]
            if not isinstance(raw, dict):
                return
            items: dict[int, datetime] = {}
            for key, value in raw.items():
                when = datetime.fromisoformat(str(value))
                if when.tzinfo is None:
                    continue
                items[int(key)] = when
        except (OSError, ValueError, KeyError, TypeError):
            return
        self._items = items

    def _save(self) -> None:
        payload = {
            "version": 1,
            "items": {str(k): v.isoformat() for k, v in sorted(self._items.items())},
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass  # stan w pamieci pozostaje; brak zapisu nie moze wywrocic UI

    @property
    def count(self) -> int:
        return len(self._items)

    def is_dismissed(self, item_id: int) -> bool:
        return item_id in self._items

    def dismiss(self, item_ids: Iterable[int], when: datetime) -> None:
        for item_id in item_ids:
            self._items[int(item_id)] = when
        self._save()

    def restore(self, item_ids: Iterable[int]) -> None:
        for item_id in item_ids:
            self._items.pop(int(item_id), None)
        self._save()

    def prune(self, older_than: datetime) -> int:
        """Usuwa wpisy zamkniete przed `older_than`; zwraca ich liczbe."""
        old = [k for k, v in self._items.items() if v < older_than]
        for k in old:
            del self._items[k]
        if old:
            self._save()
        return len(old)
