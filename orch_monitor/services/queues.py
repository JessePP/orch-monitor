"""Serwis kolejek: dzisiejsze liczniki, % sukcesu i zmiana wzgledem wczoraj."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from orch_monitor.api.client import ApiError, OrchestratorClient
from orch_monitor.api.folders import Folder
from orch_monitor.clock import Clock, day_window, to_local
from orch_monitor.services._common import iso_z, parse_dt


@dataclass(frozen=True)
class QueueRow:
    queue_id: int
    name: str
    folder: str
    successful: int
    ae: int
    be: int
    success_pct: float | None
    change_pp: float | None
    in_progress: int
    new: int
    last_processed: datetime | None


def success_pct(s: int, ae: int, be: int) -> float | None:
    total = s + ae + be
    if total == 0:
        return None
    return s / total * 100.0


def change_pp(today: float | None, yesterday: float | None) -> float | None:
    if today is None or yesterday is None:
        return None
    return today - yesterday


def _window(queue_id: int, start: datetime, end: datetime) -> str:
    return (
        f"QueueDefinitionId eq {queue_id} and EndProcessing ge {iso_z(start)}"
        f" and EndProcessing lt {iso_z(end)}"
    )


def day_counts(
    client: OrchestratorClient,
    queue_id: int,
    folder_id: int,
    start_utc: datetime,
    end_utc: datetime,
) -> tuple[int, int, int]:
    """Sukcesy, AE i BE zakonczone w oknie. Status Retried nigdy nie jest liczony."""
    win = _window(queue_id, start_utc, end_utc)
    succ = client.count("QueueItems", f"Status eq 'Successful' and {win}", folder_id)
    ae = client.count(
        "QueueItems",
        f"Status eq 'Failed' and ProcessingExceptionType eq 'ApplicationException' and {win}",
        folder_id,
    )
    be = client.count(
        "QueueItems",
        f"Status eq 'Failed' and ProcessingExceptionType eq 'BusinessException' and {win}",
        folder_id,
    )
    return succ, ae, be


def _row(
    client: OrchestratorClient,
    queue: dict[str, object],
    folder: Folder,
    today: tuple[datetime, datetime],
    yesterday: tuple[datetime, datetime],
) -> QueueRow:
    qid = int(str(queue["Id"]))
    s, ae, be = day_counts(client, qid, folder.id, *today)
    ys, yae, ybe = day_counts(client, qid, folder.id, *yesterday)
    pct = success_pct(s, ae, be)
    base = f"QueueDefinitionId eq {qid} and Status eq "
    in_progress = client.count("QueueItems", base + "'InProgress'", folder.id)
    new = client.count("QueueItems", base + "'New'", folder.id)
    last = client.get(
        "QueueItems",
        {
            "$filter": f"QueueDefinitionId eq {qid} and EndProcessing ge {iso_z(today[0])}",
            "$orderby": "EndProcessing desc",
            "$top": 1,
            "$select": "EndProcessing",
        },
        folder_id=folder.id,
    ).get("value", [])
    last_processed = parse_dt(last[0].get("EndProcessing")) if last else None
    return QueueRow(
        queue_id=qid,
        name=str(queue.get("Name") or ""),
        folder=folder.name,
        successful=s,
        ae=ae,
        be=be,
        success_pct=pct,
        change_pp=change_pp(pct, success_pct(ys, yae, ybe)),
        in_progress=in_progress,
        new=new,
        last_processed=last_processed,
    )


def today_queues(
    client: OrchestratorClient, folders: list[Folder], clock: Clock
) -> tuple[list[QueueRow], dict[str, str]]:
    today_date = to_local(clock()).date()
    today = day_window(today_date)
    yesterday = day_window(today_date - timedelta(days=1))
    rows: list[QueueRow] = []
    errors: dict[str, str] = {}
    for folder in folders:
        try:
            queues = client.get_all("QueueDefinitions", folder_id=folder.id)
            rows.extend(_row(client, q, folder, today, yesterday) for q in queues)
        except ApiError as exc:
            errors[folder.name] = str(exc)
    rows.sort(key=lambda r: (r.folder.casefold(), r.name.casefold()))
    return rows, errors
