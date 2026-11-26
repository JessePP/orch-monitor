from datetime import UTC, datetime
from pathlib import Path

from helpers import NOW
from pytestqt.qtbot import QtBot

from orch_monitor.clock import to_local
from orch_monitor.config.dismissed import DismissedStore
from orch_monitor.services.queue_details import DetailsResult, Kind, QueueItemDetail
from orch_monitor.services.queues import QueueRow
from orch_monitor.ui.queue_details_dialog import QueueDetailsDialog

QUEUE = QueueRow(7, "Q1", "Finance", 9, 3, 0, 90.0, None, 1, 2, to_local(NOW))
CLOCK_NOW = datetime(2026, 11, 26, 11, 0, 5, tzinfo=UTC)


class Provider:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, row: QueueRow, kind: Kind) -> DetailsResult:
        self.calls += 1
        items = [
            QueueItemDetail(i, f"REF-{i}", "AE", f"Błąd {i}", to_local(NOW), "BOT01")
            for i in range(1, 4)
        ]
        return DetailsResult(items)


def _dlg(qtbot: QtBot, provider: Provider, store: DismissedStore) -> QueueDetailsDialog:
    d = QueueDetailsDialog(QUEUE, provider, synchronous=True, store=store, clock=lambda: CLOCK_NOW)
    qtbot.addWidget(d)
    return d


def _store(tmp_path: Path) -> DismissedStore:
    return DismissedStore(tmp_path / "dismissed.json", clock=lambda: CLOCK_NOW)


def _refs(d: QueueDetailsDialog) -> list[str]:
    return [d.table.item(r, 0).text() for r in range(d.table.rowCount())]


def test_TC_23_5_dismiss_hides_without_api_call(qtbot: QtBot, tmp_path: Path) -> None:
    prov, store = Provider(), _store(tmp_path)
    d = _dlg(qtbot, prov, store)
    assert not d.dismiss_button.isEnabled()
    d.table.selectRow(1)
    assert d.dismiss_button.isEnabled()
    d.dismiss_button.click()
    assert _refs(d) == ["REF-1", "REF-3"]
    assert store.is_dismissed(2)
    assert prov.calls == 1
    assert d.info_label.text() == "Elementów: 2 · zamkniętych ukrytych: 1"


def test_TC_23_6_show_dismissed_greyed(qtbot: QtBot, tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.dismiss([2], CLOCK_NOW)
    d = _dlg(qtbot, Provider(), store)
    assert _refs(d) == ["REF-1", "REF-3"]
    d.show_dismissed_check.setChecked(True)
    assert _refs(d) == ["REF-1", "REF-2", "REF-3"]
    assert d.table.item(1, 1).text() == "AE (zamknięty)"
    assert d.table.item(1, 0).foreground().color().name() == "#8a8a8a"
    assert d.table.item(0, 1).text() == "AE"
    assert "zamkniętych: 1" in d.info_label.text()


def test_TC_23_7_restore(qtbot: QtBot, tmp_path: Path) -> None:
    prov, store = Provider(), _store(tmp_path)
    store.dismiss([2], CLOCK_NOW)
    d = _dlg(qtbot, prov, store)
    d.show_dismissed_check.setChecked(True)
    d.table.selectRow(0)
    assert not d.restore_button.isEnabled()
    d.table.selectRow(1)
    assert d.restore_button.isEnabled() and not d.dismiss_button.isEnabled()
    d.restore_button.click()
    assert not store.is_dismissed(2)
    d.show_dismissed_check.setChecked(False)
    assert _refs(d) == ["REF-1", "REF-2", "REF-3"]
    assert prov.calls == 1


def test_TC_23_8_stays_hidden_after_reopen(qtbot: QtBot, tmp_path: Path) -> None:
    store = _store(tmp_path)
    d = _dlg(qtbot, Provider(), store)
    d.table.selectRow(0)
    d.dismiss_button.click()
    d.close()
    d2 = _dlg(qtbot, Provider(), store)
    assert _refs(d2) == ["REF-2", "REF-3"]
    d3 = _dlg(qtbot, Provider(), _store(tmp_path))  # nowy store z tego samego pliku
    assert _refs(d3) == ["REF-2", "REF-3"]
