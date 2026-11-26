"""Silnik powiadomien: wykrywanie zdarzen przez porownanie kolejnych snapshotow (bez Qt)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Literal

from orch_monitor.clock import WARSAW, Clock, to_local
from orch_monitor.config.settings import NotificationSettings
from orch_monitor.refresh.snapshot import Snapshot
from orch_monitor.services.jobs import FaultedJob

Kind = Literal["robot_down", "queue_ae", "queue_be", "job_faulted"]
Tab = Literal["robots", "jobs", "queues"]

PROBLEM_STATUSES = frozenset({"Disconnected", "Unresponsive"})


@dataclass(frozen=True)
class Notification:
    kind: Kind
    title: str
    message: str
    target_tab: Tab
    key: str


def end_of_day(now: datetime) -> datetime:
    """Koniec biezacej doby (23:59:59 Europe/Warsaw)."""
    return datetime.combine(to_local(now).date(), time(23, 59, 59), tzinfo=WARSAW)


def mute_options(now: datetime) -> list[tuple[str, datetime]]:
    """Opcje menu wyciszenia: (etykieta, do kiedy)."""
    return [
        ("Wycisz na 30 min", now + timedelta(minutes=30)),
        ("Wycisz na 1 h", now + timedelta(hours=1)),
        ("Wycisz na 4 h", now + timedelta(hours=4)),
        ("Wycisz do końca dnia", end_of_day(now)),
    ]


class NotificationEngine:
    def __init__(self, settings_provider: Callable[[], NotificationSettings], clock: Clock) -> None:
        self._settings = settings_provider
        self._clock = clock
        self._prev: Snapshot | None = None
        self._muted_until: datetime | None = None
        self._seen_jobs: set[int] = set()

    # --- wyciszenie ---
    def mute_until(self, dt: datetime | None) -> None:
        self._muted_until = dt

    @property
    def muted_until(self) -> datetime | None:
        return self._muted_until if self.is_muted() else None

    def is_muted(self) -> bool:
        return self._muted_until is not None and self._clock() < self._muted_until

    # --- przetwarzanie ---
    def process(self, snapshot: Snapshot) -> list[Notification]:
        prev, self._prev = self._prev, snapshot
        new_jobs = [j for j in snapshot.faulted_new if j.job_id not in self._seen_jobs]
        self._seen_jobs.update(j.job_id for j in snapshot.faulted_new)
        if prev is None or self.is_muted():
            return []
        cfg = self._settings()
        out: list[Notification] = []
        if cfg.robot_down:
            out += self._robots(prev, snapshot)
        if cfg.queue_ae or cfg.queue_be:
            out += self._queues(prev, snapshot, cfg)
        if cfg.job_faulted:
            out += self._jobs(new_jobs)
        return out

    @staticmethod
    def _robots(prev: Snapshot, curr: Snapshot) -> list[Notification]:
        before = {r.robot_id: r.status for r in prev.robots.robots}
        out: list[Notification] = []
        for r in curr.robots.robots:
            old = before.get(r.robot_id)
            if old is None or old in PROBLEM_STATUSES or r.status not in PROBLEM_STATUSES:
                continue
            text = (
                f"Robot {r.name} rozłączony"
                if r.status == "Disconnected"
                else f"Robot {r.name} nie odpowiada"
            )
            out.append(Notification("robot_down", "Robot", text, "robots", f"robot:{r.robot_id}"))
        return out

    @staticmethod
    def _queues(prev: Snapshot, curr: Snapshot, cfg: NotificationSettings) -> list[Notification]:
        if prev.day != curr.day:
            return []
        before = {(q.queue_id, q.folder): q for q in prev.queues}
        out: list[Notification] = []
        for q in curr.queues:
            old = before.get((q.queue_id, q.folder))
            if old is None:
                continue
            checks: list[tuple[Kind, bool, str, int, int]] = [
                ("queue_ae", cfg.queue_ae, "AE", q.ae - old.ae, q.ae),
                ("queue_be", cfg.queue_be, "BE", q.be - old.be, q.be),
            ]
            for kind, enabled, label, delta, total in checks:
                if enabled and delta > 0:
                    out.append(
                        Notification(
                            kind,
                            f"Kolejka {q.name}",
                            f"{q.name}: {delta} nowe {label}",
                            "queues",
                            f"{kind}:{q.folder}:{q.queue_id}:{total}",
                        )
                    )
        return out

    @staticmethod
    def _jobs(jobs: list[FaultedJob]) -> list[Notification]:
        groups: dict[tuple[str, str], list[int]] = defaultdict(list)
        for j in jobs:
            groups[(j.folder, j.process)].append(j.job_id)
        out: list[Notification] = []
        for (folder, process), ids in groups.items():
            text = (
                f"Proces {process}: Faulted"
                if len(ids) == 1
                else f"Proces {process}: Faulted ({len(ids)} joby)"
            )
            out.append(
                Notification(
                    "job_faulted",
                    "Błąd procesu",
                    text,
                    "jobs",
                    f"job:{folder}:{process}:{min(ids)}",
                )
            )
        return out
