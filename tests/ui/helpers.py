import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import UTC, datetime, timedelta

from orch_monitor.clock import to_local  # noqa: E402
from orch_monitor.refresh.snapshot import Snapshot  # noqa: E402
from orch_monitor.services.jobs import PendingJob, RunningJob  # noqa: E402
from orch_monitor.services.queues import QueueRow  # noqa: E402
from orch_monitor.services.robots import RobotsResult, RobotStatus  # noqa: E402

NOW = datetime(2026, 11, 26, 11, 0, 5, tzinfo=UTC)  # 12:00:05 w Warszawie


def make_robots() -> list[RobotStatus]:
    hb = to_local(NOW)
    return [
        RobotStatus(1, "BOT01", "M1", "Available", ("Finance",), hb, "Unattended"),
        RobotStatus(2, "BOT02", "M2", "Available", ("Finance",), hb, "Unattended"),
        RobotStatus(3, "BOT03", "M3", "Available", ("Invoices",), hb, "Unattended"),
        RobotStatus(4, "BOT04", "M4", "Busy", ("Finance",), hb, "Unattended"),
        RobotStatus(5, "AAA05", "M5", "Disconnected", ("Invoices",), hb, "Attended"),
    ]


def make_snapshot(
    robots: list[RobotStatus] | None = None,
    running: list[RunningJob] | None = None,
    pending: list[PendingJob] | None = None,
    queues: list[QueueRow] | None = None,
    stale: bool = False,
    fetched_at: datetime = NOW,
) -> Snapshot:
    robots = make_robots() if robots is None else robots
    summary: dict[str, int] = {}
    for r in robots:
        summary[r.status] = summary.get(r.status, 0) + 1
    return Snapshot(
        fetched_at=to_local(fetched_at),
        robots=RobotsResult(robots, summary, {}),
        running=[] if running is None else running,
        pending=[] if pending is None else pending,
        queues=[] if queues is None else queues,
        faulted_new=[],
        stale=stale,
        day=to_local(fetched_at).date(),
    )


def make_running(is_long: bool = False, start_ago_s: int = 60, jid: int = 1) -> RunningJob:
    start = to_local(NOW - timedelta(seconds=start_ago_s))
    return RunningJob(
        jid, f"BOT0{jid}", "Proc", "M1", start, "Manual", "Finance",
        timedelta(seconds=start_ago_s), is_long,
    )  # fmt: skip
