import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest
from conftest import BASE, F1, utc

from orch_monitor.clock import WARSAW, day_window
from orch_monitor.reports.builder import ReportCancelled, build_report
from orch_monitor.reports.periods import period_custom, period_day, period_month, period_week

JOBS: list[dict[str, Any]] = []
ITEMS: list[dict[str, Any]] = []
DEFS = {"value": [{"Id": 31, "Name": "Faktury_IN"}]}


def job(jid: int, state: str, start: str, end: str, info: str = "", name: str = "Proc") -> dict:
    return {
        "Id": jid,
        "ReleaseName": name,
        "State": state,
        "StartTime": start,
        "EndTime": end,
        "Info": info,
    }


def item(status: str, end: str, typ: str | None = None, reason: str = "") -> dict[str, Any]:
    return {
        "Id": len(ITEMS) + 1,
        "QueueDefinitionId": 31,
        "Status": status,
        "ProcessingExceptionType": typ,
        "EndProcessing": end,
        "ProcessingException": {"Reason": reason},
    }


def in_window(value: str, flt: str) -> bool:
    ge = re.search(r"(?:EndTime|EndProcessing) ge (\S+)", flt)
    lt = re.search(r"(?:EndTime|EndProcessing) lt (\S+)", flt)
    assert ge and lt
    return utc(ge.group(1)) <= utc(value) < utc(lt.group(1))


def jobs_handler(request: httpx.Request) -> httpx.Response:
    flt = request.url.params["$filter"]
    assert request.url.params["$select"].startswith("Id,ReleaseName")
    return httpx.Response(200, json={"value": [j for j in JOBS if in_window(j["EndTime"], flt)]})


def items_handler(request: httpx.Request) -> httpx.Response:
    flt = request.url.params["$filter"]
    rows = [i for i in ITEMS if in_window(i["EndProcessing"], flt)]
    if m := re.search(r"Status eq '(\w+)'", flt):
        rows = [r for r in rows if r["Status"] == m.group(1)]
    if m := re.search(r"ProcessingExceptionType eq '(\w+)'", flt):
        rows = [r for r in rows if r["ProcessingExceptionType"] == m.group(1)]
    if request.url.path.endswith("$count"):
        return httpx.Response(200, text=str(len(rows)))
    assert request.url.params["$top"] == "500"
    return httpx.Response(200, json={"value": rows})


def setup(mock: Any, jobs: list[dict] | None = None, items: list[dict] | None = None) -> None:
    JOBS[:] = jobs or []
    ITEMS[:] = items or []
    mock.get(BASE + "QueueDefinitions").respond(200, json=DEFS)
    mock.get(url__startswith=BASE + "Jobs").mock(side_effect=jobs_handler)
    mock.get(url__startswith=BASE + "QueueItems").mock(side_effect=items_handler)


def test_TC_18_1_week() -> None:
    p = period_week(date(2026, 11, 26))
    assert (p.start_date, p.end_date) == (date(2026, 11, 23), date(2026, 11, 29))
    assert p.start_utc == datetime(2026, 11, 22, 23, 0, tzinfo=UTC)
    assert p.end_utc - timedelta(seconds=1) == datetime(2026, 11, 29, 23, 59, 59, tzinfo=WARSAW)
    assert len(p.days) == 7
    assert period_day(date(2026, 11, 26)).days == [date(2026, 11, 26)]
    with pytest.raises(ValueError):
        period_custom(date(2026, 11, 2), date(2026, 11, 1))


def test_TC_18_2_month(api: Any) -> None:
    p = period_month(date(2026, 11, 26))
    assert (p.start_date, p.end_date) == (date(2026, 11, 1), date(2026, 11, 30))
    client, mock = api
    setup(mock)
    r = build_report(client, p, [F1])
    assert len(r.days) == 30 and r.folders == ["Finance"]


def test_TC_18_3_be_does_not_break_verdict(api: Any) -> None:
    client, mock = api
    items = [item("Failed", "2026-11-24T10:00:00Z", "BusinessException") for _ in range(4)]
    setup(mock, items=items)
    r = build_report(client, period_week(date(2026, 11, 26)), [F1])
    assert r.summary.verdict_ok and r.summary.be == 4 and r.summary.ae == 0
    assert all(d.verdict_ok for d in r.days)


