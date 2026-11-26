import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from orch_monitor.api.auth import TOKEN_URL, TokenProvider
from orch_monitor.api.client import ApiError, OrchestratorClient

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BASE = "https://cloud.uipath.com/acme/DefaultTenant/orchestrator_/odata/"


def fx(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text("utf-8"))  # type: ignore[no-any-return]


@pytest.fixture
def env() -> Any:
    sleeps: list[float] = []
    events: list[tuple[str, str, int, float]] = []
    with respx.mock(assert_all_called=False) as mock:
        mock.post(TOKEN_URL).respond(200, json=fx("token_ok.json"))
        with httpx.Client() as http:
            tp = TokenProvider("acme", "cid", "sek", http)
            client = OrchestratorClient(
                "acme",
                "DefaultTenant",
                tp,
                http,
                sleep=sleeps.append,
                on_request=lambda *a: events.append(a),
            )
            yield client, mock, sleeps, events


def test_TC_04_1_headers(env: Any) -> None:
    client, mock, _, events = env
    route = mock.get(BASE + "Jobs").respond(200, json={"value": []})
    client.get("Jobs", {"$top": 1}, folder_id=123)
    req = route.calls[0].request
    assert req.headers["X-UIPATH-OrganizationUnitId"] == "123"
    assert req.headers["Authorization"] == "Bearer " + fx("token_ok.json")["access_token"]
    assert events[0][:3] == ("GET", "Jobs", 200)
    assert all(isinstance(x, (str, int, float)) for x in events[0])


def test_TC_04_2_paging_three_pages(env: Any) -> None:
    client, mock, _, _ = env
    for i in (1, 2, 3):
        skip = (i - 1) * 3
        mock.get(BASE + "Jobs", params={"$top": "3", "$skip": str(skip)}).respond(
            200, json=fx(f"jobs_page{i}.json")
        )
    rows = client.get_all("Jobs", folder_id=1, page_size=3)
    assert [r["Id"] for r in rows] == [1, 2, 3, 4, 5, 6, 7]


def test_paging_follows_next_link(env: Any) -> None:
    client, mock, _, _ = env
    page1 = {"value": [{"Id": 1}], "@odata.nextLink": BASE + "Jobs?$top=1&$skip=1"}
    mock.get(BASE + "Jobs", params={"$top": "1", "$skip": "0"}).respond(200, json=page1)
    mock.get(BASE + "Jobs", params={"$top": "1", "$skip": "1"}).respond(200, json={"value": []})
    assert client.get_all("Jobs", page_size=1) == [{"Id": 1}]


def test_TC_04_3_retry_after(env: Any) -> None:
    client, mock, sleeps, _ = env
    mock.get(BASE + "Jobs").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.Response(200, json={"value": [{"Id": 1}]}),
        ]
    )
    assert client.get("Jobs")["value"] == [{"Id": 1}]
    assert sleeps == [2.0]


def test_TC_04_4_503_exhausts_retries(env: Any) -> None:
    client, mock, sleeps, _ = env
    route = mock.get(BASE + "Jobs").respond(503)
    with pytest.raises(ApiError) as exc:
        client.get("Jobs")
    assert exc.value.status == 503
    assert exc.value.path == "Jobs"
    assert route.call_count == 4
    assert sleeps == [1.0, 2.0, 4.0]


def test_TC_04_5_401_refreshes_token(env: Any) -> None:
    client, mock, _, _ = env
    token_route = mock.post(TOKEN_URL).respond(200, json=fx("token_ok.json"))
    mock.get(BASE + "Jobs").mock(
        side_effect=[httpx.Response(401), httpx.Response(200, json={"value": []})]
    )
    assert client.get("Jobs") == {"value": []}
    assert token_route.call_count == 2


def test_401_twice_is_error(env: Any) -> None:
    client, mock, _, _ = env
    mock.get(BASE + "Jobs").respond(401)
    with pytest.raises(ApiError) as exc:
        client.get("Jobs")
    assert exc.value.status == 401


def test_TC_04_6_count_with_filter(env: Any) -> None:
    client, mock, _, _ = env
    route = mock.get(url__startswith=BASE + "QueueItems/$count").respond(200, text="42")
    flt = "Status eq 'Failed' and StartProcessing ge 2026-11-25T23:00:00Z"
    assert client.count("QueueItems", flt, folder_id=5) == 42
    url = str(route.calls[0].request.url)
    assert "%24filter=" not in url and "$filter=" in url
    assert " " not in url and "Status%20eq%20%27Failed%27" in url
    assert route.calls[0].request.url.params["$filter"] == flt


def test_count_without_filter_and_bad_body(env: Any) -> None:
    client, mock, _, _ = env
    mock.get(BASE + "Jobs/$count").respond(200, text="7")
    assert client.count("Jobs") == 7
    mock.get(BASE + "Jobs/$count").respond(200, text="abc")
    with pytest.raises(ApiError):
        client.count("Jobs")


def test_client_error_network_and_non_dict(env: Any) -> None:
    client, mock, sleeps, _ = env
    mock.get(BASE + "A").mock(side_effect=httpx.ConnectError("x"))
    with pytest.raises(ApiError) as exc:
        client.get("A")
    assert exc.value.status == 0 and len(sleeps) == 3
    mock.get(BASE + "B").respond(404)
    with pytest.raises(ApiError) as exc:
        client.get("B")
    assert exc.value.status == 404
    mock.get(BASE + "C").respond(200, json=[1])
    with pytest.raises(ApiError):
        client.get("C")
    assert client.base_url == BASE


def test_retry_after_invalid_uses_backoff(env: Any) -> None:
    client, mock, sleeps, _ = env
    mock.get(BASE + "Jobs").mock(
        side_effect=[
            httpx.Response(503, headers={"Retry-After": "Wed, 21 Oct"}),
            httpx.Response(200, json={}),
        ]
    )
    client.get("Jobs")
    assert sleeps == [1.0]
