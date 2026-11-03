"""UX-BIND-001. Column, type in words, read-only, and the problem badge."""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.diagnostics import Severity
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.data.publish import publish_session, warning_rows
from app.features.form_builder.qtside.data_panel.edits import bind_field, set_read_only
from app.features.form_builder.qtside.data_panel.host import narrate, session_of
from app.features.form_builder.qtside.data_panel.model import (
    FIELD_CLASSES,
    bind_text,
    column_engine,
    column_kind,
    read_only,
    record_source,
    table_of,
)
from app.features.form_builder.qtside.inspector.data_ext import DataSection
from app.qt.QtWidgets import QCheckBox, QComboBox, QLabel, QVBoxLayout, QWidget


class _Binding(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.inspectorData.binding")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        self._column_label = QLabel("Column", self)
        self._column_label.setObjectName("formBuilder.inspectorData.columnLabel")
        layout.addWidget(self._column_label)
        self._column = QComboBox(self)
        self._column.setObjectName("formBuilder.inspectorData.column")
        layout.addWidget(self._column)
        self._words = QLabel(self)
        self._words.setObjectName("formBuilder.inspectorData.typeWords")
        self._words.setWordWrap(True)
        self._words.setProperty("fbFaint", True)
        layout.addWidget(self._words)
        self._read_only = QCheckBox("Only show, never save", self)
        self._read_only.setObjectName("formBuilder.inspectorData.readOnly")
        layout.addWidget(self._read_only)
        self._problem = QLabel(self)
        self._problem.setObjectName("formBuilder.inspectorData.problem")
        self._problem.setWordWrap(True)
        self._problem.hide()
        layout.addWidget(self._problem)
        self._column.currentIndexChanged.connect(self._on_column)
        self._read_only.toggled.connect(self._on_read_only)
        self._filling = False

    def refresh(self) -> None:
        session = session_of(self)
        if session is not None:
            publish_session(session)
        self._filling = True
        self._column.blockSignals(True)
        self._read_only.blockSignals(True)
        self._column.clear()
        self._column.addItem("Bind", "")
        node = _selected_field(session)
        source = record_source(session.document) if session is not None else None
        names: tuple = ()
        if source is not None and session is not None:
            table = table_of(session.document, source)
            names = tuple(column.name for column in getattr(table, "columns", ()) or ())
            for name in names:
                self._column.addItem(name, name)
        current = bind_text(node) if node is not None else ""
        found = self._column.findData(current)
        self._column.setCurrentIndex(found if found >= 0 else 0)
        self._column_label.setText("Column" if current else "Not bound")
        self._words.setText(_words(session, source, current))
        self._read_only.setChecked(read_only(node) if node is not None else False)
        self._read_only.setEnabled(bool(current))
        message, severity = _problem(session, node)
        self._problem.setText(message)
        self._problem.setProperty("fbProblem", "error" if severity is Severity.ERROR else "warning")
        self._problem.setVisible(bool(message))
        self._column.blockSignals(False)
        self._read_only.blockSignals(False)
        self._filling = False

    def _on_column(self, index: int) -> None:
        if self._filling:
            return
        session = session_of(self)
        node = _selected_field(session)
        if session is None or node is None:
            return
        column = str(self._column.itemData(index) or "")
        try:
            bind_field(session, node.id, column, read_only=self._read_only.isChecked() and bool(column))
        except CommandRejected as exc:
            narrate(self, str(exc))
        self.refresh()

    def _on_read_only(self, checked: bool) -> None:
        if self._filling:
            return
        session = session_of(self)
        node = _selected_field(session)
        if session is None or node is None or not bind_text(node):
            return
        try:
            set_read_only(session, node.id, checked)
        except CommandRejected as exc:
            narrate(self, str(exc))
        self.refresh()


def _create(parent: QWidget) -> QWidget:
    return _Binding(parent)


def _applies(class_name: str) -> bool:
    return class_name in FIELD_CLASSES


def register(registry: object) -> None:
    getattr(registry, "add")(DataSection("binding", 30, _create, _applies))


def _selected_field(session: object) -> Optional[WidgetNode]:
    if session is None:
        return None
    selection = getattr(session, "selection", None)
    state = getattr(selection, "state", None)
    ids = getattr(state, "ids", ()) or ()
    if len(ids) != 1:
        return None
    document = session.document
    if not document.contains(ids[0]):
        return None
    node = document.node(ids[0])
    if isinstance(node, WidgetNode) and node.class_name in FIELD_CLASSES and node.id != document.root.id:
        return node
    return None


def _words(session: object, source: object, column: str) -> str:
    if session is None or source is None or not column:
        return ""
    table = table_of(session.document, source)
    for item in getattr(table, "columns", ()) or ():
        if item.name == column:
            kind = column_kind(item, column_engine(session.document, source, session), lookup=True)
            return str(getattr(kind, "words", ""))
    return ""


def _problem(session: object, node: Optional[WidgetNode]) -> tuple:
    if session is None or node is None:
        return "", None
    rows = warning_rows(session, node.id)
    if not rows:
        return "", None
    row = rows[0]
    return row.message, row.severity
