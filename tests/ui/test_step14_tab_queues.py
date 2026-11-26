import csv
from pathlib import Path

from helpers import NOW, make_snapshot
from pytestqt.qtbot import QtBot

from orch_monitor.clock import to_local
from orch_monitor.services.queue_details import DetailsResult, Kind, QueueItemDetail
from orch_monitor.services.queues import QueueRow
from orch_monitor.ui.tab_queues import QueuesTab


def _q(name: str = "Q1", ae: int = 0, be: int = 0, pct: float | None = 90.0,
       change: float | None = None) -> QueueRow:  # fmt: skip
    return QueueRow(7, name, "Finance", 9, ae, be, pct, change, 1, 2, to_local(NOW))


def _tab(qtbot: QtBot, rows: list[QueueRow], provider=None) -> QueuesTab:  # type: ignore[no-untyped-def]
    t = QueuesTab(provider, synchronous_details=True)
    qtbot.addWidget(t)
    t.apply_snapshot(make_snapshot(queues=rows))
    return t


def test_TC_14_1_ae_marker_red(qtbot: QtBot) -> None:
    t = _tab(qtbot, [_q(ae=3)])
    ae, be = t.table.item(0, 3), t.table.item(0, 4)
    assert ae.text() == "AE: 3"
    assert ae.foreground().color().red() > 150 and ae.foreground().color().green() < 80
    assert be.text() == "BE: 0"
    assert be.foreground().color().red() == be.foreground().color().green()  # szary


def test_TC_14_2_no_traffic(qtbot: QtBot) -> None:
    r = QueueRow(1, "Q", "F", 0, 0, 0, None, None, 0, 0, None)
    t = _tab(qtbot, [r])
    assert t.table.item(0, 5).text() == "–"
    assert t.table.item(0, 6).text() == ""


def test_TC_14_3_change_arrows(qtbot: QtBot) -> None:
    t = _tab(qtbot, [_q(change=5.0), _q(change=-3.0), _q(change=0.0)])
    assert [t.table.item(i, 6).text() for i in range(3)] == ["▲ 5 pp", "▼ 3 pp", "= 0 pp"]


def test_TC_14_4_double_click_opens_details(qtbot: QtBot) -> None:
    calls: list[tuple[int, Kind]] = []

    def provider(row: QueueRow, kind: Kind) -> DetailsResult:
        calls.append((row.queue_id, kind))
        item = QueueItemDetail(1, "REF-1", "AE", "Błąd", to_local(NOW), "BOT01")
        return DetailsResult([item], truncated=True)

    t = _tab(qtbot, [_q(ae=1)], provider)
    t.table.doubleClicked.emit(t.table.model().index(0, 0))
    dlg = t.last_dialog
    assert dlg is not None
    qtbot.addWidget(dlg)
    assert calls == [(7, "both")]
    assert dlg.table.item(0, 0).text() == "REF-1"
    assert dlg.table.item(0, 2).text() == "Błąd"
    assert "500" in dlg.info_label.text()
    dlg.kind_combo.setCurrentIndex(1)
    assert calls[-1] == (7, "AE")


def test_TC_14_4_async_loading_and_error(qtbot: QtBot) -> None:
    from orch_monitor.ui.queue_details_dialog import QueueDetailsDialog

    def boom(row: QueueRow, kind: Kind) -> DetailsResult:
        raise RuntimeError("awaria")

    dlg = QueueDetailsDialog(_q(), boom)
    qtbot.addWidget(dlg)
    qtbot.waitUntil(lambda: "awaria" in dlg.status_label.text(), timeout=3000)


def test_TC_14_5_export_csv_method(qtbot: QtBot, tmp_path: Path) -> None:
    t = _tab(qtbot, [_q("A;B")])
    p = tmp_path / "kolejki_2026-11-26.csv"
    t.export_csv(p)
    assert p.read_bytes().startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(p.read_text("utf-8-sig").splitlines(), delimiter=";"))
    assert len(rows) == 2 and rows[1][0] == "A;B"
