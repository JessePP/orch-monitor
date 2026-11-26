"""Punkt wejscia: python -m orch_monitor."""

import argparse
import sys
from collections.abc import Sequence

from orch_monitor import __version__

SELF_TEST_MODULES = ("PySide6.QtWidgets", "keyring", "openpyxl", "httpx", "pydantic")


def _out(text: str) -> None:
    """Pisze na stdout tylko gdy istnieje (aplikacja windowed nie ma stdout)."""
    stream = sys.stdout
    if stream is not None:
        try:
            stream.write(text + "\n")
            stream.flush()
        except (OSError, ValueError):
            pass


def self_test() -> int:
    """Sprawdza importy bibliotek; nie tworzy okna ani QApplication."""
    import importlib

    for name in SELF_TEST_MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - kazdy blad importu = niepowodzenie testu
            _out(f"self-test BLAD: {name}: {exc}")
            return 1
    _out("self-test OK")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orch_monitor", description="Orchestrator Monitor")
    parser.add_argument("--version", action="store_true", help="wypisz wersje i zakoncz")
    parser.add_argument(
        "--self-test", action="store_true", help="sprawdz zaleznosci i zakoncz (bez okna)"
    )
    args = parser.parse_args(argv)
    if args.version:
        _out(f"orch-monitor {__version__}")
        return 0
    if args.self_test:
        return self_test()
    from orch_monitor.app import run_app  # Qt importowany tylko tutaj

    return run_app(list(argv) if argv is not None else None)


if __name__ == "__main__":
    raise SystemExit(main())
