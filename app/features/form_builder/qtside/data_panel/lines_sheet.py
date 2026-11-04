"""Add lines sheet (UX-LINES-001). One undo step."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import InsertFragment, SetLogic
from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.data.schema import schema_for
from app.features.form_builder.engine.data.source import (
    CalcColumn,
    DataColumn,
    Lookup,
    Rows,
    read_rows,
    write_rows,
)
from app.features.form_builder.engine.data.types import describe
from app.features.form_builder.engine.project.table_form import label_from_column
from app.features.form_builder.engine.logic.codec import Step
from app.features.form_builder.engine.logic.events_codec import EventStep
from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import (
    EnumValue,
    NumberValue,
    SizePolicyValue,
    SizeValue,
    StringValue,
)
from app.features.form_builder.qtside.data_panel.edits import _box_placement
from app.features.form_builder.qtside.data_panel.host import narrate, session_of
from app.features.form_builder.qtside.data_panel.model import column_engine, record_source
from app.qt.QtCore import Qt
from app.qt.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import exec_qt

_MARGINS = ("leftMargin", "topMargin", "rightMargin", "bottomMargin")


def child_tables(document: object, source: object) -> Tuple[object, ...]:
    """Tables with a column that points at the form's table."""

    cached = schema_for(document, getattr(source, "connection", ""))
    if cached is None:
        return ()
    parent = getattr(source, "table", "")
    found = []
    for table in getattr(cached, "tables", ()) or ():
        if table.name == parent:
            continue
        if any(_points(column, parent) for column in table.columns):
            found.append(table)
    return tuple(found)


def lines_on(document: object) -> Tuple[Tuple[str, Rows], ...]:
    walk = getattr(document, "iter_widgets", None)
    if not callable(walk):
        return ()
    found = []
    try:
        nodes = tuple(walk())
    except Exception:
        return ()
    for node in nodes:
        name = getattr(node, "object_name", "") or ""
        entry = node.prop("cbcsRows") if hasattr(node, "prop") else None
        value = getattr(entry, "value", None)
        text = getattr(value, "text", "")
        if not isinstance(text, str) or not text.strip():
            continue
        rows, error = read_rows(text)
        if error is None and rows is not None:
            found.append((name, rows))
    return tuple(found)


def add_lines(session: object, rows: Rows, view_name: str = "") -> str:
    """Insert the grid, or bind the selected table view, plus the two buttons."""

    document = session.document
    layout = document.root.layout
    if layout is None or not isinstance(layout, LayoutNode):
        raise CommandRejected("This form has no layout to put the lines in.")
    selected = _selected_view(session)
    name = selected.object_name if selected is not None and selected.object_name else view_name or _view_name(rows.table)
    with session.log.transaction("Add lines") as txn:
        if selected is None:
            spec = _lines_box(name)
            result = txn.execute(InsertFragment(_box_placement(layout), Fragment((spec,)), undo_label="Add lines"))
            mapping = dict(result.renames)
            final = mapping.get(name, name)
            ids = document.by_name(final)
            if not ids:
                raise CommandRejected("The lines grid was not added.")
            view_id = ids[0]
        else:
            final = name
            view_id = selected.id
            mapping = _insert_buttons(txn, document, layout)
        txn.execute(SetLogic(view_id, "cbcsRows", write_rows(rows)))
        _steps(txn, document, mapping.get("addLineButton", "addLineButton"), "addRow", final)
        _steps(txn, document, mapping.get("deleteLineButton", "deleteLineButton"), "deleteRow", final)
    return final


def set_lines(session: object, node_id: object, rows: Rows) -> None:
    with session.log.transaction("Edit lines") as txn:
        txn.execute(SetLogic(node_id, "cbcsRows", write_rows(rows)))


def open_lines_sheet(host: QWidget, *, edit_name: str = "") -> None:
    session = session_of(host)
    if session is None:
        return
    try:
        sheet = LinesSheet(host, session, edit_name)
    except CommandRejected as exc:
        narrate(host, str(exc))
        return
    exec_qt(sheet)


