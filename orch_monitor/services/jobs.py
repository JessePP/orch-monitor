"""Serwis jobow: Running, Pending i Faulted."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from orch_monitor.api.client import ApiError, OrchestratorClient
from orch_monitor.api.folders import Folder
from orch_monitor.clock import Clock, to_local
from orch_monitor.services._common import iso_z, parse_dt


@dataclass(frozen=True)
class RunningJob:
    job_id: int
    robot: str
    process: str
    machine: str
    start: datetime | None
    source: str
    folder: str
    duration: timedelta
    is_long: bool


@dataclass(frozen=True)
class PendingJob:
    job_id: int
    process: str
    created: datetime | None
    waiting: timedelta
    folder: str


@dataclass(frozen=True)
class FaultedJob:
    job_id: int
    process: str
    robot: str
    end_time: datetime | None
    info: str
    folder: str


def _query(
    client: OrchestratorClient, folders: list[Folder], params: dict[str, Any]
) -> tuple[list[tuple[Folder, dict[str, Any]]], dict[str, str]]:
    rows: list[tuple[Folder, dict[str, Any]]] = []
    errors: dict[str, str] = {}
    for folder in folders:
        try:
            for row in client.get_all("Jobs", params, folder_id=folder.id):
                rows.append((folder, row))
        except ApiError as exc:
            errors[folder.name] = str(exc)
    return rows, errors


def _robot_name(row: dict[str, Any]) -> str:
    return str((row.get("Robot") or {}).get("Name") or "")


def running(
    client: OrchestratorClient, folders: list[Folder], clock: Clock, threshold: timedelta
) -> tuple[list[RunningJob], dict[str, str]]:
    now = to_local(clock())
    rows, errors = _query(client, folders, {"$filter": "State eq 'Running'", "$expand": "Robot"})
    jobs: list[RunningJob] = []
    for folder, row in rows:
        start = parse_dt(row.get("StartTime")) or parse_dt(row.get("CreationTime"))
        duration = max(now - start, timedelta(0)) if start else timedelta(0)
        jobs.append(
            RunningJob(
                job_id=int(row.get("Id", 0)),
                robot=_robot_name(row),
                process=str(row.get("ReleaseName") or ""),
                machine=str(row.get("HostMachineName") or ""),
                start=start,
                source=str(row.get("Source") or ""),
                folder=folder.name,
                duration=duration,
                is_long=duration > threshold,
            )
        )
    jobs.sort(key=lambda j: j.duration, reverse=True)
    return jobs, errors


def pending(
    client: OrchestratorClient, folders: list[Folder], clock: Clock
) -> tuple[list[PendingJob], dict[str, str]]:
    now = to_local(clock())
    rows, errors = _query(client, folders, {"$filter": "State eq 'Pending'"})
    jobs: list[PendingJob] = []
    for folder, row in rows:
        created = parse_dt(row.get("CreationTime"))
        waiting = max(now - created, timedelta(0)) if created else timedelta(0)
        jobs.append(
            PendingJob(
                int(row.get("Id", 0)),
                str(row.get("ReleaseName") or ""),
                created,
                waiting,
                folder.name,
            )
        )
    jobs.sort(key=lambda j: j.waiting, reverse=True)
    return jobs, errors


def faulted_since(
    client: OrchestratorClient, folders: list[Folder], since_utc: datetime
) -> tuple[list[FaultedJob], dict[str, str]]:
    flt = f"State eq 'Faulted' and EndTime gt {iso_z(since_utc)}"
    rows, errors = _query(client, folders, {"$filter": flt, "$expand": "Robot"})
    jobs = [
        FaultedJob(
            job_id=int(row.get("Id", 0)),
            process=str(row.get("ReleaseName") or ""),
            robot=_robot_name(row),
            end_time=parse_dt(row.get("EndTime")),
            info=str(row.get("Info") or ""),
            folder=folder.name,
        )
        for folder, row in rows
    ]
    jobs.sort(key=lambda j: (j.end_time is None, j.end_time))
    return jobs, errors
