import dataclasses
import threading
import time
from datetime import date
from typing import Any

from conftest import BASE, F1, fx, utc

from orch_monitor.refresh.scheduler import RefreshScheduler
from orch_monitor.refresh.snapshot import DataFetcher, Snapshot
from orch_monitor.services.robots import RobotsResult

NOW = utc("2026-11-26T10:00:00Z")


def snap(n: int = 0) -> Snapshot:
    return Snapshot(
        fetched_at=NOW.replace(second=n),
        robots=RobotsResult(),
        running=[],
        pending=[],
        queues=[],
        faulted_new=[],
        day=date(2026, 11, 26),
    )


def test_TC_10_1_success_notifies() -> None:
    got: list[Snapshot] = []
    s = RefreshScheduler(lambda: snap(5), 30, lambda: NOW)
    s.subscribe(got.append)
    assert s.run_once() is got[0]
    assert got[0].fetched_at.second == 5 and got[0].stale is False


def test_TC_10_2_failure_keeps_last_good_stale() -> None:
    calls = {"n": 0}

    def fetch() -> Snapshot:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("siec padla")
        return snap(1)

    got: list[Snapshot] = []
    s = RefreshScheduler(fetch, 30, lambda: NOW)
    s.subscribe(got.append)
    s.subscribe(lambda _s: 1 / 0)  # wadliwy subskrybent nie psuje reszty
    s.run_once()
    s.run_once()
    assert len(got) == 2
    assert got[1].stale is True and "siec padla" in got[1].errors["odswiezanie"]
    assert got[1].fetched_at == got[0].fetched_at and got[0].stale is False
    assert s.last_error == "siec padla"
    s.run_once()
    assert got[2].stale is False and s.last_error is None


def test_TC_10_2b_failure_without_previous_snapshot() -> None:
    def boom() -> Snapshot:
        raise RuntimeError("x")

    s = RefreshScheduler(boom, 30, lambda: NOW)
    assert s.run_once() is None and s.last_error == "x"


def test_TC_10_3_no_parallel_refresh() -> None:
    started, release = threading.Event(), threading.Event()
    count = {"n": 0}

    def slow() -> Snapshot:
        count["n"] += 1
        started.set()
        release.wait(5)
        return snap()

    s = RefreshScheduler(slow, 30, lambda: NOW)
    t = threading.Thread(target=s.run_once)
    t.start()
    assert started.wait(2)
    assert s.run_once() is None
    s.refresh_now()  # ignorowane w trakcie odswiezania
    assert count["n"] == 1
    release.set()
    t.join(2)
    assert count["n"] == 1


def test_TC_10_4_interval_change() -> None:
    waits: list[float] = []
    entered = threading.Semaphore(0)
    gate = threading.Semaphore(0)

    def fake_wait(timeout: float) -> bool:
        waits.append(timeout)
        entered.release()
        gate.acquire(timeout=5)
        return True

    s = RefreshScheduler(snap, 30, lambda: NOW, wait=fake_wait)
    s.start()
    assert entered.acquire(timeout=2)
    s.set_interval(60)
    assert s.interval_s == 60
    gate.release()
    assert entered.acquire(timeout=2)
    gate.release()
    s.stop()
    assert waits[:2] == [30, 60]


def test_TC_10_5_stop_within_2s() -> None:
    got = threading.Event()
    s = RefreshScheduler(snap, 30, lambda: NOW)
    s.subscribe(lambda _s: got.set())
    s.start()
    s.start()  # drugi start nie tworzy drugiego watku
    assert got.wait(2) and s.running
    started = time.perf_counter()
    s.stop(timeout=2)
    assert time.perf_counter() - started < 2
    assert not s.running


def test_TC_10_5b_refresh_now_wakes_loop() -> None:
    n = threading.Semaphore(0)
    s = RefreshScheduler(snap, 30, lambda: NOW)
    s.subscribe(lambda _s: n.release())
    s.start()
    assert n.acquire(timeout=2)
    s.refresh_now()
    assert n.acquire(timeout=2)
    s.stop()


def test_TC_10_6_fetcher_snapshot_and_faulted(api: Any) -> None:
    client, mock = api
    mock.get(BASE + "Sessions").respond(200, json=fx("sessions_f101.json"))
    mock.get(BASE + "QueueDefinitions").respond(200, json={"value": []})
    seen: list[str] = []

    def jobs(request: Any) -> Any:
        import httpx

        flt = request.url.params["$filter"]
        seen.append(flt)
        if "Faulted" in flt:
            return httpx.Response(200, json=fx("jobs_faulted.json"))
        return httpx.Response(
            200, json=fx("jobs_running.json" if "Running" in flt else "jobs_pending.json")
        )

    mock.get(BASE + "Jobs").mock(side_effect=jobs)
    clock = {"t": utc("2026-11-25T22:30:00Z")}
    f = DataFetcher(client, [F1], lambda: clock["t"])
    first = f.fetch()
    assert first.faulted_new == [] and not any("Faulted" in x for x in seen)
    assert first.day == date(2026, 11, 25) and len(first.robots.robots) == 4
    assert len(first.running) == 3 and len(first.pending) == 1 and first.errors == {}
    clock["t"] = utc("2026-11-25T23:30:00Z")
    second = f.fetch()
    assert second.day == date(2026, 11, 26)  # polnoc w Warszawie
    assert len(second.faulted_new) == 1
    assert "EndTime gt 2026-11-25T22:30:00Z" in seen[-1]
    assert dataclasses.replace(second, stale=True).stale


def test_TC_10_7_fetcher_errors_per_source(api: Any) -> None:
    client, mock = api
    mock.get(BASE + "Sessions").respond(500)
    mock.get(BASE + "Jobs").respond(200, json={"value": []})
    mock.get(BASE + "QueueDefinitions").respond(200, json={"value": []})
    snapshot = DataFetcher(client, [F1], lambda: NOW).fetch()
    assert set(snapshot.errors) == {"robots"} and "Finance" in snapshot.errors["robots"]


def test_TC_10_8_error_without_snapshot_is_published() -> None:
    def boom() -> Snapshot:
        raise RuntimeError("401 bledne dane")

    s = RefreshScheduler(boom, 30, lambda: utc("2026-11-26T12:00:00Z"))
    seen: list[str] = []
    s.subscribe_error(seen.append)
    assert s.run_once() is None
    assert seen == ["401 bledne dane"]