class LinesSheet(QDialog):
    """The rows UX-LINES-001 lists. [Add lines] is one undo step."""

    def __init__(self, parent: QWidget, session: object, edit_name: str = "") -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.data.linesSheet")
        self.setWindowTitle("Lines")
        self._session = session
        self._edit_name = edit_name
        source = record_source(session.document)
        if source is None:
            raise CommandRejected("Connect this form to a table first.")
        self._source = source
        self._tables = child_tables(session.document, source)
        existing = dict(lines_on(session.document))
        self._existing = existing.get(edit_name) if edit_name else None
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        self._from = QComboBox(self)
        self._from.setObjectName("formBuilder.data.linesFrom")
        for table in self._tables:
            self._from.addItem(table.name, table.name)
        if self._existing is not None:
            found = self._from.findData(self._existing.table)
            if found >= 0:
                self._from.setCurrentIndex(found)
        form.addRow("Lines from", self._from)
        self._link = QComboBox(self)
        self._link.setObjectName("formBuilder.data.linesLink")
        form.addRow("Linked by", self._link)
        self._order = QComboBox(self)
        self._order.setObjectName("formBuilder.data.linesOrder")
        form.addRow("Order by", self._order)
        self._number = QComboBox(self)
        self._number.setObjectName("formBuilder.data.linesNumber")
        form.addRow("Number lines in", self._number)
        self._columns = QTableWidget(0, 7, self)
        self._columns.setObjectName("formBuilder.data.linesColumns")
        self._columns.setHorizontalHeaderLabels(
            ["Include", "Column", "Header", "Kind", "Default", "Lookup", "Read-only"]
        )
        layout.addWidget(self._columns)
        calc_row = QHBoxLayout()
        self._calc_name = QLineEdit(self)
        self._calc_name.setPlaceholderText("Name")
        self._calc_header = QLineEdit(self)
        self._calc_header.setPlaceholderText("Header")
        self._calc_formula = QLineEdit(self)
        self._calc_formula.setPlaceholderText("Formula")
        add_calc = QPushButton("+ Calculated column", self)
        add_calc.setObjectName("formBuilder.data.linesCalc")
        add_calc.clicked.connect(self._add_calc)
        calc_row.addWidget(self._calc_name)
        calc_row.addWidget(self._calc_header)
        calc_row.addWidget(self._calc_formula)
        calc_row.addWidget(add_calc)
        layout.addLayout(calc_row)
        self._calcs: List[CalcColumn] = []
        buttons = QDialogButtonBox(self)
        word = "Add lines" if self._existing is None else "Save"
        accept = buttons.addButton(word, QDialogButtonBox.ButtonRole.AcceptRole)
        accept.setObjectName("formBuilder.data.linesAccept")
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._from.currentIndexChanged.connect(self._fill)
        self._fill()

    def _fill(self) -> None:
        table = self._current_table()
        self._link.clear()
        self._order.clear()
        self._number.clear()
        self._columns.setRowCount(0)
        self._calcs = []
        self._number.addItem("none", "")
        if table is None:
            return
        parent = self._source.table
        links = [column for column in table.columns if _points(column, parent)]
        for column in links or list(table.columns):
            self._link.addItem(column.name, column.name)
        for column in table.columns:
            self._order.addItem(column.name, column.name)
            self._number.addItem(column.name, column.name)
        _prefer(self._link, self._existing.link if self._existing is not None else (links[0].name if links else ""))
        order = self._existing.order if self._existing is not None else _guess_order(table)
        _prefer(self._order, order)
        number = self._existing.position if self._existing is not None else order
        _prefer(self._number, number)
        engine = column_engine(self._session.document, self._source, self._session)
        shown = {}
        if self._existing is not None:
            for column in self._existing.columns:
                if isinstance(column, DataColumn):
                    shown[column.column] = column
                elif isinstance(column, CalcColumn):
                    self._calcs.append(column)
        for column in table.columns:
            if column.name == getattr(table, "key", None):
                continue
            self._add_column_row(column, engine, shown.get(column.name), parent)

    def _add_column_row(self, column: object, engine: str, existing: Optional[DataColumn], parent: str) -> None:
        row = self._columns.rowCount()
        self._columns.insertRow(row)
        include = QTableWidgetItem()
        include.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        checked = existing is not None or (column.name != self._link.currentData() and column.name != self._number.currentData())
        include.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._columns.setItem(row, 0, include)
        name = QTableWidgetItem(column.name)
        name.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self._columns.setItem(row, 1, name)
        header = QTableWidgetItem(existing.header if existing is not None and existing.header else _header(column.name))
        self._columns.setItem(row, 2, header)
        ref = column.references.table if column.references is not None else ""
        kind = describe(column.type, engine=engine, column_name=column.name, references_table=ref, nullable=column.nullable)
        kind_item = QTableWidgetItem(kind.words)
        kind_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self._columns.setItem(row, 3, kind_item)
        default = QTableWidgetItem(existing.default if existing is not None else "")
        self._columns.setItem(row, 4, default)
        lookup = QTableWidgetItem()
        lookup.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        use_lookup = (existing is not None and existing.lookup is not None) or bool(ref and ref != parent)
        lookup.setCheckState(Qt.CheckState.Checked if use_lookup else Qt.CheckState.Unchecked)
        self._columns.setItem(row, 5, lookup)
        locked = QTableWidgetItem()
        locked.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        locked.setCheckState(
            Qt.CheckState.Checked if existing is not None and existing.read_only else Qt.CheckState.Unchecked
        )
        self._columns.setItem(row, 6, locked)

    def _add_calc(self) -> None:
        name = self._calc_name.text().strip()
        formula = self._calc_formula.text().strip()
        if not name or not formula:
            return
        self._calcs.append(CalcColumn(name, formula, self._calc_header.text().strip()))
        self._calc_name.clear()
        self._calc_header.clear()
        self._calc_formula.clear()

    def _accept(self) -> None:
        table = self._current_table()
        link = str(self._link.currentData() or "")
        if table is None or not link:
            narrate(self, "Choose the table these lines come from.")
            return
        columns: List[object] = []
        for row in range(self._columns.rowCount()):
            include = self._columns.item(row, 0)
            if include is None or include.checkState() != Qt.CheckState.Checked:
                continue
            name_item = self._columns.item(row, 1)
            header_item = self._columns.item(row, 2)
            default_item = self._columns.item(row, 4)
            lookup_item = self._columns.item(row, 5)
            locked_item = self._columns.item(row, 6)
            name = "" if name_item is None else name_item.text()
            schema_column = _named(table, name)
            lookup = None
            if lookup_item is not None and lookup_item.checkState() == Qt.CheckState.Checked and schema_column is not None:
                lookup = _lookup_for(schema_column)
            columns.append(
                DataColumn(
                    name,
                    "" if header_item is None else header_item.text(),
                    "",
                    lookup,
                    "" if default_item is None else default_item.text(),
                    locked_item is not None and locked_item.checkState() == Qt.CheckState.Checked,
                )
            )
        columns.extend(self._calcs)
        if not columns:
            narrate(self, "Include at least one column.")
            return
        rows = Rows(
            table.name,
            link,
            str(getattr(table, "key", None) or "id"),
            tuple(columns),
            str(self._order.currentData() or ""),
            str(self._number.currentData() or ""),
        )
        try:
            if self._existing is None:
                add_lines(self._session, rows)
            else:
                ids = self._session.document.by_name(self._edit_name)
                if not ids:
                    raise CommandRejected("That lines grid is gone.")
                set_lines(self._session, ids[0], rows)
        except CommandRejected as exc:
            narrate(self, str(exc))
            return
        self.accept()

    def _current_table(self):
        name = str(self._from.currentData() or "")
        for table in self._tables:
            if table.name == name:
                return table
        return self._tables[0] if self._tables else None


