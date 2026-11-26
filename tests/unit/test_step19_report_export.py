import io
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import load_workbook

from orch_monitor.clock import WARSAW
from orch_monitor.reports.csv_export import export_report_csv_zip, write_csv
from orch_monitor.reports.model import (
    DayStats,
    ErrorEntry,
    ProcessStats,
    QueueStats,
    Report,
    Summary,
)
from orch_monitor.reports.periods import period_week
from orch_monitor.reports.xlsx_export import export_report_xlsx, report_filename


def make_report(ok: bool = False) -> Report:
    p = period_week(date(2026, 11, 26))
    return Report(
        period=p,
        folders=["Finance"],
        summary=Summary(ok, 5, 10, 0 if ok else 1, 2, 0 if ok else 1),
        processes=[ProcessStats("Raport; dzienny", 5, 4, 1, 0, timedelta(minutes=20))],
        queues=[
            QueueStats("Faktury_IN", "Finance", 8, 1, 1, 80.0),
            QueueStats("Pusta", "Finance", 0, 0, 0, None),
        ],
        days=[DayStats(d, 0, 0, 0, True) for d in p.days[:2]]
        + [DayStats(p.days[2], 1, 1, 0, False)],
        errors=[
            ErrorEntry(
                "Faulted",
                datetime(2026, 11, 25, 10, 10, tzinfo=WARSAW),
                "Raport",
                "Finance",
                "Błąd ąę",
            )
        ],
    )


def test_TC_19_1_sheets(tmp_path: Path) -> None:
    out = tmp_path / "r.xlsx"
    export_report_xlsx(make_report(), out)
    wb = load_workbook(out)
    assert wb.sheetnames == ["Podsumowanie", "Procesy", "Kolejki", "Dni", "Błędy"]
    assert wb["Procesy"]["A2"].value == "Raport; dzienny"
    assert wb["Podsumowanie"]["A1"].font.bold and wb["Kolejki"]["A1"].font.bold


def test_TC_19_2_dates_and_percent(tmp_path: Path) -> None:
    out = tmp_path / "r.xlsx"
    export_report_xlsx(make_report(), out)
    wb = load_workbook(out)
    cell = wb["Dni"]["A2"]
    assert isinstance(cell.value, datetime) and cell.is_date
    err = wb["Błędy"]["B2"]
    assert err.is_date and err.value == datetime(2026, 11, 25, 10, 10) and err.value.tzinfo is None
    pct = wb["Kolejki"]["F2"]
    assert pct.value == 0.8 and pct.number_format == "0.0%"
    assert wb["Kolejki"]["F3"].value is None
    assert wb["Podsumowanie"]["B2"].is_date


def test_TC_19_3_verdict_colors(tmp_path: Path) -> None:
    bad, good = tmp_path / "b.xlsx", tmp_path / "g.xlsx"
    export_report_xlsx(make_report(False), bad)
    export_report_xlsx(make_report(True), good)
    c = load_workbook(bad)["Podsumowanie"]["B5"]
    assert c.value == "Z błędami" and c.fill.start_color.rgb.endswith("FFC7CE")
    c = load_workbook(good)["Podsumowanie"]["B5"]
    assert c.value == "Bez błędów" and c.fill.start_color.rgb.endswith("C6EFCE")


def test_TC_19_4_csv_zip(tmp_path: Path) -> None:
    out = tmp_path / "r.zip"
    export_report_csv_zip(make_report(), out)
    with zipfile.ZipFile(out) as zf:
        assert sorted(zf.namelist()) == [
            "bledy.csv",
            "dni.csv",
            "kolejki.csv",
            "podsumowanie.csv",
            "procesy.csv",
        ]
        for name in zf.namelist():
            assert zf.read(name).startswith(b"\xef\xbb\xbf")
        text = zf.read("kolejki.csv").decode("utf-8-sig")
        assert text.splitlines()[0] == "Kolejka;Folder;Sukcesy;AE;BE;% sukcesu"
        assert "Faktury_IN;Finance;8;1;1;80,0" in text
        assert '"Raport; dzienny";5;4;1;0;0:20:00' in zf.read("procesy.csv").decode("utf-8-sig")
        assert "Błąd ąę" in zf.read("bledy.csv").decode("utf-8-sig")
        assert "Z błędami" in zf.read("podsumowanie.csv").decode("utf-8-sig")


def test_write_csv_to_path_and_fileobj(tmp_path: Path) -> None:
    f = tmp_path / "a.csv"
    write_csv([[1, "ż"]], ["a", "b"], f)
    assert f.read_bytes() == b"\xef\xbb\xbfa;b\r\n1;\xc5\xbc\r\n"
    buf = io.StringIO()
    write_csv([[1, 2]], ["x", "y"], buf)
    assert buf.getvalue() == "x;y\r\n1;2\r\n"


def test_TC_19_5_filename() -> None:
    p = period_week(date(2026, 11, 26))
    assert report_filename(p, "xlsx") == "raport_2026-11-23_2026-11-29.xlsx"
    assert report_filename(p, ".zip") == "raport_2026-11-23_2026-11-29.zip"
