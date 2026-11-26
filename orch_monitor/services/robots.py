"""Serwis robotow: statusy sesji robotow ze wszystkich monitorowanych folderow."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from orch_monitor.api.client import ApiError, OrchestratorClient
from orch_monitor.api.folders import Folder
from orch_monitor.services._common import parse_dt

_PROBLEM = {"Disconnected", "Unresponsive"}


@dataclass(frozen=True)
class RobotStatus:
    robot_id: int
    name: str
    machine: str
    status: str
    folders: tuple[str, ...]
    last_heartbeat: datetime | None
    robot_type: str


@dataclass(frozen=True)
class RobotsResult:
    robots: list[RobotStatus] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


def _group(status: str) -> int:
    if status in _PROBLEM:
        return 0
    return {"Busy": 1, "Available": 2}.get(status, 3)


def fetch_robots(client: OrchestratorClient, folders: list[Folder]) -> RobotsResult:
    errors: dict[str, str] = {}
    found: dict[int, RobotStatus] = {}
    for folder in folders:
        try:
            rows = client.get_all("Sessions", {"$expand": "Robot"}, folder_id=folder.id)
        except ApiError as exc:
            errors[folder.name] = str(exc)
            continue
        for row in rows:
            robot = row.get("Robot") or {}
            rid = int(robot.get("Id", row.get("RobotId", 0)) or 0)
            item = RobotStatus(
                robot_id=rid,
                name=str(robot.get("Name") or row.get("RobotName") or ""),
                machine=str(row.get("HostMachineName") or ""),
                status=str(row.get("State") or ""),
                folders=(folder.name,),
                last_heartbeat=parse_dt(row.get("ReportingTime")),
                robot_type=str(robot.get("Type") or ""),
            )
            prev = found.get(rid)
            if prev is None:
                found[rid] = item
                continue
            folders_all = (*prev.folders, *(f for f in item.folders if f not in prev.folders))
            newer = item.last_heartbeat is not None and (
                prev.last_heartbeat is None or item.last_heartbeat > prev.last_heartbeat
            )
            base = item if newer else prev
            found[rid] = RobotStatus(
                base.robot_id,
                base.name,
                base.machine,
                base.status,
                folders_all,
                base.last_heartbeat,
                base.robot_type,
            )
    robots = sorted(found.values(), key=lambda r: (_group(r.status), r.name.casefold()))
    summary = dict(Counter(r.status for r in robots))
    return RobotsResult(robots, summary, errors)
