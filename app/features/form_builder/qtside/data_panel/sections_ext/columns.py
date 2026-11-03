"""One row per column. Drag, Enter, or Shift+Enter binds it. M8.3b owns lines."""

from __future__ import annotations

from typing import Any, Optional

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.data.source import has_data_source
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.qtside.canvas.mime_hooks import register_mime_hook, unregister_mime_hook
from app.features.form_builder.qtside.data_panel.edits import bind_or_insert, insert_column_field
from app.features.form_builder.qtside.data_panel.host import canvas_of, narrate, session_of
from app.features.form_builder.qtside.data_panel.model import (
    COLUMN_MIME,
    FIELD_CLASSES,
    bound_field,
    column_engine,
    column_kind,
    record_source,
)
from app.features.form_builder.qtside.data_panel.sections_ext import PanelSection
from app.qt.QtCore import QByteArray, Qt
from app.qt.QtGui import QDrag
from app.qt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value, event_pos


class _Hook:
    def __init__(self, section: "_Columns") -> None:
        self._section = section
        self.canvas: object = None

    def accepts(self, mime: object) -> bool:
        has = getattr(mime, "hasFormat", None)
        return bool(callable(has) and has(COLUMN_MIME))

    def hover(self, mime: object, at: tuple, copy: bool) -> None:
        del mime, at, copy

    def drop(self, mime: object, at: tuple, copy: bool) -> None:
        del copy
        column = _mime_column(mime)
        if not column:
            return
        session = session_of(self._section)
        if session is None:
            return
        node_id = _hit(self.canvas, session, at)
        found = _column(session, column)
        if found is None:
            return
        try:
            sentence = bind_or_insert(session, found, node_id)
        except CommandRejected as exc:
            narrate(self._section, str(exc))
            return
        if sentence:
            narrate(self._section, sentence)

    def leave(self) -> None:
        return None


class _Row(QWidget):
    def __init__(self, parent: QWidget, section: "_Columns", column: object) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.data.columnRow")
        self.setProperty("column", column.name)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(24)
        self._section = section
        self._column = column
        self._press: Optional[object] = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        name = QLabel(column.name, self)
        name.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        layout.addWidget(name)
        badges = QLabel(_badges(section, column), self)
        badges.setProperty("fbFaint", True)
        layout.addWidget(badges)
        words = QLabel(self)
        words.setWordWrap(True)
        words.setMaximumWidth(184)
        words.setProperty("fbFaint", True)
        layout.addWidget(words, 1)
        self._words = words
        self._bound = QPushButton(self)
        self._bound.setObjectName("formBuilder.data.bound")
        self._bound.setFlat(True)
        self._bound.clicked.connect(self._select)
        layout.addWidget(self._bound)
        self.refresh()

    def refresh(self) -> None:
        session = session_of(self._section)
        source = record_source(session.document) if session is not None else None
        engine = column_engine(session.document, source, session, self._section) if source is not None and session is not None else "sqlite"
        kind = column_kind(self._column, engine, lookup=True)
        self._words.setText(str(getattr(kind, "words", "")))
        field = bound_field(session.document, self._column.name) if session is not None else ""
        self._bound.setText(field or "(not bound)")
        if not field:
            self._bound.setProperty("fbFaint", True)
        else:
            self._bound.setProperty("fbFaint", False)
        phrase = "bound to %s" % field if field else "not bound"
        self.setAccessibleName("%s, %s, %s" % (self._column.name, getattr(kind, "words", ""), phrase))

    def _select(self) -> None:
        session = session_of(self._section)
        name = self._bound.text()
        if session is None or not name or name == "(not bound)":
            return
        ids = session.document.by_name(name)
        if ids:
            session.selection.set((ids[0],), source=SelectionSource.PROGRAM)

    def mousePressEvent(self, event: object) -> None:  # noqa: N802
        self._press = event_pos(event)
        super().mousePressEvent(event)  # type: ignore[arg-type]

    def mouseMoveEvent(self, event: object) -> None:  # noqa: N802
        if self._press is None:
            super().mouseMoveEvent(event)  # type: ignore[arg-type]
            return
        pos = event_pos(event)
        if (pos - self._press).manhattanLength() < 8:  # type: ignore[operator]
            return
        drag = QDrag(self)
        mime = _mime(self._column.name)
        drag.setMimeData(mime)
        self._press = None
        drag.exec(Qt.DropAction.CopyAction)

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = enum_value(event.key())  # type: ignore[attr-defined]
        enter = enum_value(Qt.Key.Key_Return)
        if key not in (enter, enum_value(Qt.Key.Key_Enter)):
            super().keyPressEvent(event)  # type: ignore[arg-type]
            return
        shift = enum_value(event.modifiers()) & enum_value(Qt.KeyboardModifier.ShiftModifier)  # type: ignore[attr-defined]
        session = session_of(self._section)
        if session is None:
            return
        try:
            if shift:
                _bind_selection(session, self._column)
            else:
                insert_column_field(session, self._column)
        except CommandRejected as exc:
            narrate(self, str(exc))


