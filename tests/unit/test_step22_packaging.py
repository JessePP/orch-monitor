import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LIVE_ENV = ("ORCH_ORG", "ORCH_TENANT", "ORCH_CLIENT_ID", "ORCH_SECRET")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    return subprocess.run(
        [sys.executable, "-m", "orch_monitor", *args],
        capture_output=True, text=True, timeout=60, cwd=ROOT, env=env,
    )  # fmt: skip


def test_TC_22_1_spec_exists_onefile_windowed() -> None:
    spec = (ROOT / "packaging" / "OrchMonitor.spec").read_text("utf-8")
    assert "console=False" in spec and 'name="OrchMonitor"' in spec
    assert "COLLECT" not in spec and "a.binaries" in spec  # onefile
    assert "keyring.backends.Windows" in spec
    assert (ROOT / "packaging" / "entry.py").exists()
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")
    assert "build-windows" in ci and "windows-latest" in ci and "OrchMonitor.spec" in ci
    assert "--self-test" in ci and "--version" in ci


def test_TC_22_2_version_exit_code() -> None:
    res = _run("--version")
    expected = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]["version"]
    assert res.returncode == 0 and expected in res.stdout


def test_TC_22_3_self_test_exit_code() -> None:
    res = _run("--self-test")
    assert res.returncode == 0, res.stderr
    assert "self-test OK" in res.stdout


def _live_env() -> dict[str, str]:
    missing = [k for k in LIVE_ENV if not os.environ.get(k)]
    if missing:
        pytest.skip("Brak zmiennych środowiskowych: " + ", ".join(missing))
    return {k: os.environ[k] for k in LIVE_ENV}


@pytest.mark.live
def test_TC_22_4_live_fetch_snapshot() -> None:
    from datetime import timedelta

    import httpx

    from orch_monitor.api.auth import TokenProvider
    from orch_monitor.api.client import OrchestratorClient
    from orch_monitor.api.folders import list_folders
    from orch_monitor.clock import utc_now
    from orch_monitor.refresh.snapshot import DataFetcher

    env = _live_env()
    with httpx.Client(timeout=30.0) as http:
        tokens = TokenProvider(env["ORCH_ORG"], env["ORCH_CLIENT_ID"], env["ORCH_SECRET"], http)
        client = OrchestratorClient(env["ORCH_ORG"], env["ORCH_TENANT"], tokens, http)
        folders = list_folders(client)
        assert folders
        snap = DataFetcher(client, folders, utc_now, lambda: timedelta(minutes=90)).fetch()
    assert not snap.stale and snap.robots is not None


@pytest.mark.live
def test_TC_22_5_manual_ae_notification() -> None:
    _live_env()
    assert (ROOT / "docs" / "lista_kontrolna_tenant.md").exists()
    pytest.skip("Test ręczny: patrz docs/lista_kontrolna_tenant.md, punkt TC-22.5")


@pytest.mark.live
def test_TC_22_6_manual_weekly_report() -> None:
    _live_env()
    assert (ROOT / "docs" / "lista_kontrolna_tenant.md").exists()
    pytest.skip("Test ręczny: patrz docs/lista_kontrolna_tenant.md, punkt TC-22.6")
