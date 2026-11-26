import re
from datetime import date, datetime
from typing import Any

import httpx
from conftest import BASE, F1, fx, utc

from orch_monitor.clock import day_window
from orch_monitor.services.queues import (
    change_pp,
    day_counts,
    success_pct,
    today_queues,
)

ITEMS: list[dict[str, Any]] = []
FILTERS: list[str] = []


def item(qid: int, status: str, end: str | None, typ: str | None = None) -> dict[str, Any]:
    return {"q": qid, "status": status, "end": utc(end) if end else None, "type": typ}


def build_items() -> list[dict[str, Any]]:
    rows = [item(31, "Successful", f"2026-11-26T0{i}:00:00Z") for i in range(1, 9)]
    rows.append(item(31, "Failed", "2026-11-26T06:00:00Z", "ApplicationException"))
    rows.append(item(31, "Failed", "2026-11-26T08:30:00Z", "BusinessException"))
    rows += [item(31, "Retried", "2026-11-26T07:00:00Z", "ApplicationException")] * 3
    rows += [item(31, "Successful", f"2026-11-25T1{i}:00:00Z") for i in range(3)]
    rows.append(item(31, "Failed", "2026-11-25T14:00:00Z", "ApplicationException"))
    rows += [item(31, "InProgress", None)] * 2 + [item(31, "New", None)] * 4
    return rows


def matches(row: dict[str, Any], flt: str) -> bool:
    if (m := re.search(r"QueueDefinitionId eq (\d+)", flt)) and row["q"] != int(m.group(1)):
        return False
    if (m := re.search(r"Status eq '(\w+)'", flt)) and row["status"] != m.group(1):
        return False
    if (m := re.search(r"ProcessingExceptionType eq '(\w+)'", flt)) and row["type"] != m.group(1):
        return False
    m = re.search(r"EndProcessing ge (\S+)", flt)
    if m and (row["end"] is None or row["end"] < utc(m.group(1))):
        return False
    m = re.search(r"EndProcessing lt (\S+)", flt)
    return not (m and (row["end"] is None or row["end"] >= utc(m.group(1))))


def handler(request: httpx.Request) -> httpx.Response:
    flt = request.url.params.get("$filter", "")
    FILTERS.append(flt)
    rows = [r for r in ITEMS if matches(r, flt)]
    if request.url.path.endswith("$count"):
        return httpx.Response(200, text=str(len(rows)))
    rows.sort(key=lambda r: r["end"], reverse=True)
    out = [{"EndProcessing": r["end"].strftime("%Y-%m-%dT%H:%M:%S.123Z")} for r in rows[:1]]
    return httpx.Response(200, json={"value": out})


def setup(mock: Any, items: list[dict[str, Any]], clock_text: str = "2026-11-26T09:00:00Z") -> Any:
    ITEMS[:] = items
    FILTERS.clear()
    mock.get(BASE + "QueueDefinitions").respond(200, json=fx("queue_defs.json"))
    mock.get(url__startswith=BASE + "QueueItems").mock(side_effect=handler)
    now = utc(clock_text)
    return lambda: now


def test_TC_08_1_window_today(api: Any) -> None:
    client, mock = api
    clock = setup(mock, build_items())
    today_queues(client, [F1], clock)
    assert any("EndProcessing ge 2026-11-25T23:00:00Z" in f for f in FILTERS)
    assert any("EndProcessing lt 2026-11-26T23:00:00Z" in f for f in FILTERS)


def test_TC_08_2_dst_day(api: Any) -> None:
    start, end = day_window(date(2026, 3, 29))
    assert start == utc("2026-03-28T23:00:00Z")
    assert end - start == utc("2026-03-29T22:00:00Z") - utc("2026-03-28T23:00:00Z")
    assert (end - start).total_seconds() == 23 * 3600
    client, mock = api
    clock = setup(mock, [], "2026-03-29T10:00:00Z")
    today_queues(client, [F1], clock)
    assert any("ge 2026-03-28T23:00:00Z" in f and "lt 2026-03-29T22:00:00Z" in f for f in FILTERS)


def test_TC_08_3_success_pct_80() -> None:
    assert success_pct(8, 1, 1) == 80.0


def test_TC_08_4_change_pp(api: Any) -> None:
    assert change_pp(80.0, 75.0) == 5.0
    client, mock = api
    rows, errors = today_queues(client, [F1], setup(mock, build_items()))
    q = next(r for r in rows if r.queue_id == 31)
    assert (q.successful, q.ae, q.be) == (8, 1, 1)
    assert q.success_pct == 80.0 and q.change_pp == 5.0
    assert (q.in_progress, q.new) == (2, 4)
    assert errors == {} and q.name == "Faktury_IN" and q.folder == "Finance"
    assert q.last_processed is not None and q.last_processed.hour == 9  # 08:30Z -> 09:30 PL
    assert q.last_processed.minute == 30


def test_TC_08_5_queue_without_items(api: Any) -> None:
    client, mock = api
    rows, _ = today_queues(client, [F1], setup(mock, build_items()))
    empty = next(r for r in rows if r.queue_id == 32)
    assert (empty.successful, empty.ae, empty.be) == (0, 0, 0)
    assert empty.success_pct is None and empty.change_pp is None
    assert empty.last_processed is None
    assert success_pct(0, 0, 0) is None
    assert change_pp(None, 50.0) is None and change_pp(50.0, None) is None


def test_TC_08_6_filters_no_retried(api: Any) -> None:
    client, mock = api
    rows, _ = today_queues(client, [F1], setup(mock, build_items()))
    assert FILTERS
    assert not any("Retried" in f for f in FILTERS)
    assert any(
        f.startswith("Status eq 'Failed' and ProcessingExceptionType eq 'ApplicationException'")
        for f in FILTERS
    )
    assert any(
        f.startswith("Status eq 'Failed' and ProcessingExceptionType eq 'BusinessException'")
        for f in FILTERS
    )
    # 3 elementy Retried dzis nie wplywaja na liczniki
    assert next(r for r in rows if r.queue_id == 31).ae == 1


def test_TC_08_7_midnight_boundary(api: Any) -> None:
    client, mock = api
    ITEMS[:] = [
        item(31, "Successful", "2026-11-25T22:59:00Z"),  # 25.11 23:59 PL
        item(31, "Successful", "2026-11-25T23:00:00Z"),  # 26.11 00:00 PL
    ]
    mock.get(url__startswith=BASE + "QueueItems").mock(side_effect=handler)
    today: tuple[datetime, datetime] = day_window(date(2026, 11, 26))
    yesterday = day_window(date(2026, 11, 25))
    assert day_counts(client, 31, 101, *today) == (1, 0, 0)
    assert day_counts(client, 31, 101, *yesterday) == (1, 0, 0)
    assert ITEMS[0]["end"] < today[0]


def test_TC_08_8_folder_error(api: Any) -> None:
    client, mock = api
    mock.get(BASE + "QueueDefinitions").respond(500)
    rows, errors = today_queues(client, [F1], lambda: utc("2026-11-26T09:00:00Z"))
    assert rows == [] and set(errors) == {"Finance"}
