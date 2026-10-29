"""A label's Buddy row as a drop-down (UX-MODE-004, R3 8, R3 9).

"None", then the form's fields in reading order as "emailEdit · Line edit";
typing filters the list and Enter picks the first match. The choice is one
undo step named "Set buddy of {label}".
"""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.engine.query import tab_stops as q
from app.features.form_builder.engine.commands.catalog_ext.tab_order import SetLabelBuddy
from app.features.form_builder.qtside.inspector.api import EditorHost, EditorKey, GroupId, Registrar, RowSpec, Summary
from app.features.form_builder.qtside.inspector.words import class_words
from app.qt.QtCore import Qt
from app.qt.QtGui import QKeyEvent
from app.qt.QtWidgets import QComboBox, QCompleter, QWidget

BUDDY_PICKER = EditorKey("buddy_picker")
NONE_LABEL = "None"
_MISSING = " (not on this form)"


def choice_text(name: str, qt_class: str) -> str:
    return "%s · %s" % (name, class_words(qt_class).friendly)


class _Combo(QComboBox):
    def __init__(self, owner: "BuddyEditor", parent: QWidget) -> None:
        super().__init__(parent)
        self._owner = owner

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._owner.pick_typed()
            return
        super().keyPressEvent(event)


class BuddyEditor:
    """A Summary row: the buddy is not a Qt property, so the editor reads the document and writes ``SetLabelBuddy``."""

    def __init__(self, spec: object, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._shown: Optional[str] = None
        self._combo = _Combo(self, parent)
        self._combo.setObjectName("formBuilder.buddyPicker")
        self._combo.setAccessibleName("Buddy")
        self._combo.setEditable(True)
        self._combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        completer = QCompleter(self._combo.model(), self._combo)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._combo.setCompleter(completer)
        self._combo.activated.connect(self._activated)

    @property
    def widget(self) -> QWidget:
        return self._combo

    def show(self, value: object) -> None:
        del value
        owners = self._host.owner_ids()
        document = self._host.document()
        current = q.buddy_of(document, owners[0]) if len(owners) == 1 else None
        self._shown = current
        choices = q.buddy_choices(document)
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItem(NONE_LABEL, None)
        names = []
        for stop in choices:
            self._combo.addItem(choice_text(stop.name, stop.qt_class), stop.name)
            names.append(stop.name)
        if current is not None and current not in names:
            self._combo.addItem(current + _MISSING, current)
        index = 0 if current is None else self._combo.findData(current)
        self._combo.setCurrentIndex(max(0, index))
        self._combo.blockSignals(False)

    def is_dirty(self) -> bool:
        return False

    def pick_typed(self) -> None:
        """Enter: the first entry that contains the typed words, else the entry already chosen."""
        edit = self._combo.lineEdit()
        typed = edit.text().strip().lower() if edit is not None else ""
        if not typed or self._combo.findText(edit.text() if edit is not None else "") >= 0:
            self._activated(self._combo.currentIndex() if not typed else self._combo.findText(edit.text()))
            return
        for index in range(self._combo.count()):
            if typed in self._combo.itemText(index).lower():
                self._combo.setCurrentIndex(index)
                self._activated(index)
                return
        self._host.invalid("No widget called \u201c%s\u201d on this form." % edit.text().strip())

    def _activated(self, index: int) -> None:
        name = self._combo.itemData(index)
        if name == self._shown:
            return
        owners = self._host.owner_ids()
        session = _session_of(self._host)
        if len(owners) != 1 or session is None:
            return
        document = self._host.document()
        command = SetLabelBuddy(owners[0], None if name is None else str(name), q.caption(document, owners[0]))
        session.log.execute(command)


def _session_of(host: object) -> object:
    session = getattr(host, "session", None)
    if session is not None:
        return session
    services = getattr(host, "_services", None)
    return getattr(services, "session", None)


def register(registrar: Registrar) -> None:
    registrar.editor(BUDDY_PICKER, BuddyEditor)
    registrar.row(
        RowSpec(
            "buddyChoice",
            GroupId.CONTENT,
            "Buddy",
            "The field that gets the focus when the user presses this label's Alt letter.",
            Summary(),
            classes=("QLabel",),
            editor=BUDDY_PICKER,
        )
    )