def _lines_box(view: str) -> NodeSpec:
    grid = NodeSpec(
        "widget",
        None,
        (("class_name", "QTableView"), ("object_name", view)),
        (
            PropertyEntry("property", "minimumHeight", NumberValue(120)),
            PropertyEntry("property", "sizePolicy", SizePolicyValue("Expanding", "Expanding")),
        ),
    )
    buttons = _button_row()
    items = tuple(
        NodeSpec("layoutitem", None, (), (), (), (("content", (widget,)),)) for widget in (grid, buttons)
    )
    return NodeSpec(
        "layout",
        None,
        (("class_name", "QVBoxLayout"), ("object_name", "linesBox")),
        tuple(PropertyEntry("property", margin, NumberValue(0)) for margin in _MARGINS),
        (),
        (("layout_items", items),),
    )


def _button_row() -> NodeSpec:
    add = _line_button("addLineButton", "Add line")
    delete = _line_button("deleteLineButton", "Delete line")
    spacer = NodeSpec(
        "spacer",
        None,
        (("name", "lineButtonSpacer"),),
        (
            PropertyEntry("property", "orientation", EnumValue("Qt::Horizontal")),
            PropertyEntry("property", "sizeHint", SizeValue(40, 20)),
        ),
    )
    items = tuple(
        NodeSpec("layoutitem", None, (), (), (), (("content", (widget,)),))
        for widget in (spacer, add, delete)
    )
    return NodeSpec(
        "layout",
        None,
        (("class_name", "QHBoxLayout"), ("object_name", "lineButtons")),
        tuple(PropertyEntry("property", margin, NumberValue(0)) for margin in _MARGINS),
        (),
        (("layout_items", items),),
    )


