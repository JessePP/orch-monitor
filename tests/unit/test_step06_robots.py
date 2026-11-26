from typing import Any

from conftest import BASE, F1, F2, fx

from orch_monitor.services.robots import fetch_robots


def route(mock: Any, folder_id: int, fixture: str) -> None:
    mock.get(BASE + "Sessions", headers={"X-UIPATH-OrganizationUnitId": str(folder_id)}).respond(
        200, json=fx(fixture)
    )


def test_TC_06_1_four_sessions_mapped(api: Any) -> None:
    client, mock = api
    route(mock, 101, "sessions_f101.json")
    res = fetch_robots(client, [F1])
    assert len(res.robots) == 4
    beta = next(r for r in res.robots if r.name == "Beta_bot")
    assert (beta.robot_id, beta.machine, beta.status, beta.robot_type) == (
        12,
        "VM-BRAVO",
        "Busy",
        "Unattended",
    )
    assert beta.folders == ("Finance",)
    assert beta.last_heartbeat is not None
    assert beta.last_heartbeat.utcoffset().total_seconds() == 3600  # type: ignore[union-attr]
    req = mock.calls.last.request
    assert req.url.params["$expand"] == "Robot"


def test_TC_06_2_sorting(api: Any) -> None:
    client, mock = api
    route(mock, 101, "sessions_f101.json")
    res = fetch_robots(client, [F1])
    assert [r.name for r in res.robots] == ["alpha_bot", "gamma_bot", "Beta_bot", "zeta_bot"]
    assert [r.status for r in res.robots] == ["Unresponsive", "Disconnected", "Busy", "Available"]


def test_TC_06_3_dedup_across_folders(api: Any) -> None:
    client, mock = api
    route(mock, 101, "sessions_f101.json")
    route(mock, 102, "sessions_f102.json")
    res = fetch_robots(client, [F1, F2])
    assert len(res.robots) == 5
    beta = [r for r in res.robots if r.robot_id == 12]
    assert len(beta) == 1
    assert beta[0].folders == ("Finance", "Invoices")
    assert beta[0].status == "Busy"  # nowszy heartbeat z folderu Finance


def test_TC_06_4_summary(api: Any) -> None:
    client, mock = api
    route(mock, 101, "sessions_f101.json")
    route(mock, 102, "sessions_f102.json")
    res = fetch_robots(client, [F1, F2])
    assert res.summary == {"Available": 2, "Busy": 1, "Disconnected": 1, "Unresponsive": 1}


def test_TC_06_5_one_folder_500(api: Any) -> None:
    client, mock = api
    route(mock, 101, "sessions_f101.json")
    mock.get(BASE + "Sessions", headers={"X-UIPATH-OrganizationUnitId": "102"}).respond(500)
    res = fetch_robots(client, [F1, F2])
    assert len(res.robots) == 4
    assert set(res.errors) == {"Invoices"}
    assert "500" in res.errors["Invoices"]
