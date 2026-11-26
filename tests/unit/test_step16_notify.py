from datetime import UTC, date, datetime, timedelta

from orch_monitor.clock import WARSAW
from orch_monitor.config.settings import NotificationSettings
from orch_monitor.notify.engine import NotificationEngine, end_of_day, mute_options
from orch_monitor.refresh.snapshot import Snapshot
from orch_monitor.services.jobs import FaultedJob
from orch_monitor.services.queues import QueueRow
from orch_monitor.services.robots import RobotsResult, RobotStatus

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)


class Clk:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def qrow(name: str, ae: int = 0, be: int = 0, qid: int = 1) -> QueueRow:
    return QueueRow(qid, name, "Finance", 10, ae, be, None, None, 0, 0, None)


def robot(name: str, status: str, rid: int = 1) -> RobotStatus:
    return RobotStatus(rid, name, "M1", status, ("Finance",), None, "Unattended")


def job(jid: int, process: str = "Raport_dzienny") -> FaultedJob:
    return FaultedJob(jid, process, "BOT01", NOW, "blad", "Finance")


def snap(
    queues: list[QueueRow] | None = None,
    robots: list[RobotStatus] | None = None,
    faulted: list[FaultedJob] | None = None,
    day: date = date(2026, 11, 26),
) -> Snapshot:
    return Snapshot(
        fetched_at=NOW,
        robots=RobotsResult(robots=robots or []),
        running=[],
        pending=[],
        queues=queues or [],
        faulted_new=faulted or [],
        day=day,
    )


def engine(
    settings: NotificationSettings | None = None, clk: Clk | None = None
) -> NotificationEngine:
    cfg = settings or NotificationSettings()
    return NotificationEngine(lambda: cfg, clk or Clk())


def test_TC_16_1_first_snapshot_no_notifications() -> None:
    assert engine().process(snap([qrow("X", ae=4)], [robot("BOT01", "Disconnected")])) == []


def test_TC_16_2_new_ae() -> None:
    e = engine()
    e.process(snap([qrow("X", ae=2)]))
    out = e.process(snap([qrow("X", ae=5)]))
    assert [(n.kind, n.message, n.target_tab) for n in out] == [
        ("queue_ae", "X: 3 nowe AE", "queues")
    ]


def test_TC_16_3_no_change() -> None:
    e = engine()
    e.process(snap([qrow("X", ae=5)]))
    assert e.process(snap([qrow("X", ae=5)])) == []


def test_TC_16_4_be_disabled() -> None:
    e = engine()
    e.process(snap([qrow("X")]))
    assert e.process(snap([qrow("X", be=1)])) == []


def test_TC_16_5_be_enabled() -> None:
    e = engine(NotificationSettings(queue_be=True))
    e.process(snap([qrow("X")]))
    out = e.process(snap([qrow("X", be=1)]))
    assert [n.message for n in out] == ["X: 1 nowe BE"]
    assert out[0].kind == "queue_be"


def test_TC_16_6_robot_disconnected() -> None:
    e = engine()
    e.process(snap(robots=[robot("BOT01", "Available")]))
    out = e.process(snap(robots=[robot("BOT01", "Disconnected")]))
    assert [(n.message, n.target_tab, n.kind) for n in out] == [
        ("Robot BOT01 rozłączony", "robots", "robot_down")
    ]


def test_TC_16_6_robot_unresponsive_and_disabled() -> None:
    e = engine()
    e.process(snap(robots=[robot("BOT01", "Busy")]))
    out = e.process(snap(robots=[robot("BOT01", "Unresponsive")]))
    assert [n.message for n in out] == ["Robot BOT01 nie odpowiada"]
    off = engine(NotificationSettings(robot_down=False))
    off.process(snap(robots=[robot("BOT01", "Busy")]))
    assert off.process(snap(robots=[robot("BOT01", "Disconnected")])) == []


