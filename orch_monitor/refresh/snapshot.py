"""Snapshot danych i DataFetcher budujacy go z serwisow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from orch_monitor.api.client import ApiError, OrchestratorClient
from orch_monitor.api.folders import Folder
from orch_monitor.clock import Clock, to_local
from orch_monitor.services import jobs as jobs_svc
from orch_monitor.services import queues as queues_svc
from orch_monitor.services.jobs import FaultedJob, PendingJob, RunningJob
from orch_monitor.services.queues import QueueRow
from orch_monitor.services.robots import RobotsResult, fetch_robots


@dataclass(frozen=True)
class Snapshot:
    fetched_at: datetime
    robots: RobotsResult
    running: list[RunningJob]
    pending: list[PendingJob]
    queues: list[QueueRow]
    faulted_new: list[FaultedJob]
    errors: dict[str, str] = field(default_factory=dict)
    stale: bool = False
    day: date = date(1970, 1, 1)


def _join(errs: dict[str, str]) -> str:
    return "; ".join(f"{k}: {v}" for k, v in errs.items())


class DataFetcher:
    def __init__(
        self,
        client: OrchestratorClient,
        folders: list[Folder],
        clock: Clock,
        threshold: Callable[[], timedelta] = lambda: timedelta(minutes=120),
    ) -> None:
        self._client = client
        self._folders = folders
        self._clock = clock
        self._threshold = threshold
        self._last_faulted_check: datetime | None = None

    def fetch(self) -> Snapshot:
        started = to_local(self._clock())
        c, f = self._client, self._folders
        robots = fetch_robots(c, f)
        run, run_err = jobs_svc.running(c, f, self._clock, self._threshold())
        pend, pend_err = jobs_svc.pending(c, f, self._clock)
        queues, q_err = queues_svc.today_queues(c, f, self._clock)
        faulted: list[FaultedJob] = []
        f_err: dict[str, str] = {}
        if self._last_faulted_check is not None:
            faulted, f_err = jobs_svc.faulted_since(c, f, self._last_faulted_check)
        if not f_err:
            self._last_faulted_check = started
        errors = {
            name: _join(e)
            for name, e in (
                ("robots", robots.errors),
                ("running", run_err),
                ("pending", pend_err),
                ("queues", q_err),
                ("faulted", f_err),
            )
            if e
        }
        return Snapshot(
            fetched_at=started,
            robots=robots,
            running=run,
            pending=pend,
            queues=queues,
            faulted_new=faulted,
            errors=errors,
            stale=False,
            day=started.date(),
        )


__all__ = ["ApiError", "DataFetcher", "Snapshot"]