class _Columns(QWidget):
    def __init__(self, host: Any) -> None:
        super().__init__(host)
        self.setObjectName("formBuilder.data.columns")
        self._host = host
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._inner = QWidget()
        self._rows = QVBoxLayout(self._inner)
        self._rows.setContentsMargins(0, 0, 0, 0)
        self._scroll.setWidget(self._inner)
        layout.addWidget(self._scroll)
        self._hook = _Hook(self)
        register_mime_hook(self._hook)
        self.destroyed.connect(lambda: unregister_mime_hook(self._hook))
        self.refresh()

    def refresh(self) -> None:
        self._hook.canvas = canvas_of(self)
        while self._rows.count():
            item = self._rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        session = session_of(self)
        source = record_source(session.document) if session is not None else None
        if session is None or source is None:
            return
        from app.features.form_builder.qtside.data_panel.model import table_of

        table = table_of(session.document, source)
        for column in getattr(table, "columns", ()) or ():
            self._rows.addWidget(_Row(self._inner, self, column))
        self._rows.addStretch(1)


def _create(host: Any) -> QWidget:
    return _Columns(host)


def _applies(doc: Any) -> bool:
    return has_data_source(doc)


def register(registry: Any) -> None:
    registry.add(PanelSection("columns", 40, _create, _applies))


def _badges(section: _Columns, column: object) -> str:
    session = session_of(section)
    source = record_source(session.document) if session is not None else None
    marks = []
    if source is not None and column.name == source.key:
        marks.append("key")
    if not getattr(column, "nullable", True):
        marks.append("required")
    if getattr(column, "unique", False):
        marks.append("unique")
    return " ".join(marks)


def _mime(name: str) -> object:
    from app.qt.QtCore import QMimeData

    mime = QMimeData()
    mime.setData(COLUMN_MIME, QByteArray(name.encode("utf-8")))
    return mime


def _mime_column(mime: object) -> str:
    data = mime.data(COLUMN_MIME)  # type: ignore[attr-defined]
    raw = bytes(data) if data is not None else b""
    return raw.decode("utf-8", "replace")


def _column(session: object, name: str) -> object:
    source = record_source(session.document)
    if source is None:
        return None
    from app.features.form_builder.qtside.data_panel.model import table_of

    table = table_of(session.document, source)
    for column in getattr(table, "columns", ()) or ():
        if column.name == name:
            return column
    return None


def _hit(canvas: object, session: object, at: tuple) -> object:
    if canvas is None or not hasattr(canvas, "mapToScene"):
        return _selected(session)
    try:
        point = canvas.mapToScene(int(at[0]), int(at[1]))  # type: ignore[attr-defined]
    except Exception:
        return _selected(session)
    index = getattr(getattr(canvas, "_controller", None), "_index", None)
    if index is None:
        index = getattr(canvas, "_index", None)
    if index is None:
        return _selected(session)
    ensure = getattr(index, "ensure_fresh", None)
    if callable(ensure):
        ensure()
    hit = index.query(int(point.x()), int(point.y()))
    if hit is None:
        return _selected(session)
    node = session.document.node(hit.node)
    if isinstance(node, WidgetNode) and node.class_name in FIELD_CLASSES:
        return node.id
    return None


def _selected(session: object) -> object:
    selection = getattr(session, "selection", None)
    state = getattr(selection, "state", None)
    ids = getattr(state, "ids", ()) or ()
    if len(ids) == 1:
        return ids[0]
    return None


def _bind_selection(session: object, column: object) -> None:
    node_id = _selected(session)
    if node_id is None:
        insert_column_field(session, column)
        return
    sentence = bind_or_insert(session, column, node_id)
    if sentence:
        raise CommandRejected(sentence)