def test_TC_16_7_robot_reported_once() -> None:
    e = engine()
    e.process(snap(robots=[robot("BOT01", "Available")]))
    assert len(e.process(snap(robots=[robot("BOT01", "Disconnected")]))) == 1
    assert e.process(snap(robots=[robot("BOT01", "Disconnected")])) == []
    assert e.process(snap(robots=[robot("BOT01", "Unresponsive")])) == []
    e.process(snap(robots=[robot("BOT01", "Available")]))
    assert len(e.process(snap(robots=[robot("BOT01", "Disconnected")]))) == 1


def test_TC_16_8_faulted_job_once() -> None:
    e = engine()
    e.process(snap())
    out = e.process(snap(faulted=[job(5)]))
    assert [(n.message, n.target_tab, n.kind) for n in out] == [
        ("Proces Raport_dzienny: Faulted", "jobs", "job_faulted")
    ]
    assert e.process(snap(faulted=[job(5)])) == []


def test_TC_16_8_faulted_grouped_per_process() -> None:
    e = engine()
    e.process(snap())
    out = e.process(snap(faulted=[job(1), job(2), job(3), job(4, "Inny")]))
    assert sorted(n.message for n in out) == [
        "Proces Inny: Faulted",
        "Proces Raport_dzienny: Faulted (3 joby)",
    ]
    off = engine(NotificationSettings(job_faulted=False))
    off.process(snap())
    assert off.process(snap(faulted=[job(9)])) == []


def test_TC_16_9_midnight_no_alarms() -> None:
    e = engine()
    e.process(snap([qrow("X", ae=5)], day=date(2026, 11, 26)))
    assert e.process(snap([qrow("X", ae=0)], day=date(2026, 11, 27))) == []
    out = e.process(snap([qrow("X", ae=2)], day=date(2026, 11, 27)))
    assert [n.message for n in out] == ["X: 2 nowe AE"]


def test_TC_16_10_mute_and_unmute() -> None:
    clk = Clk(datetime(2026, 11, 26, 12, 0, tzinfo=UTC))  # 13:00 PL
    e = engine(clk=clk)
    until = datetime(2026, 11, 26, 13, 0, tzinfo=UTC)
    e.mute_until(until)
    assert e.is_muted() and e.muted_until == until
    e.process(snap([qrow("X", ae=0)]))
    clk.now = datetime(2026, 11, 26, 12, 30, tzinfo=UTC)
    assert e.process(snap([qrow("X", ae=3)], faulted=[job(1)])) == []
    clk.now = until + timedelta(minutes=1)
    assert not e.is_muted() and e.muted_until is None
    assert e.process(snap([qrow("X", ae=3)], faulted=[job(1)])) == []
    out = e.process(snap([qrow("X", ae=4)]))
    assert [n.message for n in out] == ["X: 1 nowe AE"]
    e.mute_until(clk.now + timedelta(hours=1))
    e.mute_until(None)
    assert not e.is_muted()


def test_TC_16_11_three_queues() -> None:
    e = engine()
    e.process(snap([qrow("A", qid=1), qrow("B", qid=2), qrow("C", qid=3)]))
    out = e.process(snap([qrow("A", 1, qid=1), qrow("B", 2, qid=2), qrow("C", 3, qid=3)]))
    assert sorted(n.message for n in out) == ["A: 1 nowe AE", "B: 2 nowe AE", "C: 3 nowe AE"]
    assert len({n.key for n in out}) == 3


def test_mute_helpers() -> None:
    now = datetime(2026, 11, 26, 14, 20, tzinfo=UTC)  # 15:20 PL
    eod = end_of_day(now)
    assert eod == datetime(2026, 11, 26, 23, 59, 59, tzinfo=WARSAW)
    opts = dict(mute_options(now))
    assert opts["Wycisz na 1 h"] == now + timedelta(hours=1)
    assert opts["Wycisz na 30 min"] == now + timedelta(minutes=30)
    assert opts["Wycisz na 4 h"] == now + timedelta(hours=4)
    assert opts["Wycisz do końca dnia"] == eod
