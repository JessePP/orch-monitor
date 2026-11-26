"""Logowanie do pliku z rotacja i maskowaniem sekretow."""

from __future__ import annotations

import logging
import os
import re
import sys
import traceback
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "orch_monitor"
LOG_FILE = "orch_monitor.log"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 4  # razem maks. 5 plikow
MASK = "***"

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-._~+/]+=*"), r"\1" + MASK),
    (re.compile(r"(?i)(client_secret\s*[=:]\s*)[^&\s'\"]+"), r"\1" + MASK),
    (re.compile(r"(?i)([\"']?access_token[\"']?\s*[=:]\s*[\"']?)[^&\s'\",}]+"), r"\1" + MASK),
]


def redact(text: str) -> str:
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


class RedactingFilter(logging.Filter):
    """Maskuje tokeny i sekrety w kazdym rekordzie (komunikat, argumenty, wyjatek)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        if record.exc_info:
            text = "".join(traceback.format_exception(*record.exc_info))
            record.exc_text = redact(text)
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True


def default_log_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "OrchMonitor" / "logs"
    return Path.home() / ".local" / "state" / "orch-monitor" / "logs"


def setup_logging(log_dir: Path | None = None) -> Path:
    """Konfiguruje logger aplikacji; zwraca sciezke biezacego pliku logu."""
    directory = log_dir or default_log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / LOG_FILE
    logger = logging.getLogger(LOGGER_NAME)
    for old in list(logger.handlers):
        if getattr(old, "_orch_monitor", False):
            logger.removeHandler(old)
            old.close()
    handler = RotatingFileHandler(
        path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    handler._orch_monitor = True  # type: ignore[attr-defined]
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return path


def make_api_logger(
    logger: logging.Logger | None = None,
) -> Callable[[str, str, int, float], None]:
    """Callback zgodny z OrchestratorClient(on_request=...): 'GET Jobs 200 123 ms'."""
    log = logger or logging.getLogger(f"{LOGGER_NAME}.api")

    def on_request(method: str, path: str, status: int, elapsed_ms: float) -> None:
        text = f"{method} {path} {status} {elapsed_ms:.0f} ms"
        if status in (401, 403):
            log.error("Błąd autoryzacji: %s", text)
        elif status == 0 or status >= 400:
            log.warning(text)
        else:
            log.info(text)

    return on_request


def log_auth_error(exc: BaseException, logger: logging.Logger | None = None) -> None:
    """Loguje blad autoryzacji jako ERROR (komunikat bez sekretu)."""
    (logger or logging.getLogger(f"{LOGGER_NAME}.auth")).error("Błąd autoryzacji: %s", exc)
