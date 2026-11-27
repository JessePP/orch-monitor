import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from conftest import BASE, F1, fx, utc

from orch_monitor.config.notes import ErrorRef, NotesError, NotesStore, safe_name
from orch_monitor.config.settings import Settings, parse_settings
from orch_monitor.refresh.snapshot import DataFetcher

T1 = datetime(2026, 11, 27, 8, 0, 0, tzinfo=UTC)
T2 = datetime(2026, 11, 27, 8, 5, 0, tzinfo=UTC)
REF = ErrorRef("queue_item", 42, "Kolejka Q1 (Finance) · REF-42", "AE: Timeout")


def _store(base: Path, author: str = "jan", t: datetime = T1, tenant: str = "Prod") -> NotesStore:
    return NotesStore(base, tenant, author=author, clock=lambda: t)


def test_TC_24_1_add_and_reload(tmp_path: Path) -> None:
    s = _store(tmp_path)
    note = s.add(REF, "  Sprawdzam logi robota  ")
    assert note.text == "Sprawdzam logi robota" and note.author == "jan"
    files = list((tmp_path / "Prod" / "qi-42").glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text("utf-8"))
    assert data["version"] == 1 and data["error"]["title"] == REF.title
    again = _store(tmp_path).notes_for(REF.key)  # nowy obiekt = np. inny start aplikacji
    assert [(n.author, n.created_at, n.text) for n in again] == [
        ("jan", T1, "Sprawdzam logi robota")
    ]
    with pytest.raises(NotesError):
        s.add(REF, "   ")


def test_TC_24_2_two_users_share_folder(tmp_path: Path) -> None:
    jan, ola = _store(tmp_path, "jan", T1), _store(tmp_path, "ola", T1)
    jan.add(REF, "Moje")
    ola.add(REF, "Moje też")  # ta sama sekunda: osobne pliki, nic nie nadpisane
    notes = jan.notes_for(REF.key)
    assert sorted(n.text for n in notes) == ["Moje", "Moje też"]
    assert {n.author for n in ola.notes_for(REF.key)} == {"jan", "ola"}


def test_TC_24_3_delete_only_own(tmp_path: Path) -> None:
    jan, ola = _store(tmp_path, "jan", T1), _store(tmp_path, "ola", T2)
    jan.add(REF, "A")
    ola.add(REF, "B")
    a, b = jan.notes_for(REF.key)
    assert jan.can_delete(a) and not jan.can_delete(b)
    with pytest.raises(NotesError, match="własną"):
        jan.delete(REF.key, b)
    jan.delete(REF.key, a)
    assert [n.text for n in ola.notes_for(REF.key)] == ["B"]


def test_TC_24_4_missing_or_broken_files(tmp_path: Path) -> None:
    s = _store(tmp_path / "nie_ma")
    assert s.notes_for(REF.key) == [] and s.counts() == {}
    s2 = _store(tmp_path)
    s2.add(REF, "dobra")
    folder = tmp_path / "Prod" / "qi-42"
    (folder / "zly.json").write_text("{nie json", "utf-8")
    (folder / "bez_strefy.json").write_text(
        json.dumps({"author": "x", "created_at": "2026-11-27T08:00:00", "text": "t"}), "utf-8"
    )
    assert [n.text for n in s2.notes_for(REF.key)] == ["dobra"]


def test_TC_24_4_unreachable_folder_polish_error(tmp_path: Path) -> None:
    blocker = tmp_path / "plik"
    blocker.write_text("x", "utf-8")  # „folder” jest plikiem: zapis musi sie nie udac
    s = _store(blocker)
    with pytest.raises(NotesError, match="Nie udało się zapisać notatek"):
        s.add(REF, "tekst")


def test_TC_24_5_counts_and_tenant_separation(tmp_path: Path) -> None:
    prod, test = _store(tmp_path, tenant="Prod"), _store(tmp_path, tenant="Test")
    job = ErrorRef("job", 42, "Job X")
    prod.add(REF, "1")
    prod.add(REF, "2")
    prod.add(job, "3")
    assert prod.counts() == {"qi-42": 2, "job-42": 1}
    assert test.counts() == {} and test.notes_for(REF.key) == []
    bad = safe_name("..\\..\\evil/../x")
    assert "/" not in bad and "\\" not in bad and not bad.startswith(".")
    assert safe_name("") == "x"


def test_TC_24_5_configure_and_settings(tmp_path: Path) -> None:
    s = NotesStore(None, "Prod", author="jan")
    assert not s.shared and s.root.name == "Prod"
    s.configure(tmp_path, "")
    assert s.shared and s.location == str(tmp_path) and s.root == tmp_path / "domyslny"
    assert Settings().notes_folder == ""
    assert parse_settings({"notes_folder": r"\\srv\team"}).notes_folder == r"\\srv\team"


@pytest.mark.skipif(os.name == "nt", reason="chmod na Windows nie blokuje odczytu")
def test_TC_24_4_counts_unreadable_raises(tmp_path: Path) -> None:
    s = _store(tmp_path)
    s.add(REF, "x")
    if os.geteuid() == 0:
        pytest.skip("root czyta wszystko")
    s.root.chmod(0)
    try:
        with pytest.raises(NotesError):
            s.counts()
    finally:
        s.root.chmod(0o755)


def test_TC_24_6_fetcher_tracks_faulted_today(api: Any) -> None:
    client, mock = api
    mock.get(BASE + "Sessions").respond(200, json=fx("sessions_f101.json"))
    mock.get(BASE + "QueueDefinitions").respond(200, json={"value": []})
    seen: list[str] = []
    faulted = {"rows": fx("jobs_faulted.json")["value"]}

    def jobs(request: Any) -> Any:
        flt = request.url.params["$filter"]
        seen.append(flt)
        if "Faulted" in flt:
            return httpx.Response(200, json={"value": faulted["rows"]})
        return httpx.Response(200, json={"value": []})

    mock.get(BASE + "Jobs").mock(side_effect=jobs)
    clock = {"t": utc("2026-11-26T13:00:00Z")}
    f = DataFetcher(client, [F1], lambda: clock["t"], track_faulted_today=True)
    first = f.fetch()
    # pierwsze pobranie: od polnocy w Warszawie (23:00 UTC), bez powiadomien
    assert "EndTime gt 2026-11-25T23:00:00Z" in seen[-1]
    assert [j.job_id for j in first.faulted_today] == [701] and first.faulted_new == []
    clock["t"] = utc("2026-11-26T13:30:00Z")
    new = dict(faulted["rows"][0], Id=702, EndTime="2026-11-26T13:20:00Z")
    faulted["rows"] = [new]
    second = f.fetch()
    assert "EndTime gt 2026-11-26T13:00:00Z" in seen[-1]
    assert [j.job_id for j in second.faulted_new] == [702]
    assert [j.job_id for j in second.faulted_today] == [702, 701]  # od najnowszego
    clock["t"] = utc("2026-11-26T23:10:00Z")  # 00:10 w Warszawie, nowa doba
    faulted["rows"] = []
    third = f.fetch()
    assert third.faulted_today == []