def test_TC_18_4_faulted_tuesday(api: Any) -> None:
    client, mock = api
    setup(mock, jobs=[job(1, "Faulted", "2026-11-24T09:00:00Z", "2026-11-24T09:10:00Z", "x")])
    r = build_report(client, period_week(date(2026, 11, 26)), [F1])
    assert not r.summary.verdict_ok and r.summary.faulted == 1
    bad = [d for d in r.days if not d.verdict_ok]
    assert [(d.day, d.faulted) for d in bad] == [(date(2026, 11, 24), 1)]


def test_TC_18_5_avg_duration(api: Any) -> None:
    client, mock = api
    jobs = [
        job(i, "Successful", f"2026-11-24T0{i}:00:00Z", f"2026-11-24T0{i}:{m}:00Z")
        for i, m in ((1, 10), (2, 20), (3, 30))
    ]
    setup(mock, jobs=jobs)
    r = build_report(client, period_day(date(2026, 11, 24)), [F1])
    p = r.processes[0]
    assert (p.runs, p.successful, p.faulted, p.stopped) == (3, 3, 0, 0)
    assert p.avg_duration == timedelta(minutes=20)
    assert r.summary.jobs_total == 3


def test_TC_18_6_error_entries(api: Any) -> None:
    client, mock = api
    jobs = [
        job(1, "Faulted", "2026-11-24T09:00:00Z", "2026-11-24T09:10:00Z", "Brak pliku", "Raport"),
        job(2, "Stopped", "2026-11-24T09:00:00Z", "2026-11-24T09:05:00Z"),
    ]
    items = [item("Failed", "2026-11-24T11:00:00Z", "ApplicationException", "Timeout")]
    setup(mock, jobs=jobs, items=items)
    r = build_report(client, period_day(date(2026, 11, 24)), [F1])
    f, ae = r.errors
    assert (f.kind, f.process_or_queue, f.message, f.folder) == (
        "Faulted",
        "Raport",
        "Brak pliku",
        "Finance",
    )
    assert f.when == datetime(2026, 11, 24, 10, 10, tzinfo=WARSAW)
    assert (ae.kind, ae.process_or_queue, ae.message) == ("AE", "Faktury_IN", "Timeout")
    q = r.queues[0]
    assert (q.ae, q.successful, q.success_pct) == (1, 0, 0.0)
    assert r.days[0].ae == 1


def test_TC_18_7_dst_month(api: Any) -> None:
    p = period_month(date(2026, 3, 10))
    assert len(p.days) == 31
    assert p.days[28] == date(2026, 3, 29)
    prev_end = None
    for d in p.days:
        s, e = day_window(d)
        assert s < e
        assert prev_end is None or prev_end == s
        prev_end = e
    assert day_window(date(2026, 3, 29))[1] - day_window(date(2026, 3, 29))[0] == timedelta(
        hours=23
    )
    assert p.start_utc == day_window(date(2026, 3, 1))[0] and p.end_utc == prev_end
    client, mock = api
    setup(mock, items=[item("Successful", "2026-03-28T23:30:00Z")])  # 00:30 PL 29.03
    r = build_report(client, p, [F1])
    assert r.queues[0].successful == 1


def test_TC_18_8_empty(api: Any) -> None:
    client, mock = api
    setup(mock)
    r = build_report(client, period_week(date(2026, 11, 26)), [F1])
    assert r.summary.verdict_ok
    assert (r.summary.jobs_total, r.summary.queue_items_total, r.summary.ae, r.summary.be) == (
        0,
        0,
        0,
        0,
    )
    assert r.processes == [] and r.errors == [] and r.queues[0].success_pct is None


def test_progress_and_cancel(api: Any) -> None:
    client, mock = api
    setup(mock)
    calls: list[tuple[int, int]] = []
    build_report(
        client, period_day(date(2026, 11, 24)), [F1], progress=lambda a, b: calls.append((a, b))
    )
    assert calls[-1][0] == calls[-1][1] and len(calls) == 3
    with pytest.raises(ReportCancelled):
        build_report(client, period_day(date(2026, 11, 24)), [F1], cancelled=lambda: True)