def _insert_buttons(txn: object, document: object, layout: LayoutNode) -> dict:
    del document
    result = txn.execute(InsertFragment(_box_placement(layout), Fragment((_button_row(),)), undo_label="Add lines"))
    return dict(getattr(result, "renames", ()) or ())


def _steps(txn: object, document: object, button: str, verb: str, view: str) -> None:
    ids = document.by_name(button)
    if not ids:
        return
    node = document.node(ids[0])
    final = getattr(node, "object_name", button) or button
    txn.execute(
        SetEventSteps(
            final,
            "clicked",
            (EventStep(verb, raw=Step(verb, fields=(("grid", view),))),),
            caption="Add lines",
        )
    )


def _selected_view(session: object) -> Optional[WidgetNode]:
    selection = getattr(session, "selection", None)
    state = getattr(selection, "state", None)
    ids = getattr(state, "ids", ()) or ()
    if len(ids) != 1:
        return None
    document = session.document
    if not document.contains(ids[0]):
        return None
    node = document.node(ids[0])
    if isinstance(node, WidgetNode) and node.class_name == "QTableView" and node.id != document.root.id:
        return node
    return None


def _view_name(table: str) -> str:
    from app.features.form_builder.engine.project.table_form import column_widget_name

    return "%sView" % column_widget_name(table, ())


def _line_button(object_name: str, text: str) -> NodeSpec:
    return NodeSpec(
        "widget",
        None,
        (("class_name", "QPushButton"), ("object_name", object_name)),
        (
            PropertyEntry("property", "text", StringValue(text)),
            PropertyEntry("property", "sizePolicy", SizePolicyValue("Fixed", "Fixed")),
        ),
    )


def _points(column: object, parent: str) -> bool:
    ref = getattr(column, "references", None)
    return getattr(ref, "table", "") == parent


def _guess_order(table: object) -> str:
    names = [column.name for column in table.columns]
    for candidate in ("line_no", "position", "sort"):
        if candidate in names:
            return candidate
    key = getattr(table, "key", None)
    return str(key or (names[0] if names else ""))


def _prefer(box: QComboBox, name: str) -> None:
    found = box.findData(name)
    if found >= 0:
        box.setCurrentIndex(found)


def _header(name: str) -> str:
    return label_from_column(name)


def _named(table: object, name: str):
    for column in table.columns:
        if column.name == name:
            return column
    return None


def _lookup_for(column: object) -> Optional[Lookup]:
    ref = column.references
    if ref is None:
        return None
    show = "name"
    return Lookup(ref.table, ref.column or "id", show, show, ())


def _sentence(table: str, view: str) -> str:
    return "Lines from %s → %s" % (table, view)


def summary(document: object) -> str:
    found = lines_on(document)
    if not found:
        return ""
    name, rows = found[0]
    return _sentence(rows.table, name or _view_name(rows.table))

