"""Snapshot danych i DataFetcher budujacy go z serwisow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from orch_monitor.api.client import ApiError, OrchestratorClient
from orch_monitor.api.folders import Folder
from orch_monitor.clock import Clock, day_window, to_local
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
    faulted_today: list[FaultedJob] = field(default_factory=list)  # od najnowszego


def _join(errs: dict[str, str]) -> str:
    return "; ".join(f"{k}: {v}" for k, v in errs.items())


class DataFetcher:
    def __init__(
        self,
        client: OrchestratorClient,
        folders: list[Folder],
        clock: Clock,
        threshold: Callable[[], timedelta] = lambda: timedelta(minutes=120),
        warnings: dict[str, str] | None = None,
        track_faulted_today: bool = False,
    ) -> None:
        self._client = client
        self._folders = folders
        self._clock = clock
        self._threshold = threshold
        self._last_faulted_check: datetime | None = None
        self._warnings = dict(warnings or {})
        self._yesterday_cache: queues_svc.YesterdayCache = {}
        self._track_today = track_faulted_today
        self._faulted_today: dict[int, FaultedJob] = {}

    def fetch(self) -> Snapshot:
        started = to_local(self._clock())
        c, f = self._client, self._folders
        robots = fetch_robots(c, f)
        run, run_err = jobs_svc.running(c, f, self._clock, self._threshold())
        pend, pend_err = jobs_svc.pending(c, f, self._clock)
        queues, q_err = queues_svc.today_queues(c, f, self._clock, self._yesterday_cache)
        faulted: list[FaultedJob] = []
        f_err: dict[str, str] = {}
        day_start = day_window(started.date())[0]
        if self._last_faulted_check is not None:
            faulted, f_err = jobs_svc.faulted_since(c, f, self._last_faulted_check)
        elif self._track_today:
            # pierwsze pobranie: dzisiejsze Faulted do listy, bez powiadomien (jak dotad)
            today, f_err = jobs_svc.faulted_since(c, f, day_start)
            self._faulted_today = {j.job_id: j for j in today}
        if not f_err:
            self._last_faulted_check = started
        for job in faulted:
            self._faulted_today[job.job_id] = job
        self._faulted_today = {
            k: j
            for k, j in self._faulted_today.items()
            if j.end_time is not None and j.end_time >= day_start
        }
        errors = {**self._warnings}
        errors |= {
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
            faulted_today=sorted(
                self._faulted_today.values(),
                key=lambda j: j.end_time or day_start,
                reverse=True,
            ),
        )


__all__ = ["ApiError", "DataFetcher", "Snapshot"]
