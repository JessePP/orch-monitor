"""Budowanie raportu z API Orchestratora (bez lokalnej bazy)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime, timedelta

from orch_monitor.api.client import OrchestratorClient
from orch_monitor.api.folders import Folder
from orch_monitor.clock import day_window
from orch_monitor.reports.model import (
    DayStats,
    ErrorEntry,
    ProcessStats,
    QueueStats,
    Report,
    Summary,
)
from orch_monitor.reports.periods import Period
from orch_monitor.services._common import iso_z, parse_dt
from orch_monitor.services.queues import day_counts, success_pct

Progress = Callable[[int, int], None]
Cancelled = Callable[[], bool]

AE_ITEMS_LIMIT = 500


class ReportCancelled(Exception):
    """Uzytkownik anulowal budowanie raportu."""


_Run = tuple[str, datetime | None, datetime | None]


class _Ctx:
    def __init__(self, total: int, progress: Progress | None, cancelled: Cancelled | None) -> None:
        self.total = total
        self.done = 0
        self._progress = progress
        self._cancelled = cancelled

    def check(self) -> None:
        if self._cancelled is not None and self._cancelled():
            raise ReportCancelled("Raport anulowany.")

    def step(self) -> None:
        self.done += 1
        if self._progress is not None:
            self._progress(self.done, self.total)


def build_report(
    client: OrchestratorClient,
    period: Period,
    folders: list[Folder],
    progress: Progress | None = None,
    cancelled: Cancelled | None = None,
) -> Report:
    # definicje kolejek (potrzebne do policzenia liczby krokow)
    queue_defs: dict[int, list[dict[str, object]]] = {}
    for folder in folders:
        queue_defs[folder.id] = client.get_all("QueueDefinitions", folder_id=folder.id)
    total = 2 * len(folders) + sum(len(q) for q in queue_defs.values())
    ctx = _Ctx(total, progress, cancelled)

    faulted_per_day: dict[date, int] = defaultdict(int)
    ae_per_day: dict[date, int] = defaultdict(int)
    be_per_day: dict[date, int] = defaultdict(int)
    errors: list[ErrorEntry] = []

    # joby
    runs: dict[str, list[_Run]] = defaultdict(list)
    for folder in folders:
        ctx.check()
        flt = f"EndTime ge {iso_z(period.start_utc)} and EndTime lt {iso_z(period.end_utc)}"
        rows = client.get_all(
            "Jobs",
            {"$filter": flt, "$select": "Id,ReleaseName,State,StartTime,EndTime,Info"},
            folder_id=folder.id,
            page_size=1000,
        )
        for row in rows:
            name = str(row.get("ReleaseName") or "")
            start, end = parse_dt(row.get("StartTime")), parse_dt(row.get("EndTime"))
            state = str(row.get("State") or "")
            runs[name].append((state, start, end))
            if state == "Faulted":
                if end is not None:
                    faulted_per_day[end.date()] += 1
                errors.append(
                    ErrorEntry("Faulted", end, name, folder.name, str(row.get("Info") or ""))
                )
        ctx.step()

    processes = [_process_stats(name, items) for name, items in runs.items()]
    processes.sort(key=lambda p: (-p.runs, p.process.casefold()))

    # kolejki
    queue_stats: list[QueueStats] = []
    names: dict[tuple[int, int], str] = {}
    for folder in folders:
        for qdef in queue_defs[folder.id]:
            qid = int(str(qdef["Id"]))
            qname = str(qdef.get("Name") or "")
            names[(folder.id, qid)] = qname
            s_tot = ae_tot = be_tot = 0
            for d in period.days:
                ctx.check()
                s, ae, be = day_counts(client, qid, folder.id, *day_window(d))
                s_tot, ae_tot, be_tot = s_tot + s, ae_tot + ae, be_tot + be
                ae_per_day[d] += ae
                be_per_day[d] += be
            queue_stats.append(
                QueueStats(
                    qname, folder.name, s_tot, ae_tot, be_tot, success_pct(s_tot, ae_tot, be_tot)
                )
            )
            ctx.step()
    queue_stats.sort(key=lambda q: (q.folder.casefold(), q.name.casefold()))

    # tresc AE
    for folder in folders:
        ctx.check()
        if any(ae_per_day.values()):
            flt = (
                "Status eq 'Failed' and ProcessingExceptionType eq 'ApplicationException'"
                f" and EndProcessing ge {iso_z(period.start_utc)}"
                f" and EndProcessing lt {iso_z(period.end_utc)}"
            )
            data = client.get(
                "QueueItems",
                {
                    "$filter": flt,
                    "$select": "Id,QueueDefinitionId,Reference,EndProcessing,ProcessingException",
                    "$orderby": "EndProcessing desc",
                    "$top": AE_ITEMS_LIMIT,
                },
                folder_id=folder.id,
            )
            for item in data.get("value", []):
                exc = item.get("ProcessingException") or {}
                qname = names.get((folder.id, int(item.get("QueueDefinitionId") or 0)), "")
                errors.append(
                    ErrorEntry(
                        "AE",
                        parse_dt(item.get("EndProcessing")),
                        qname,
                        folder.name,
                        str(exc.get("Reason") or ""),
                    )
                )
        ctx.step()

    errors.sort(key=lambda e: (e.when is None, e.when))
    days = _days(period, faulted_per_day, ae_per_day, be_per_day)
    s_all = sum(q.successful for q in queue_stats)
    ae_all = sum(q.ae for q in queue_stats)
    be_all = sum(q.be for q in queue_stats)
    faulted_all = sum(p.faulted for p in processes)
    summary = Summary(
        verdict_ok=faulted_all == 0 and ae_all == 0,
        jobs_total=sum(p.runs for p in processes),
        queue_items_total=s_all + ae_all + be_all,
        ae=ae_all,
        be=be_all,
        faulted=faulted_all,
    )
    return Report(period, [f.name for f in folders], summary, processes, queue_stats, days, errors)


def _days(
    period: Period,
    faulted: dict[date, int],
    ae: dict[date, int],
    be: dict[date, int],
) -> list[DayStats]:
    return [
        DayStats(d, faulted[d], ae[d], be[d], faulted[d] == 0 and ae[d] == 0) for d in period.days
    ]


def _process_stats(name: str, items: list[_Run]) -> ProcessStats:
    durations = [end - start for _s, start, end in items if start is not None and end is not None]
    avg = sum(durations, timedelta()) / len(durations) if durations else None
    states = [state for state, _a, _b in items]
    return ProcessStats(
        name,
        len(items),
        states.count("Successful"),
        states.count("Faulted"),
        states.count("Stopped"),
        avg,
    )
