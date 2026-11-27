"""Okno notatek do jednego bledu (element kolejki AE/BE lub job Faulted)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from orch_monitor.clock import to_local
from orch_monitor.config.notes import ErrorRef, Note, NotesError, NotesStore

LOCAL_HINT = (
    "Notatki zapisywane tylko na tym komputerze. Aby zespół widział te same notatki, "
    "ustaw wspólny folder w Ustawieniach."
)


def format_note_header(note: Note) -> str:
    return f"{note.author} · {to_local(note.created_at).strftime('%d.%m.%Y %H:%M')}"


def note_count_text(n: int) -> str:
    return f"📝 {n}" if n else ""


class NotesDialog(QDialog):
    """Lista notatek (kto, kiedy, tekst), dopisywanie nowej i usuwanie wlasnej.

    Kazda zmiana emituje `changed`, zeby tabela z licznikiem notatek mogla sie odswiezyc.
    """

    changed = Signal()

    def __init__(self, ref: ErrorRef, store: NotesStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ref = ref
        self._store = store
        self._notes: list[Note] = []
        self.setWindowTitle(f"Notatki: {ref.title}")
        self.resize(560, 520)
        self.title_label = QLabel(ref.title)
        self.title_label.setStyleSheet("font-weight: bold;")
        self.title_label.setWordWrap(True)
        self.detail_label = QLabel(ref.detail)
        self.detail_label.setWordWrap(True)
        self.detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail_label.setVisible(bool(ref.detail))
        where = f"Notatki wspólne dla zespołu: {store.location}" if store.shared else LOCAL_HINT
        self.location_label = QLabel(where)
        self.location_label.setWordWrap(True)
        self.location_label.setStyleSheet("color: #616161;")
        self.notes_list = QListWidget()
        self.notes_list.setWordWrap(True)
        self.notes_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.empty_label = QLabel("Brak notatek – dodaj pierwszą poniżej")
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #b71c1c;")
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Co się stało, co sprawdzono, kto się tym zajmuje…")
        self.editor.setFixedHeight(110)
        self.add_button = QPushButton("Dodaj notatkę")
        self.delete_button = QPushButton("Usuń moją notatkę")
        self.refresh_button = QPushButton("Odśwież")
        self.refresh_button.setToolTip("Pobiera notatki dopisane w międzyczasie przez innych")
        buttons = QHBoxLayout()
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.delete_button)
        buttons.addStretch(1)
        buttons.addWidget(self.add_button)
        lay = QVBoxLayout(self)
        lay.addWidget(self.title_label)
        lay.addWidget(self.detail_label)
        lay.addWidget(self.location_label)
        lay.addWidget(self.notes_list, 1)
        lay.addWidget(self.empty_label)
        lay.addWidget(self.status_label)
        lay.addWidget(QLabel(f"Nowa notatka (autor: {store.author})"))
        lay.addWidget(self.editor)
        lay.addLayout(buttons)
        self.add_button.clicked.connect(self.add_note)
        self.delete_button.clicked.connect(self.delete_selected)
        self.refresh_button.clicked.connect(self.reload)
        self.editor.textChanged.connect(self._update_buttons)
        self.notes_list.itemSelectionChanged.connect(self._update_buttons)
        self.reload()

    def reload(self) -> None:
        try:
            self._notes = self._store.notes_for(self.ref.key)
        except NotesError as exc:
            self._notes = []
            self.status_label.setText(str(exc))
        else:
            self.status_label.setText("")
        self.notes_list.clear()
        for note in self._notes:
            item = QListWidgetItem(f"{format_note_header(note)}\n{note.text}")
            self.notes_list.addItem(item)
        self.empty_label.setVisible(not self._notes)
        if self._notes:
            self.notes_list.scrollToBottom()
        self._update_buttons()

    def selected_note(self) -> Note | None:
        row = self.notes_list.currentRow()
        if self.notes_list.selectedItems() and 0 <= row < len(self._notes):
            return self._notes[row]
        return None

    def _update_buttons(self) -> None:
        self.add_button.setEnabled(bool(self.editor.toPlainText().strip()))
        note = self.selected_note()
        self.delete_button.setEnabled(note is not None and self._store.can_delete(note))

    def add_note(self) -> bool:
        text = self.editor.toPlainText()
        if not text.strip():
            return False
        try:
            self._store.add(self.ref, text)
        except NotesError as exc:
            self.status_label.setText(str(exc))  # tekst zostaje w polu, mozna sprobowac ponownie
            return False
        self.editor.clear()
        self.reload()
        self.changed.emit()
        return True

    def delete_selected(self) -> bool:
        note = self.selected_note()
        if note is None:
            return False
        try:
            self._store.delete(self.ref.key, note)
        except NotesError as exc:
            self.status_label.setText(str(exc))
            return False
        self.reload()
        self.changed.emit()
        return True
