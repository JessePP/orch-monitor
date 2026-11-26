import json
from pathlib import Path
from typing import Any

import httpx
import respx

from orch_monitor.api.auth import TOKEN_URL, TokenProvider
from orch_monitor.api.client import OrchestratorClient
from orch_monitor.api.folders import Folder, list_folders, resolve_folders

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BASE = "https://cloud.uipath.com/acme/DefaultTenant/orchestrator_/odata/"


def fx(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text("utf-8"))  # type: ignore[no-any-return]


def run(fixture: str) -> list[Folder]:
    with respx.mock() as mock, httpx.Client() as http:
        mock.post(TOKEN_URL).respond(200, json=fx("token_ok.json"))
        mock.get(url__startswith=BASE + "Folders").respond(200, json=fx(fixture))
        client = OrchestratorClient(
            "acme", "DefaultTenant", TokenProvider("acme", "c", "s", http), http
        )
        return list_folders(client)


def test_TC_05_1_three_folders() -> None:
    folders = run("folders.json")
    assert folders == [
        Folder(101, "Finance", "Finance"),
        Folder(102, "Invoices", "Finance/Invoices"),
        Folder(103, "HR", "HR"),
    ]


def test_TC_05_2_missing_folder_warns() -> None:
    folders = run("folders.json")
    resolved, warnings = resolve_folders(["Finance/Invoices", "HR", "Legal", "invoices"], folders)
    assert [f.id for f in resolved] == [102, 103]
    assert len(warnings) == 1 and "Legal" in warnings[0]


def test_TC_05_3_empty_list() -> None:
    assert run("folders_empty.json") == []
    assert resolve_folders(["X"], [])[0] == []
    assert resolve_folders([], run("folders.json")) == ([], [])
