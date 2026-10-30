"""Every step on the form, when the form itself is selected (UX-BEH-016)."""

from __future__ import annotations

from app.qt.QtCore import Qt
from app.qt.QtWidgets import QLabel, QLineEdit, QVBoxLayout, QWidget
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.qtside.inspector._services import Dropped, Rejected
from app.features.form_builder.qtside.inspector.behavior_ext import BehaviorSection, SectionHost, SectionInputs
from app.features.form_builder.qtside.inspector.behavior_ext._rows import FormRow, Gesture, finish, project_form


class FormEventsBody(QWidget):
    def __init__(self, host: SectionHost) -> None:
        super().__init__(host.parent)
        self.setObjectName("formBuilder.events.form")
        self._services = host.services
        self._chrome = host.services.chrome
        self._rows: tuple = ()
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 4, 0, 4)
        self._title = QLabel(self)
        column.addWidget(self._title)
        self._filter = QLineEdit(self)
        self._filter.setObjectName("formBuilder.events.formFilter")
        self._filter.setAccessibleName("Search events")
        self._filter.setPlaceholderText("Search events")
        self._filter.textChanged.connect(self._refill)
        column.addWidget(self._filter)
        self._list = QVBoxLayout()
        column.addLayout(self._list)
        self._empty = QLabel("No events on this form yet.", self)
        column.addWidget(self._empty)

    def apply_colors(self, panel: str, text: str) -> None:
        chrome = self._chrome
        self._filter.setStyleSheet(
            "QLineEdit { color: %s; background: %s; border: 1px solid %s; padding: 2px 6px; }"
            "QLineEdit:focus { border: %dpx solid %s; }"
            % (text, chrome.input, chrome.border, chrome.focus_width, chrome.accent)
        )

    def paint(self, inputs: SectionInputs) -> None:
        self._chrome = self._services.chrome
        self._rows = project_form(inputs.session.document, QtClassTable.shared())
        self._title.setText("ALL EVENTS ON THIS FORM %d" % len(self._rows))
        self._refill()

    def _refill(self, _text: str = "") -> None:
        while self._list.count():
            item = self._list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        needle = self._filter.text().casefold().strip()
        shown = [row for row in self._rows if not needle or needle in row.words.casefold() or needle in row.sender.casefold()]
        self._empty.setText("No events on this form yet." if not self._rows else "")
        if needle and self._rows and not shown:
            self._empty.setText("Nothing matches \u201c%s\u201d." % self._filter.text())
        self._empty.setVisible(bool(self._empty.text()))
        for row in shown:
            self._list.addWidget(_FormRow(row, self))

    def go(self, row: FormRow) -> None:
        parent = self.parent()
        events = getattr(parent, "section_widget", None)
        body = events("events") if callable(events) else None
        note = getattr(body, "note_added", None)
        if callable(note):
            note(row.signal, row.index)
        found = self._services.session.document.by_name(row.sender)
        if found:
            self._services.session.selection.set((found[0],), source=SelectionSource.PROGRAM)

    def delete(self, row: FormRow) -> None:
        doc = self._services.session.document
        outcome = finish(doc, QtClassTable.shared(), row.sender, Gesture("delete", row.signal, row.index))
        if outcome is None or outcome.command is None:
            return
        result = self._services.execute(outcome.command)
        if isinstance(result, (Rejected, Dropped)):
            return


class _FormRow(QLabel):
    def __init__(self, row: FormRow, body: FormEventsBody) -> None:
        super().__init__(row.words, body)
        self.setWordWrap(True)
        self.setMinimumWidth(0)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        chrome = body._services.chrome
        self.setStyleSheet(
            "QLabel:focus { border: %dpx solid %s; }" % (chrome.focus_width, chrome.accent)
        )
        self.setAccessibleName(row.words)
        self._row = row
        self._body = body
        if row.missing:
            self.setStyleSheet("color: %s;" % body._chrome.error)

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = enum_value(event.key())  # type: ignore[attr-defined]
        if key in (enum_value(Qt.Key.Key_Return), enum_value(Qt.Key.Key_Enter)):
            self._body.go(self._row)
            return
        if key == enum_value(Qt.Key.Key_Delete):
            self._body.delete(self._row)
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]


def _applies(inputs: SectionInputs) -> bool:
    return inputs.is_form


def _create(host: SectionHost) -> QWidget:
    return FormEventsBody(host)


def register(registry: object) -> None:
    registry.add(BehaviorSection("form_events", 40, _create, _applies))  # type: ignore[attr-defined]
