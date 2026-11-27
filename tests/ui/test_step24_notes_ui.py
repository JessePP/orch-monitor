import dataclasses
from datetime import UTC, datetime, timedelta
from pathlib import Path

from helpers import NOW, make_snapshot
from pytestqt.qtbot import QtBot

from orch_monitor.app import notes_store_for
from orch_monitor.clock import to_local
from orch_monitor.config.notes import ErrorRef, NotesStore
from orch_monitor.config.settings import Settings, load_settings
from orch_monitor.services.jobs import FaultedJob
from orch_monitor.services.queue_details import DetailsResult, Kind, QueueItemDetail
from orch_monitor.services.queues import QueueRow
from orch_monitor.ui.notes_dialog import LOCAL_HINT, NotesDialog
from orch_monitor.ui.queue_details_dialog import NOTES_COL, QueueDetailsDialog
from orch_monitor.ui.settings_dialog import SettingsDialog
from orch_monitor.ui.tab_jobs import FAULTED_NOTES_COL, JobsTab

QUEUE = QueueRow(7, "Q1", "Finance", 9, 3, 0, 90.0, None, 1, 2, to_local(NOW))
T = datetime(2026, 11, 26, 11, 0, 5, tzinfo=UTC)
REF = ErrorRef("queue_item", 2, "Kolejka Q1 (Finance) · REF-2", "AE: Błąd 2")


def _notes(base: Path | None, author: str = "jan", t: datetime = T) -> NotesStore:
    return NotesStore(base, "Prod", author=author, clock=lambda: t)


def _provider(row: QueueRow, kind: Kind) -> DetailsResult:
    return DetailsResult(
        [
            QueueItemDetail(i, f"REF-{i}", "AE", f"Błąd {i}", to_local(NOW), "BOT01")
            for i in range(1, 4)
        ]
    )


def test_TC_24_7_add_note_in_dialog(qtbot: QtBot, tmp_path: Path) -> None:
    store = _notes(tmp_path)
    d = NotesDialog(REF, store)
    qtbot.addWidget(d)
    assert d.notes_list.count() == 0 and d.empty_label.isVisibleTo(d)
    assert not d.add_button.isEnabled()
    d.editor.setPlainText("   ")
    assert not d.add_button.isEnabled()
    d.editor.setPlainText("Restart maszyny pomógł")
    assert d.add_button.isEnabled()
    with qtbot.waitSignal(d.changed, timeout=1000):
        d.add_button.click()
    assert d.editor.toPlainText() == ""
    assert d.notes_list.count() == 1
    assert d.notes_list.item(0).text() == "jan · 26.11.2026 12:00\nRestart maszyny pomógł"
    assert d.location_label.text() == f"Notatki wspólne dla zespołu: {tmp_path}"


def test_TC_24_8_delete_only_own_and_refresh(qtbot: QtBot, tmp_path: Path) -> None:
    jan, ola = _notes(tmp_path, "jan"), _notes(tmp_path, "ola", T - timedelta(minutes=5))
    ola.add(REF, "Notatka Oli")
    d = NotesDialog(REF, jan)
    qtbot.addWidget(d)
    d.notes_list.setCurrentRow(0)
    assert not d.delete_button.isEnabled()  # cudza notatka
    jan.add(REF, "Moja")  # dopisana „w miedzyczasie”
    assert d.notes_list.count() == 1
    d.refresh_button.click()
    assert d.notes_list.count() == 2
    d.notes_list.setCurrentRow(1)
    assert d.delete_button.isEnabled()
    d.delete_button.click()
    assert [n.text for n in ola.notes_for(REF.key)] == ["Notatka Oli"]


def test_TC_24_9_queue_details_notes_column(qtbot: QtBot, tmp_path: Path) -> None:
    store = _notes(tmp_path)
    store.add(REF, "Już sprawdzam")
    d = QueueDetailsDialog(QUEUE, _provider, synchronous=True, notes=store, clock=lambda: T)
    qtbot.addWidget(d)
    assert d.table.horizontalHeaderItem(NOTES_COL).text() == "Notatki"
    assert not d.table.isColumnHidden(NOTES_COL)
    assert [d.table.item(r, NOTES_COL).text() for r in range(3)] == ["", "📝 1", ""]
    assert not d.notes_button.isEnabled()
    d.table.selectRow(0)
    assert d.notes_button.isEnabled()
    d.notes_button.click()
    dlg = d.notes_dialog
    assert dlg is not None and dlg.ref.key == "qi-1" and "REF-1" in dlg.ref.title
    dlg.editor.setPlainText("Nowa")
    dlg.add_note()
    assert d.table.item(0, NOTES_COL).text() == "📝 1"
    dlg2 = d.open_notes(1)
    assert dlg2 is not None and dlg2.notes_list.count() == 1
    assert dlg2.ref.detail == "AE: Błąd 2"


