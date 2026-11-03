"""UX-LKP-001. Fill from, show, save, order, also, first item, and type-to-search."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Optional, Sequence, Tuple

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import SetLogic, SetProperty
from app.features.form_builder.engine.data.publish import publish_session, warning_rows
from app.features.form_builder.engine.data.schema import schema_for
from app.features.form_builder.engine.data.source import Lookup, read_lookup, singular, write_lookup
from app.features.form_builder.engine.diagnostics import Severity
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import BoolValue, StringValue
from app.features.form_builder.qtside.data_panel.column_insert_hooks import search_screen_command
from app.features.form_builder.qtside.data_panel.host import narrate, session_of
from app.features.form_builder.qtside.data_panel.lookup_columns import clear_show_focus, pending_show_focus
from app.features.form_builder.qtside.data_panel.model import record_source
from app.features.form_builder.qtside.inspector.data_ext import DataSection
from app.features.form_builder.engine.codegen.lookup_plan import suggest_lookup
from app.qt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

_SEARCH_ACTION = " [Use a search screen instead]"


class _Lookup(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.inspectorData.lookup")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        self._title = QLabel("Lookup", self)
        layout.addWidget(self._title)
        self._table = self._combo("formBuilder.inspectorData.lookupTable", "Fill from")
        self._rows = QLabel(self)
        self._rows.setObjectName("formBuilder.inspectorData.lookupRows")
        self._rows.setWordWrap(True)
        self._rows.hide()
        layout.addWidget(self._rows)
        self._search = QToolButton(self)
        self._search.setObjectName("formBuilder.inspectorData.lookupSearch")
        self._search.setText("[Use a search screen instead]")
        self._search.hide()
        self._search.clicked.connect(self._on_search)
        layout.addWidget(self._search)
        self._show = self._combo("formBuilder.inspectorData.lookupShow", "Show")
        self._key = self._combo("formBuilder.inspectorData.lookupKey", "Save")
        self._order = self._combo("formBuilder.inspectorData.lookupOrder", "Order by")
        row = QWidget(self)
        row.setObjectName("formBuilder.inspectorData.lookupAlsoRow")
        carried = QHBoxLayout(row)
        carried.setContentsMargins(0, 0, 0, 0)
        self._also_row = carried
        self._also_add = QToolButton(row)
        self._also_add.setObjectName("formBuilder.inspectorData.lookupAlsoAdd")
        self._also_add.setText("+")
        self._also_add.setToolTip("Also carry")
        self._also_add.setAccessibleName("Also carry")
        self._also_add.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._also_menu = QMenu(self._also_add)
        self._also_add.setMenu(self._also_menu)
        self._also_menu.aboutToShow.connect(self._fill_also_menu)
        carried.addWidget(self._also_add)
        carried.addStretch(1)
        layout.addWidget(row)
        blank_row = QWidget(self)
        blank_line = QHBoxLayout(blank_row)
        blank_line.setContentsMargins(0, 0, 0, 0)
        self._blank_on = QCheckBox("First item", blank_row)
        self._blank_on.setObjectName("formBuilder.inspectorData.lookupBlankOn")
        self._blank = QLineEdit(blank_row)
        self._blank.setObjectName("formBuilder.inspectorData.lookupBlank")
        blank_line.addWidget(self._blank_on)
        blank_line.addWidget(self._blank, 1)
        layout.addWidget(blank_row)
        self._typed = QCheckBox("Let people type to search", self)
        self._typed.setObjectName("formBuilder.inspectorData.lookupType")
        layout.addWidget(self._typed)
        self._table.currentIndexChanged.connect(self._on_table)
        self._show.currentIndexChanged.connect(self._on_show)
        self._key.currentIndexChanged.connect(self._on_key)
        self._order.currentIndexChanged.connect(self._on_order)
        self._blank_on.toggled.connect(self._on_blank_on)
        self._blank.editingFinished.connect(self._on_blank)
        self._typed.toggled.connect(self._on_typed)
        self._filling = False

    def _combo(self, name: str, caption: str) -> QComboBox:
        label = QLabel(caption, self)
        self.layout().addWidget(label)
        combo = QComboBox(self)
        combo.setObjectName(name)
        self.layout().addWidget(combo)
        return combo

    def refresh(self) -> None:
        session = session_of(self)
        if session is not None:
            publish_session(session)
        self._filling = True
        for combo in (self._table, self._show, self._key, self._order):
            combo.blockSignals(True)
        self._blank_on.blockSignals(True)
        self._typed.blockSignals(True)
        node = _selected_combo(session)
        lookup = _read(node)
        tables, columns = _schema_lists(session, lookup.table if lookup is not None else "")
        _fill(self._table, tables, lookup.table if lookup is not None else "", "(none)")
        _fill(self._show, columns, lookup.show if lookup is not None else "")
        _fill(self._key, columns, lookup.key if lookup is not None else "")
        _fill(self._order, columns, (lookup.order or lookup.show) if lookup is not None else "")
        self._paint_chips(lookup.also if lookup is not None else ())
        blank = lookup.blank if lookup is not None else ""
        column, nullable = _bound_column(session, node)
        kept = bool(nullable)
        self._blank_on.setChecked(True if kept else bool(blank))
        self._blank_on.setEnabled(not kept)
        self._blank_on.setToolTip("Kept because %s can be blank." % column if kept and column else "")
        self._blank.setText(blank or _default_blank(lookup.table if lookup is not None else ""))
        self._blank.setEnabled(kept or bool(blank))
        self._typed.setChecked(_editable(node))
        message, severity = _notice(session, node)
        sentence, action = _sentence(message)
        self._rows.setText(sentence)
        self._rows.setVisible(bool(sentence))
        self._search.setVisible(bool(action))
        if severity is Severity.ERROR:
            self._rows.setProperty("fbProblem", "error")
        elif sentence:
            self._rows.setProperty("fbProblem", "warning")
        table_name = lookup.table if lookup is not None else ""
        show_name = lookup.show if lookup is not None else ""
        self.setAccessibleName(
            "Lookup, fill from %s, show %s" % (table_name or "a table", show_name or "a column")
        )
        for combo in (self._table, self._show, self._key, self._order):
            combo.blockSignals(False)
        self._blank_on.blockSignals(False)
        self._typed.blockSignals(False)
        self._filling = False
        if session is not None and node is not None and pending_show_focus(session.document) == node.id:
            self._show.setFocus()
            clear_show_focus(session.document)

    def _on_table(self, _index: int) -> None:
        if self._filling:
            return
        name = str(self._table.currentData() or "")
        if not name:
            if self._current() is None:
                return
            self._store(None, "Clear lookup")
            return
        session = session_of(self)
        _tables, columns = _schema_lists(session, name)
        target = _table_named(session, name)
        key = getattr(target, "key", None) or "id"
        column = SimpleNamespace(references=SimpleNamespace(table=name, column=key))
        tables = _tables_of(session)
        suggested = suggest_lookup(column, tables)
        if suggested is None:
            suggested = Lookup(name, key if key in columns else (columns[0] if columns else "id"), columns[0] if columns else "name")
        self._store(suggested, "Fill from %s" % name)

    def _on_show(self, _index: int) -> None:
        self._replace("show", str(self._show.currentData() or ""), "Show %s" % (self._show.currentData() or ""))

    def _on_key(self, _index: int) -> None:
        self._replace("key", str(self._key.currentData() or ""), "Save %s" % (self._key.currentData() or ""))

    def _on_order(self, _index: int) -> None:
        self._replace("order", str(self._order.currentData() or ""), "Order by %s" % (self._order.currentData() or ""))

    def _on_also_add(self, name: str) -> None:
        if self._filling:
            return
        current = self._current()
        if not name or current is None or name in current.also:
            return
        self._store(replace(current, also=current.also + (name,)), "Also carry %s" % name)

    def _on_also_remove(self, name: str) -> None:
        if self._filling:
            return
        current = self._current()
        if current is None or name not in current.also:
            return
        self._store(replace(current, also=tuple(column for column in current.also if column != name)), "Remove %s" % name)

    def _fill_also_menu(self) -> None:
        self._also_menu.clear()
        current = self._current()
        if current is None:
            return
        _tables, columns = _schema_lists(session_of(self), current.table)
        excluded = {current.show, current.key, *current.also}
        for name in columns:
            if not name or name in excluded:
                continue
            action = self._also_menu.addAction(name)
            action.triggered.connect(lambda _checked=False, column=name: self._on_also_add(column))

    def _paint_chips(self, carried: Sequence[str]) -> None:
        while self._also_row.count():
            item = self._also_row.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self._also_add:
                widget.setParent(None)
                widget.deleteLater()
        for name in carried:
            chip = QToolButton(self._also_add.parentWidget())
            chip.setObjectName("formBuilder.inspectorData.lookupAlsoChip")
            chip.setText("%s ×" % name)
            chip.setToolTip("Remove %s" % name)
            chip.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            chip.clicked.connect(lambda _checked=False, column=name: self._on_also_remove(column))
            self._also_row.addWidget(chip)
        self._also_row.addWidget(self._also_add)
        self._also_row.addStretch(1)

    def _on_search(self) -> None:
        command = search_screen_command()
        if command is None:
            return
        current = self._current()
        command(current.table if current is not None else "")

    def _on_blank_on(self, checked: bool) -> None:
        if self._filling:
            return
        current = self._current()
        if current is None:
            return
        text = self._blank.text().strip() if checked else ""
        if checked and not text:
            text = _default_blank(current.table)
        self._store(replace(current, blank=text), "First item")

    def _on_blank(self) -> None:
        if self._filling or not self._blank_on.isChecked():
            return
        current = self._current()
        if current is None:
            return
        text = self._blank.text()
        if text == current.blank:
            return
        self._store(replace(current, blank=text), "First item")

    def _on_typed(self, checked: bool) -> None:
        if self._filling:
            return
        session = session_of(self)
        node = _selected_combo(session)
        if session is None or node is None:
            return
        try:
            with session.log.transaction("Let people type to search") as txn:
                txn.execute(SetProperty(node.id, "editable", BoolValue(bool(checked))))
        except CommandRejected as exc:
            narrate(self, str(exc))
        self.refresh()

    def _replace(self, field: str, value: str, label: str) -> None:
        if self._filling:
            return
        current = self._current()
        if current is None or not value or getattr(current, field) == value:
            return
        self._store(replace(current, **{field: value}), label)

    def _current(self) -> Optional[Lookup]:
        return _read(_selected_combo(session_of(self)))

    def _store(self, lookup: Optional[Lookup], label: str) -> None:
        if self._filling:
            return
        session = session_of(self)
        node = _selected_combo(session)
        if session is None or node is None:
            return
        text = write_lookup(lookup) if lookup is not None else None
        try:
            with session.log.transaction(label) as txn:
                txn.execute(SetLogic(node.id, "cbcsLookup", text))
        except CommandRejected as exc:
            narrate(self, str(exc))
        self.refresh()


def _create(parent: QWidget) -> QWidget:
    return _Lookup(parent)


def _applies(class_name: str) -> bool:
    return class_name == "QComboBox"


def register(registry: object) -> None:
    getattr(registry, "add")(DataSection("lookup", 40, _create, _applies))


def _selected_combo(session: object) -> Optional[WidgetNode]:
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
    if isinstance(node, WidgetNode) and (node.class_name or "") == "QComboBox" and node.id != document.root.id:
        return node
    return None


def _read(node: Optional[WidgetNode]) -> Optional[Lookup]:
    if node is None:
        return None
    entry = node.prop("cbcsLookup")
    value = getattr(entry, "value", None)
    text = value.text if isinstance(value, StringValue) else ""
    if not text:
        return None
    found, _error = read_lookup(text)
    return found


def _editable(node: Optional[WidgetNode]) -> bool:
    if node is None:
        return False
    entry = node.prop("editable")
    value = getattr(entry, "value", None)
    return isinstance(value, BoolValue) and bool(value.value)


def _schema_lists(session: object, table_name: str) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    tables = _tables_of(session)
    names = tuple(getattr(table, "name", "") for table in tables if getattr(table, "name", ""))
    if table_name and table_name not in names:
        names = names + (table_name,)
    columns = _columns(tables, table_name)
    return names, columns


def _tables_of(session: object) -> Tuple[object, ...]:
    if session is None:
        return ()
    source = record_source(session.document)
    if source is None:
        return ()
    schema = schema_for(session.document, source.connection)
    return tuple(getattr(schema, "tables", ()) or ())


def _table_named(session: object, name: str) -> object:
    for table in _tables_of(session):
        if getattr(table, "name", "") == name:
            return table
    return SimpleNamespace(key="id", columns=())


def _columns(tables: Sequence[object], table_name: str) -> Tuple[str, ...]:
    for table in tables:
        if getattr(table, "name", "") != table_name:
            continue
        return tuple(column.name for column in getattr(table, "columns", ()) or () if getattr(column, "name", ""))
    return ()


def _fill(combo: QComboBox, names: Sequence[str], current: str, placeholder: Optional[str] = None) -> None:
    combo.clear()
    if placeholder is not None:
        combo.addItem(placeholder, "")
    for name in names:
        combo.addItem(name, name)
    if current and combo.findData(current) < 0:
        combo.addItem(current, current)
    if not current:
        combo.setCurrentIndex(0)
        return
    found = combo.findData(current)
    combo.setCurrentIndex(found if found >= 0 else 0)


def _default_blank(table: str) -> str:
    if not table:
        return "(choose)"
    return "(choose a %s)" % singular(table)


def _bound_column(session: object, node: Optional[WidgetNode]) -> Tuple[str, bool]:
    if session is None or node is None:
        return "", False
    from app.features.form_builder.engine.data.source import read_bind

    column = read_bind(_text_of(node, "cbcsBind")).column
    if not column:
        return "", False
    source = record_source(session.document)
    if source is None:
        return column, False
    for table in _tables_of(session):
        if getattr(table, "name", "") != source.table:
            continue
        for item in getattr(table, "columns", ()) or ():
            if getattr(item, "name", "") == column:
                return column, bool(getattr(item, "nullable", False))
    return column, False


def _text_of(node: object, name: str) -> str:
    prop = getattr(node, "prop", None)
    if not callable(prop):
        return ""
    entry = prop(name)
    value = getattr(entry, "value", None)
    if isinstance(value, StringValue):
        return value.text
    return ""


def _sentence(message: str) -> Tuple[str, bool]:
    if not message:
        return "", False
    action = message.endswith(_SEARCH_ACTION) and search_screen_command() is not None
    if message.endswith(_SEARCH_ACTION):
        message = message[: -len(_SEARCH_ACTION)]
    return message, bool(action)


def _notice(session: object, node: Optional[WidgetNode]) -> tuple:
    if session is None or node is None:
        return "", None
    rows = warning_rows(session, node.id)
    if not rows:
        return "", None
    row = rows[0]
    return str(getattr(row, "message", "") or ""), getattr(row, "severity", None)
