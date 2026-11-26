import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from conftest import BASE, fx

from orch_monitor.api.auth import TOKEN_URL, AuthError, TokenProvider
from orch_monitor.api.client import OrchestratorClient
from orch_monitor.logging_setup import (
    LOGGER_NAME,
    default_log_dir,
    log_auth_error,
    make_api_logger,
    redact,
    setup_logging,
)


@pytest.fixture
def logdir(tmp_path: Path) -> Iterator[Path]:
    d = tmp_path / "logs"
    setup_logging(d)
    yield d
    logger = logging.getLogger(LOGGER_NAME)
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()


def flush() -> None:
    for h in logging.getLogger(LOGGER_NAME).handlers:
        h.flush()


def all_text(d: Path) -> str:
    flush()
    return "".join(p.read_text("utf-8") for p in d.glob("*"))


def test_TC_21_1_api_request_logged(logdir: Path) -> None:
    make_api_logger()("GET", "Jobs", 200, 123.4)
    assert "GET Jobs 200 123 ms" in all_text(logdir)


def test_TC_21_1_real_client_callback(logdir: Path) -> None:
    with respx.mock() as mock, httpx.Client() as http:
        mock.post(TOKEN_URL).respond(200, json=fx("token_ok.json"))
        mock.get(BASE + "Jobs").respond(200, json={"value": []})
        client = OrchestratorClient(
            "acme",
            "DefaultTenant",
            TokenProvider("acme", "cid", "sek", http),
            http,
            on_request=make_api_logger(),
        )
        client.get("Jobs")
    assert " GET Jobs 200 " in all_text(logdir)


def test_TC_21_2_token_never_logged(logdir: Path) -> None:
    log = logging.getLogger(f"{LOGGER_NAME}.x")
    token = "eyJhbGciOi.SECRETTOKEN-123"
    log.info("Authorization: Bearer %s", token)
    log.info("body client_secret=topsecret&x=1")
    log.info('{"access_token": "abc.def", "expires_in": 3600}')
    try:
        raise RuntimeError(f"oops Bearer {token}")
    except RuntimeError:
        log.exception("fail")
    text = all_text(logdir)
    assert "SECRETTOKEN" not in text and "topsecret" not in text and "abc.def" not in text
    assert "Bearer ***" in text and "client_secret=***" in text and "3600" in text


def test_redact_plain() -> None:
    assert redact("nic") == "nic"
    assert redact("access_token=zzz&a=1") == "access_token=***&a=1"


def test_TC_21_3_auth_error_logged_as_error(logdir: Path) -> None:
    with respx.mock() as mock, httpx.Client() as http:
        mock.post(TOKEN_URL).respond(401, json={"error": "invalid_client"})
        with pytest.raises(AuthError) as ei:
            TokenProvider("acme", "cid", "TAJNYSEKRET", http).get_token()
    log_auth_error(ei.value)
    make_api_logger()("GET", "Jobs", 401, 5.0)
    flush()
    text = all_text(logdir)
    assert "ERROR" in text and "Logowanie odrzucone" in text
    assert "TAJNYSEKRET" not in text
    assert text.count("ERROR") == 2


def test_TC_21_4_rotation_max_5_files(logdir: Path) -> None:
    log = logging.getLogger(f"{LOGGER_NAME}.rot")
    line = "x" * 1000
    for _ in range(7000):
        log.info(line)
    flush()
    files = sorted(p.name for p in logdir.iterdir())
    assert 2 <= len(files) <= 5
    assert "orch_monitor.log.1" in files
    assert all(p.stat().st_size <= 1_100_000 for p in logdir.iterdir())


def test_setup_idempotent_and_default_dir(logdir: Path, monkeypatch: Any) -> None:
    setup_logging(logdir)
    assert len(logging.getLogger(LOGGER_NAME).handlers) == 1
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", "C:/L")
    assert default_log_dir().parts[-2:] == ("OrchMonitor", "logs")