def test_TC_24_9_no_notes_store_hides_column(qtbot: QtBot) -> None:
    d = QueueDetailsDialog(QUEUE, _provider, synchronous=True)
    qtbot.addWidget(d)
    assert d.table.isColumnHidden(NOTES_COL) and not d.notes_button.isVisibleTo(d)
    assert d.open_notes(0) is None


def test_TC_24_10_jobs_tab_faulted_with_notes(qtbot: QtBot, tmp_path: Path) -> None:
    store = _notes(tmp_path)
    jobs = [
        FaultedJob(702, "Raport", "BOT02", to_local(NOW), "Nie znaleziono pliku", "Finance"),
        FaultedJob(701, "Faktury", "BOT01", to_local(NOW), "Timeout", "Finance"),
    ]
    store.add(ErrorRef("job", 701, "Job Faktury"), "Znany problem z SAP")
    t = JobsTab(lambda: NOW, notes=store)
    qtbot.addWidget(t)
    t.apply_snapshot(dataclasses.replace(make_snapshot(), faulted_today=jobs))
    assert t.stack.currentWidget() is not t.empty_label  # nic nie dziala, ale sa Faulted
    assert t.counter.text() == "0 działa · 0 czeka · 2 Faulted dziś"
    assert t.faulted_table.rowCount() == 2
    assert t.faulted_table.item(0, 3).text() == "Nie znaleziono pliku"
    col = [t.faulted_table.item(r, FAULTED_NOTES_COL).text() for r in range(2)]
    assert col == ["", "📝 1"]
    dlg = t.open_notes(1)
    assert dlg is not None and dlg.ref.key == "job-701" and dlg.notes_list.count() == 1
    dlg.editor.setPlainText("Druga")
    dlg.add_note()
    assert t.faulted_table.item(1, FAULTED_NOTES_COL).text() == "📝 2"
    assert JobsTab(lambda: NOW).open_notes(0) is None


def test_TC_24_11_settings_notes_folder(qtbot: QtBot, tmp_path: Path) -> None:
    saved: list[Settings] = []
    d = SettingsDialog(
        Settings(organization="acme", tenant="Prod", client_id="cid"),
        lambda *a: [],
        saved.append,
        secret_exists=True,
        settings_path=tmp_path / "s.toml",
        load_secret=lambda cid: "TAJNE",
        store_secret=lambda cid, sec: None,
        synchronous=True,
    )
    qtbot.addWidget(d)
    assert d.notes_edit.text() == ""
    d.notes_edit.setText(r"  \\serwer\zespol\OrchMonitor ")
    assert d.save()
    assert saved[0].notes_folder == r"\\serwer\zespol\OrchMonitor"
    assert load_settings(tmp_path / "s.toml").notes_folder == r"\\serwer\zespol\OrchMonitor"
    store = notes_store_for(Settings(tenant="Prod"))
    assert not store.shared
    same = notes_store_for(Settings(tenant="Prod", notes_folder=str(tmp_path)), store)
    assert same is store and store.shared and store.root == tmp_path / "Prod"


def test_TC_24_12_local_hint_and_unreachable_folder(qtbot: QtBot, tmp_path: Path) -> None:
    local = NotesDialog(REF, _notes(None))
    qtbot.addWidget(local)
    assert local.location_label.text() == LOCAL_HINT
    blocker = tmp_path / "plik"
    blocker.write_text("x", "utf-8")
    d = NotesDialog(REF, _notes(blocker))
    qtbot.addWidget(d)
    d.editor.setPlainText("Nie zapisze się")
    assert not d.add_note()
    assert d.status_label.text().startswith("Nie udało się zapisać notatek")
    assert d.editor.toPlainText() == "Nie zapisze się"  # tekst nie ginie
