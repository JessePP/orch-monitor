import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from orch_monitor.config.dismissed import DismissedStore

NOW = datetime(2026, 11, 26, 11, 0, 5, tzinfo=UTC)


def _store(p: Path, now: datetime = NOW) -> DismissedStore:
    return DismissedStore(p, clock=lambda: now)


def test_TC_23_1_save_and_load(tmp_path: Path) -> None:
    p = tmp_path / "sub" / "dismissed.json"
    s = _store(p)
    assert s.count == 0 and not s.is_dismissed(5)
    s.dismiss([5, 6], NOW)
    data = json.loads(p.read_text("utf-8"))
    assert data["version"] == 1 and set(data["items"]) == {"5", "6"}
    assert not p.with_suffix(".json.tmp").exists()
    again = _store(p)
    assert again.is_dismissed(5) and again.is_dismissed(6) and again.count == 2
    assert not again.is_dismissed(7)


def test_TC_23_2_corrupt_or_missing_file(tmp_path: Path) -> None:
    p = tmp_path / "dismissed.json"
    assert _store(p).count == 0
    for bad in ["{nie json", '{"version": 1}', '{"items": [1]}', '{"items": {"x": "y"}}', ""]:
        p.write_text(bad, encoding="utf-8")
        s = _store(p)
        assert s.count == 0
    s.dismiss([1], NOW)
    assert _store(p).is_dismissed(1)


def test_TC_23_3_prune_60_days(tmp_path: Path) -> None:
    p = tmp_path / "dismissed.json"
    _store(p, NOW - timedelta(days=100)).dismiss([1], NOW - timedelta(days=61))
    s = _store(p, NOW - timedelta(days=100))
    s.dismiss([2], NOW - timedelta(days=59))
    s.dismiss([3], NOW)
    loaded = _store(p)  # prune przy ladowaniu
    assert not loaded.is_dismissed(1)
    assert loaded.is_dismissed(2) and loaded.is_dismissed(3)
    assert "1" not in json.loads(p.read_text("utf-8"))["items"]
    assert loaded.prune(NOW - timedelta(days=30)) == 1  # usuwa tylko #2
    assert loaded.count == 1


def test_TC_23_4_restore(tmp_path: Path) -> None:
    p = tmp_path / "dismissed.json"
    s = _store(p)
    s.dismiss([1, 2, 3], NOW)
    s.restore([2, 99])
    assert not s.is_dismissed(2) and s.count == 2
    assert not _store(p).is_dismissed(2) and _store(p).is_dismissed(1)
