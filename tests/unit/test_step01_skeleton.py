import shutil
import subprocess
import sys
import tomllib
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import orch_monitor
from orch_monitor.clock import WARSAW, day_window, to_local, utc_now

ROOT = Path(__file__).resolve().parents[2]


def test_TC_01_1_version_cli() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "orch_monitor", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    expected = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]["version"]
    assert out.returncode == 0
    assert expected in out.stdout
    assert orch_monitor.__version__ == expected


def test_TC_01_2_ruff_and_mypy_clean() -> None:
    ruff = shutil.which("ruff") or str(Path(sys.executable).parent / "ruff")
    if not Path(ruff).exists():
        pytest.skip("ruff niedostepny")
    r = subprocess.run([ruff, "check", "."], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    m = subprocess.run(
        [sys.executable, "-m", "mypy", "orch_monitor"], cwd=ROOT, capture_output=True, text=True
    )
    assert m.returncode == 0, m.stdout


def test_TC_01_3_layers_import_without_qt() -> None:
    code = (
        "import sys, orch_monitor.services, orch_monitor.api, orch_monitor.config, "
        "orch_monitor.notify, orch_monitor.reports, orch_monitor.refresh;"
        "assert 'PySide6' not in sys.modules, 'PySide6 zaimportowany'"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_clock_utc_now_is_aware() -> None:
    assert utc_now().tzinfo is not None
    assert utc_now().utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_clock_day_window_winter_and_dst() -> None:
    s, e = day_window(date(2026, 1, 15))
    assert s == datetime(2026, 1, 14, 23, 0, tzinfo=UTC)
    assert e == datetime(2026, 1, 15, 23, 0, tzinfo=UTC)
    # dzien zmiany czasu (marzec): 23 godziny
    s, e = day_window(date(2026, 3, 29))
    assert (e - s).total_seconds() == 23 * 3600
    # dzien zmiany czasu (pazdziernik): 25 godzin
    s, e = day_window(date(2026, 10, 25))
    assert (e - s).total_seconds() == 25 * 3600


def test_clock_to_local() -> None:
    dt = to_local(datetime(2026, 7, 1, 10, 0, tzinfo=UTC))
    assert dt.tzinfo == WARSAW
    assert dt.hour == 12
    assert to_local(datetime(2026, 7, 1, 10, 0)).hour == 12
