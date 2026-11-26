import csv
from datetime import date
from pathlib import Path

from orch_monitor.reports.csv_queues import default_filename, export_queues_csv
from orch_monitor.services.queues import QueueRow


def _row(name: str = "Q1", pct: float | None = 80.0, change: float | None = 5.0) -> QueueRow:
    return QueueRow(1, name, "Finance", 8, 1, 1, pct, change, 2, 3, None)


def test_TC_14_5_default_filename_and_format(tmp_path: Path) -> None:
    assert default_filename(date(2026, 11, 26)) == "kolejki_2026-11-26.csv"
    p = tmp_path / default_filename(date(2026, 11, 26))
    export_queues_csv([_row(), _row("Q2", None, None)], p)
    raw = p.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(raw.decode("utf-8-sig").splitlines(), delimiter=";"))
    assert len(rows) == 3
    assert rows[0][0] == "Kolejka"
    assert rows[1][5] == "80.0%" and rows[1][6] == "▲ 5 pp"
    assert rows[2][5] == "–" and rows[2][6] == ""


def test_TC_14_6_semicolon_and_polish_chars(tmp_path: Path) -> None:
    p = tmp_path / "k.csv"
    export_queues_csv([_row("Faktury; zażółć gęślą")], p)
    text = p.read_text("utf-8-sig")
    assert '"Faktury; zażółć gęślą"' in text
    rows = list(csv.reader(text.splitlines(), delimiter=";"))
    assert rows[1][0] == "Faktury; zażółć gęślą"
