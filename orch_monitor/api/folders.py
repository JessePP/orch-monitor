"""Foldery Orchestratora: lista i dopasowanie do ustawien."""

from __future__ import annotations

from dataclasses import dataclass

from orch_monitor.api.client import OrchestratorClient


@dataclass(frozen=True)
class Folder:
    id: int
    name: str
    full_path: str


def list_folders(client: OrchestratorClient) -> list[Folder]:
    rows = client.get_all("Folders")
    return [
        Folder(
            id=int(r["Id"]),
            name=str(r["DisplayName"]),
            full_path=str(r.get("FullyQualifiedName") or r["DisplayName"]),
        )
        for r in rows
    ]


def resolve_folders(
    configured: list[str], available: list[Folder]
) -> tuple[list[Folder], list[str]]:
    """Dopasowuje nazwy/sciezki z ustawien do folderow; brakujace daje jako ostrzezenia."""
    resolved: list[Folder] = []
    warnings: list[str] = []
    for wanted in configured:
        key = wanted.strip().casefold()
        match = next((f for f in available if f.full_path.casefold() == key), None)
        if match is None:
            match = next((f for f in available if f.name.casefold() == key), None)
        if match is None:
            warnings.append(f"Folder '{wanted}' nie istnieje w Orchestratorze i zostal pominiety.")
        elif match not in resolved:
            resolved.append(match)
    return resolved, warnings
