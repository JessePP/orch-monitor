"""Punkt wejscia: python -m orch_monitor."""

import argparse
from collections.abc import Sequence

from orch_monitor import __version__


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orch_monitor", description="Orchestrator Monitor")
    parser.add_argument("--version", action="version", version=f"orch-monitor {__version__}")
    args = parser.parse_args(argv)
    del args
    from orch_monitor.app import run_app  # Qt importowany tylko tutaj

    return run_app(list(argv) if argv is not None else None)


if __name__ == "__main__":
    raise SystemExit(main())
