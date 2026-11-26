"""Harmonogram odswiezania w osobnym watku (bez Qt)."""

from __future__ import annotations

import dataclasses
import threading
from collections.abc import Callable

from orch_monitor.clock import Clock
from orch_monitor.refresh.snapshot import Snapshot

Wait = Callable[[float], bool]


class RefreshScheduler:
    def __init__(
        self,
        fetch: Callable[[], Snapshot],
        interval_s: float,
        clock: Clock,
        wait: Wait | None = None,
    ) -> None:
        self._fetch = fetch
        self._interval = float(interval_s)
        self._clock = clock
        self._event = threading.Event()
        self._stop = threading.Event()
        self._wait: Wait = wait if wait is not None else self._event.wait
        self._lock = threading.Lock()
        self._subs: list[Callable[[Snapshot], None]] = []
        self._thread: threading.Thread | None = None
        self.last_good: Snapshot | None = None
        self.last_error: str | None = None

    @property
    def interval_s(self) -> float:
        return self._interval

    def set_interval(self, seconds: float) -> None:
        self._interval = float(seconds)
        self._event.set()  # przerywa biezace oczekiwanie, nowy interwal od razu

    def subscribe(self, cb: Callable[[Snapshot], None]) -> None:
        self._subs.append(cb)

    def _publish(self, snap: Snapshot) -> None:
        for cb in list(self._subs):
            try:
                cb(snap)
            except Exception:  # noqa: BLE001 - blad subskrybenta nie moze zabic watku
                continue

    def run_once(self) -> Snapshot | None:
        """Jedno odswiezenie; None gdy poprzednie jeszcze trwa lub nie ma co publikowac."""
        if not self._lock.acquire(blocking=False):
            return None
        try:
            try:
                snap = self._fetch()
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc) or type(exc).__name__
                if self.last_good is None:
                    return None
                snap = dataclasses.replace(
                    self.last_good,
                    stale=True,
                    errors={**self.last_good.errors, "odswiezanie": self.last_error},
                )
            else:
                self.last_error = None
                self.last_good = snap
            self._publish(snap)
            return snap
        finally:
            self._lock.release()

    def refresh_now(self) -> None:
        """Zleca natychmiastowe odswiezenie (ignorowane, gdy jedno juz trwa)."""
        if self._lock.locked():
            return
        self._event.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            if self._stop.is_set():
                break
            self._wait(self._interval)
            self._event.clear()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="refresh", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self._event.set()
        if self._thread is not None:
            self._thread.join(timeout)

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
