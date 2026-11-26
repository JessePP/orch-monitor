"""Szczegoly kolejki: dzisiejsze elementy zakonczone bledem (AE/BE)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from orch_monitor.api.client import OrchestratorClient
from orch_monitor.clock import Clock, day_window, to_local
from orch_monitor.services._common import iso_z, parse_dt

Kind = Literal["AE", "BE", "both"]
_TYPES = {"AE": "ApplicationException", "BE": "BusinessException"}


@dataclass(frozen=True)
class QueueItemDetail:
    item_id: int
    reference: str
    exception_type: Literal["AE", "BE"]
    reason: str
    end_processing: datetime | None
    robot: str


@dataclass(frozen=True)
class DetailsResult:
    items: list[QueueItemDetail] = field(default_factory=list)
    truncated: bool = False


def fetch_queue_details(
    client: OrchestratorClient,
    queue_id: int,
    folder_id: int,
    clock: Clock,
    kind: Kind = "both",
    limit: int = 500,
) -> DetailsResult:
    start, end = day_window(to_local(clock()).date())
    flt = (
        f"QueueDefinitionId eq {queue_id} and Status eq 'Failed'"
        f" and EndProcessing ge {iso_z(start)} and EndProcessing lt {iso_z(end)}"
    )
    if kind in _TYPES:
        flt += f" and ProcessingExceptionType eq '{_TYPES[kind]}'"
    data = client.get(
        "QueueItems",
        {
            "$filter": flt,
            "$orderby": "EndProcessing desc",
            "$top": limit + 1,
            "$select": (
                "Id,Reference,ProcessingExceptionType,ProcessingException,EndProcessing,Robot"
            ),
            "$expand": "Robot",
        },
        folder_id=folder_id,
    )
    rows = data.get("value", [])
    items = [
        QueueItemDetail(
            item_id=int(r.get("Id", 0)),
            reference=str(r.get("Reference") or ""),
            exception_type="AE" if r.get("ProcessingExceptionType") == _TYPES["AE"] else "BE",
            reason=str((r.get("ProcessingException") or {}).get("Reason") or ""),
            end_processing=parse_dt(r.get("EndProcessing")),
            robot=str((r.get("Robot") or {}).get("Name") or ""),
        )
        for r in rows[:limit]
    ]
    return DetailsResult(items, truncated=len(rows) > limit)
