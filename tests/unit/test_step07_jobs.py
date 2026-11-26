from datetime import timedelta
from typing import Any

from conftest import BASE, F1, F2, fx, utc

from orch_monitor.services.jobs import faulted_since, pending, running

NOW = utc("2026-11-26T10:00:00Z")
CLOCK = lambda: NOW  # noqa: E731
TWO_H = timedelta(minutes=120)


def job(start: str, **kw: Any) -> dict[str, Any]:
    return {"Id": 1, "ReleaseName": "P", "StartTime": start, "Robot": {"Name": "r"}, **kw}


def serve(mock: Any, rows: list[dict[str, Any]]) -> None:
    mock.get(BASE + "Jobs").respond(200, json={"value": rows})


def test_TC_07_1_long_job(api: Any) -> None:
    client, mock = api
    serve(mock, [job("2026-11-26T07:59:00Z")])
    jobs, errors = running(client, [F1], CLOCK, TWO_H)
    assert jobs[0].is_long is True and jobs[0].duration == timedelta(hours=2, minutes=1)
    assert errors == {}
    params = mock.calls.last.request.url.params
    assert params["$filter"] == "State eq 'Running'" and params["$expand"] == "Robot"


def test_TC_07_2_not_long(api: Any) -> None:
    client, mock = api
    serve(mock, [job("2026-11-26T08:01:00Z")])
    assert running(client, [F1], CLOCK, TWO_H)[0][0].is_long is False


def test_TC_07_3_threshold_change(api: Any) -> None:
    client, mock = api
    serve(mock, [job("2026-11-26T09:15:00Z")])
    assert running(client, [F1], CLOCK, timedelta(minutes=30))[0][0].is_long is True
    assert running(client, [F1], CLOCK, TWO_H)[0][0].is_long is False


def test_TC_07_3b_exact_threshold_not_long_and_sorting(api: Any) -> None:
    client, mock = api
    mock.get(BASE + "Jobs").respond(200, json=fx("jobs_running.json"))
    jobs, _ = running(client, [F1], CLOCK, TWO_H)
    assert [j.job_id for j in jobs] == [503, 501, 502]
    assert jobs[0].duration == TWO_H and jobs[0].is_long is False
    assert jobs[0].source == "Queue" and jobs[0].process == "Sync_HR"
    assert jobs[0].robot == "echo_bot" and jobs[0].folder == "Finance"


def test_TC_07_4_pending(api: Any) -> None:
    client, mock = api
    mock.get(BASE + "Jobs").respond(200, json=fx("jobs_pending.json"))
    jobs, errors = pending(client, [F1], CLOCK)
    assert mock.calls.last.request.url.params["$filter"] == "State eq 'Pending'"
    assert jobs[0].waiting == timedelta(minutes=20)
    assert jobs[0].process == "Faktury_IN" and errors == {}


def test_TC_07_5_faulted_filter(api: Any) -> None:
    client, mock = api
    mock.get(BASE + "Jobs").respond(200, json=fx("jobs_faulted.json"))
    jobs, _ = faulted_since(client, [F1], utc("2026-11-26T12:00:00Z"))
    flt = mock.calls.last.request.url.params["$filter"]
    assert flt == "State eq 'Faulted' and EndTime gt 2026-11-26T12:00:00Z"
    assert jobs[0].info == "Nie znaleziono pliku" and jobs[0].robot == "Beta_bot"


def test_TC_07_6_times_in_warsaw(api: Any) -> None:
    client, mock = api
    mock.get(BASE + "Jobs").respond(200, json=fx("jobs_faulted.json"))
    jobs, _ = faulted_since(client, [F1], utc("2026-11-26T12:00:00Z"))
    end = jobs[0].end_time
    assert end is not None and end.hour == 13 and end.tzinfo is not None
    assert str(end.tzinfo) == "Europe/Warsaw"
    serve(mock, [job("2026-11-26T08:59:00.1234567Z")])
    start = running(client, [F1], CLOCK, TWO_H)[0][0].start
    assert start is not None and start.hour == 9 and str(start.tzinfo) == "Europe/Warsaw"


def test_TC_07_7_folder_error_isolated(api: Any) -> None:
    client, mock = api
    mock.get(BASE + "Jobs", headers={"X-UIPATH-OrganizationUnitId": "101"}).respond(
        200, json={"value": [job("2026-11-26T09:00:00Z")]}
    )
    mock.get(BASE + "Jobs", headers={"X-UIPATH-OrganizationUnitId": "102"}).respond(500)
    jobs, errors = running(client, [F1, F2], CLOCK, TWO_H)
    assert len(jobs) == 1 and set(errors) == {"Invoices"}
