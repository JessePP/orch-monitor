import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from orch_monitor.api.auth import TOKEN_URL, TokenProvider
from orch_monitor.api.client import OrchestratorClient
from orch_monitor.api.folders import Folder

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BASE = "https://cloud.uipath.com/acme/DefaultTenant/orchestrator_/odata/"
F1 = Folder(101, "Finance", "Finance")
F2 = Folder(102, "Invoices", "Finance/Invoices")


def fx(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text("utf-8"))  # type: ignore[no-any-return]


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


@pytest.fixture
def api() -> Iterator[tuple[OrchestratorClient, respx.MockRouter]]:
    with respx.mock(assert_all_called=False) as mock:
        mock.post(TOKEN_URL).respond(200, json=fx("token_ok.json"))
        with httpx.Client() as http:
            client = OrchestratorClient(
                "acme",
                "DefaultTenant",
                TokenProvider("acme", "cid", "sek", http),
                http,
                sleep=lambda _s: None,
            )
            yield client, mock
