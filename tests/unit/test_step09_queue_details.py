from typing import Any

import httpx
from conftest import BASE, fx, utc

from orch_monitor.services.queue_details import fetch_queue_details

CLOCK = lambda: utc("2026-11-26T09:00:00Z")  # noqa: E731


def serve(mock: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        flt = request.url.params["$filter"]
        rows = fx("queue_items_failed.json")["value"]
        for key in ("ApplicationException", "BusinessException"):
            if f"ProcessingExceptionType eq '{key}'" in flt:
                rows = [r for r in rows if r["ProcessingExceptionType"] == key]
        return httpx.Response(200, json={"value": rows[: int(request.url.params["$top"])]})

    mock.get(url__startswith=BASE + "QueueItems").mock(side_effect=handler)


def test_TC_09_1_five_items_newest_first(api: Any) -> None:
    client, mock = api
    serve(mock)
    res = fetch_queue_details(client, 31, 101, CLOCK)
    assert len(res.items) == 5 and res.truncated is False
    assert [i.exception_type for i in res.items] == ["AE", "AE", "AE", "BE", "BE"]
    assert res.items[0].reason == "Powod 1" and res.items[0].reference == "REF-1"
    assert res.items[0].robot == "Beta_bot"
    ends = [i.end_processing for i in res.items]
    assert ends == sorted(ends, reverse=True)  # type: ignore[type-var]
    params = mock.calls.last.request.url.params
    flt = params["$filter"]
    assert "Status eq 'Failed'" in flt and "EndProcessing ge 2026-11-25T23:00:00Z" in flt
    assert params["$orderby"] == "EndProcessing desc" and params["$top"] == "501"
    assert "ProcessingException" in params["$select"] and params["$expand"] == "Robot"


def test_TC_09_2_filter_ae_only(api: Any) -> None:
    client, mock = api
    serve(mock)
    res = fetch_queue_details(client, 31, 101, CLOCK, kind="AE")
    assert len(res.items) == 3 and {i.exception_type for i in res.items} == {"AE"}
    res_be = fetch_queue_details(client, 31, 101, CLOCK, kind="BE")
    assert len(res_be.items) == 2


def test_TC_09_3_truncated(api: Any) -> None:
    client, mock = api
    rows = [
        {"Id": i, "Reference": str(i), "ProcessingExceptionType": "BusinessException"}
        for i in range(501)
    ]
    mock.get(url__startswith=BASE + "QueueItems").respond(200, json={"value": rows})
    res = fetch_queue_details(client, 31, 101, CLOCK)
    assert len(res.items) == 500 and res.truncated is True
    assert mock.calls.last.request.url.params["$top"] == "501"


def test_TC_09_4_missing_reason(api: Any) -> None:
    client, mock = api
    serve(mock)
    res = fetch_queue_details(client, 31, 101, CLOCK)
    assert res.items[-1].reason == "" and res.items[-1].reference == "REF-5"
