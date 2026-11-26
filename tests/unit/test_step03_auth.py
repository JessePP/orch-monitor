import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from orch_monitor.api.auth import DEFAULT_SCOPES, TOKEN_URL, AuthError, TokenProvider

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SECRET = "SUPER-TAJNY-SEKRET"


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 26, 8, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def make(clock: FakeClock, http: httpx.Client) -> TokenProvider:
    return TokenProvider("acme", "cid", SECRET, http, clock=clock)


@pytest.fixture
def token_body() -> dict[str, object]:
    return json.loads((FIXTURES / "token_ok.json").read_text("utf-8"))


@respx.mock
def test_TC_03_1_success_request_body(token_body: dict[str, object]) -> None:
    route = respx.post(TOKEN_URL).respond(200, json=token_body)
    with httpx.Client() as http:
        token = make(FakeClock(), http).get_token()
    assert token == token_body["access_token"]
    form = parse_qs(route.calls[0].request.content.decode())
    assert form["grant_type"] == ["client_credentials"]
    assert form["client_id"] == ["cid"]
    assert form["scope"] == [DEFAULT_SCOPES]


@respx.mock
def test_TC_03_2_cache(token_body: dict[str, object]) -> None:
    route = respx.post(TOKEN_URL).respond(200, json=token_body)
    clock = FakeClock()
    with httpx.Client() as http:
        tp = make(clock, http)
        assert tp.get_token() == tp.get_token()
        assert route.call_count == 1
        tp.invalidate()
        tp.get_token()
        assert route.call_count == 2


@respx.mock
def test_TC_03_3_refresh_before_expiry(token_body: dict[str, object]) -> None:
    route = respx.post(TOKEN_URL).respond(200, json=token_body)
    clock = FakeClock()
    with httpx.Client() as http:
        tp = make(clock, http)
        tp.get_token()
        clock.now += timedelta(seconds=3600 - 120)  # 120 s do wygasniecia: cache
        tp.get_token()
        assert route.call_count == 1
        clock.now += timedelta(seconds=90)  # 30 s do wygasniecia: odswiezenie
        tp.get_token()
        assert route.call_count == 2


@respx.mock
@pytest.mark.parametrize("status", [400, 401])
def test_TC_03_4_credentials_error(status: int) -> None:
    respx.post(TOKEN_URL).respond(status, json={"error": "invalid_client", "echo": SECRET})
    with httpx.Client() as http, pytest.raises(AuthError) as exc:
        make(FakeClock(), http).get_token()
    assert exc.value.kind == "credentials"
    assert SECRET not in str(exc.value)


@respx.mock
def test_TC_03_5_timeout_is_network_error() -> None:
    respx.post(TOKEN_URL).mock(side_effect=httpx.ConnectTimeout("timeout"))
    with httpx.Client() as http, pytest.raises(AuthError) as exc:
        make(FakeClock(), http).get_token()
    assert exc.value.kind == "network"
    assert SECRET not in str(exc.value)


@respx.mock
def test_auth_other_failures() -> None:
    with httpx.Client() as http:
        respx.post(TOKEN_URL).mock(side_effect=httpx.ConnectError("x"))
        with pytest.raises(AuthError) as exc:
            make(FakeClock(), http).get_token()
        assert exc.value.kind == "network"
        respx.post(TOKEN_URL).respond(503)
        with pytest.raises(AuthError) as exc:
            make(FakeClock(), http).get_token()
        assert exc.value.kind == "network"
        respx.post(TOKEN_URL).respond(200, json={"nope": 1})
        with pytest.raises(AuthError) as exc:
            make(FakeClock(), http).get_token()
        assert exc.value.kind == "credentials"
