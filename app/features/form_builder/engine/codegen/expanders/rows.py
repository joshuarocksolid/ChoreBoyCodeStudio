"""Lines grid (CONTRACTS.md section 19.1, order 420).

The model is the edit surface. ``_cbcs_plan_lines`` decides the write. Record
load, save, and dirty already call the method names this module fills in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from app.features.form_builder.engine.codegen.expanders.record import _engine
from app.features.form_builder.engine.codegen.literals import py_string
from app.features.form_builder.engine.codegen.logic_hooks import CodegenContext, Contribution, Method
from app.features.form_builder.engine.data.lines import link_position_unique
from app.features.form_builder.engine.data.schema import schema_for
from app.features.form_builder.engine.data.source import (
    CalcColumn,
    DataColumn,
    Lookup,
    RecordSource,
    Rows,
    read_data,
    read_rows,
)
from app.features.form_builder.engine.data.sql import (
    assignment_piece,
    delete_lines_for_link,
    delete_row,
    insert_row,
    is_identifier,
    key_clause,
    select_lines,
    select_lookup,
    set_line_position,
    update_head,
)
from app.features.form_builder.engine.data.types import describe
from app.features.form_builder.engine.logic import compat
from app.features.form_builder.engine.logic.formula.env import FormulaEnv
from app.features.form_builder.engine.logic.formula.nodes import Attr, Bin, Lit, Ref, Unary
from app.features.form_builder.engine.logic.formula.parse import parse_text
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import StringValue


@dataclass(frozen=True)
class _Col:
    name: str
    header: str
    kind: str
    family: str
    nullable: bool
    calculated: bool
    locked: bool
    formula: str
    default: str
    lookup: Optional[Lookup]


class RowsExpander:
    """One lines grid. A form without ``cbcsRows`` contributes nothing."""

    expander_id = "rows"
    level = 4
    order = 420

    def contribute(self, doc: UiDocument, ctx: CodegenContext) -> Contribution:
        source = _record(doc)
        if source is None:
            return Contribution()
        found = _grids(doc, ctx)
        if not found:
            return Contribution()
        view, rows = found[0]
        engine, _problem = _engine(ctx, source.connection)
        if engine not in ("sqlite", "postgres"):
            return Contribution()
        if not _names_ok(rows, view):
            return Contribution()
        columns = _columns(doc, source, rows, engine)
        if not columns:
            return Contribution()
        table = _line_table(doc, source.connection, rows.table)
        keys = () if table is None else table.unique_keys
        return _contribution(
            view,
            rows,
            columns,
            engine,
            link_position_unique(keys, rows.link, rows.position),
            table,
        )


def _contribution(view: str, rows: Rows, columns: Sequence[_Col], engine: str, unique: bool, table: object) -> Contribution:
    hidden = {rows.key, rows.link, rows.position}
    stored = tuple(column.name for column in columns if not column.calculated and column.name not in hidden)
    select_names = (rows.key,) + stored
    if rows.position and rows.position not in select_names:
        select_names = select_names + (rows.position,)
    families = {name: _family_of(name, columns, rows, table, engine) for name in select_names}
    nulls = {name: _nullable_of(name, columns, rows) for name in select_names}
    select_sql = select_lines(engine, rows.table, select_names, rows.link, rows.order or rows.position, rows.key)
    methods = [
        _method("_cbcs_load_lines", "_conn, _key", _load_body(view)),
        _method("_cbcs_save_lines", "_conn, _parent", _save_body(view, engine, rows, stored)),
        _method("_cbcs_lines_dirty", "", _dirty_body()),
        _method("_cbcs_clear_lines", "", _clear_body(view)),
        _method("_cbcs_delete_lines", "_conn, _key", _delete_link_body()),
        _method("_cbcs_validate_lines", "", _validate_body(view)),
        _method("_cbcs_add_row", "", _add_body(view, columns)),
        _method("_cbcs_delete_row", "", _delete_row_body(view)),
        _method("cbcs_read_lines", "", _read_body(view)),
        _method("_cbcs_grid_column", "_name", _grid_body(view)),
        _method("_cbcs_line_rows", "", _rows_body(view)),
        _method("_cbcs_line_dict", "_r", _dict_body(view)),
        _method("_cbcs_line_out", "_column, _value", _convert_body(families, nulls, engine, True)),
        _method("_cbcs_line_in", "_column, _value", _convert_body(families, nulls, engine, False)),
        _method("_cbcs_recompute_lines", "", _recompute_body(view, columns)),
        _method("_cbcs_line_changed", "*_args", _changed_body()),
        _method("_cbcs_line_editor", "_parent, _index", _editor_body()),
        _method("_cbcs_line_editor_data", "_editor, _index", _editor_data_body()),
        _method("_cbcs_line_commit", "_editor, _model, _index", _commit_body()),
        _method("_cbcs_line_also", "_column, _key, _name", _also_body()),
        _method("_cbcs_line_lookup_label", "_name, _key", _label_body()),
        _method("_cbcs_load_line_lookups", "_conn", _lookup_body(columns, engine)),
    ]
    imports = [
        ("PySide6.QtCore", "Qt"),
        ("PySide6.QtGui", "QBrush"),
        ("PySide6.QtGui", "QColor"),
        ("PySide6.QtGui", "QPalette"),
        ("PySide6.QtGui", "QKeySequence"),
        ("PySide6.QtGui", "QShortcut"),
        ("PySide6.QtGui", "QStandardItem"),
        ("PySide6.QtGui", "QStandardItemModel"),
        ("PySide6.QtWidgets", "QComboBox"),
        ("PySide6.QtWidgets", "QDoubleSpinBox"),
        ("PySide6.QtWidgets", "QLineEdit"),
        ("PySide6.QtWidgets", "QMessageBox"),
        ("PySide6.QtWidgets", "QSpinBox"),
        ("PySide6.QtWidgets", "QStyledItemDelegate"),
    ]
    families_used = set(families.values())
    if "decimal" in families_used or any(column.kind == "decimal" for column in columns):
        imports.append(("decimal", "Decimal"))
    if families_used.intersection(("date", "time", "datetime")):
        imports.extend((("datetime", "date"), ("datetime", "datetime"), ("datetime", "time")))
    setup = _setup(view, rows, columns, select_names, stored, unique, select_sql, engine)
    return Contribution(
        imports=tuple(imports),
        setup_lines=tuple(setup),
        methods=tuple(methods),
        helpers=("_cbcs_line_plan",),
        needs_form=True,
    )


def _method(name: str, params: str, lines: Sequence[str]) -> Method:
    return Method(name=name, body="\n".join(lines), source_ref="rows", params=params)


def _setup(view, rows, columns, select_names, stored, unique, select_sql, engine):
    headers = ", ".join(py_string(column.header) for column in columns)
    names = ", ".join(py_string(column.name) for column in columns)
    kinds = ", ".join(py_string(column.kind) for column in columns)
    nullable = ", ".join("True" if column.nullable else "False" for column in columns)
    locked = ", ".join("True" if column.locked or column.calculated else "False" for column in columns)
    select_list = ", ".join(py_string(name) for name in select_names)
    stored_list = ", ".join(py_string(name) for name in stored)
    assign = []
    for column in columns:
        if column.calculated:
            continue
        assign.append("%s: %s" % (py_string(column.name), py_string(assignment_piece(engine, column.name))))
    lookups = []
    for column in columns:
        if column.lookup is None:
            continue
        statement = select_lookup(
            engine,
            column.lookup.table,
            column.lookup.key,
            column.lookup.show,
            column.lookup.also,
        )
        if column.lookup.also:
            also = "(%s,)" % ", ".join(py_string(name) for name in column.lookup.also)
        else:
            also = "()"
        lookups.append(
            "(%s, %s, %s, %s)"
            % (py_string(column.name), py_string(statement.text), py_string(column.lookup.show), also)
        )
    lines = [
        "class _CbcsLineDelegate(QStyledItemDelegate):",
        "    def __init__(self, ui):",
        "        super(_CbcsLineDelegate, self).__init__(ui.%s)" % view,
        "        self._ui = ui",
        "    def createEditor(self, parent, option, index):",
        "        return self._ui._cbcs_line_editor(parent, index)",
        "    def setEditorData(self, editor, index):",
        "        self._ui._cbcs_line_editor_data(editor, index)",
        "    def setModelData(self, editor, model, index):",
        "        self._ui._cbcs_line_commit(editor, model, index)",
        "_model = QStandardItemModel(self.%s)" % view,
        "_model.setHorizontalHeaderLabels((%s,))" % headers,
        "self.%s.setModel(_model)" % view,
        "self.%s.setItemDelegate(_CbcsLineDelegate(self))" % view,
        "_model.dataChanged.connect(self._cbcs_line_changed)",
        "_model.rowsInserted.connect(self._cbcs_line_changed)",
        "_model.rowsRemoved.connect(self._cbcs_line_changed)",
        "self._cbcs_line_role = int(Qt.ItemDataRole.UserRole)",
        "self._cbcs_line_key_role = self._cbcs_line_role + 1",
        "self._cbcs_line_key = %s" % py_string(rows.key),
        "self._cbcs_line_link = %s" % py_string(rows.link),
        "self._cbcs_line_position = %s" % py_string(rows.position),
        "self._cbcs_line_table = %s" % py_string(rows.table),
        "self._cbcs_line_unique = %s" % ("True" if unique else "False"),
        "self._cbcs_line_names = (%s,)" % names,
        "self._cbcs_line_headers = (%s,)" % headers,
        "self._cbcs_line_kinds = (%s,)" % kinds,
        "self._cbcs_line_nullable = (%s,)" % nullable,
        "self._cbcs_line_locked = (%s,)" % locked,
        "self._cbcs_line_stored = (%s,)" % stored_list,
        "self._cbcs_line_select_names = (%s,)" % select_list,
        "self._cbcs_line_select = %s" % py_string(select_sql.text),
        "self._cbcs_line_delete = %s" % py_string(delete_row(engine, rows.table, rows.key).text),
        "self._cbcs_line_delete_link = %s" % py_string(delete_lines_for_link(engine, rows.table, rows.link).text),
        "self._cbcs_line_position_sql = %s"
        % py_string(set_line_position(engine, rows.table, rows.position or rows.key, rows.key).text if rows.position else ""),
        "self._cbcs_line_insert = %s" % py_string(_insert_sql(engine, rows, stored)),
        "self._cbcs_line_update = %s" % py_string(update_head(engine, rows.table) + " "),
        "self._cbcs_line_where = %s" % py_string(key_clause(engine, rows.key)),
        "self._cbcs_line_assign = {%s}" % ", ".join(assign),
        "self._cbcs_line_lookups = (%s,)" % ", ".join(lookups) if lookups else "self._cbcs_line_lookups = ()",
        "self._cbcs_line_lookup = {}",
        "self._cbcs_line_also_map = {}",
        "self._cbcs_line_snapshot = ()",
        "self._cbcs_deleted_line_keys = []",
        "self._cbcs_line_guard = False",
        "self._cbcs_add_shortcut = QShortcut(QKeySequence(%s), self.%s)" % (py_string("Ctrl+Insert"), view),
        "self._cbcs_add_shortcut.activated.connect(self._cbcs_add_row)",
        "self._cbcs_delete_shortcut = QShortcut(QKeySequence(%s), self.%s)" % (py_string("Ctrl+Delete"), view),
        "self._cbcs_delete_shortcut.activated.connect(self._cbcs_delete_row)",
        "_saved_validate = getattr(self, %s, None)" % py_string("cbcs_validate"),
        "def _cbcs_validate_with_lines(_saved=_saved_validate):",
        "    if _saved is not None and _saved() is False:",
        "        return False",
        "    return self._cbcs_validate_lines()",
        "self.cbcs_validate = _cbcs_validate_with_lines",
    ]
    return lines


def _insert_sql(engine: str, rows: Rows, stored: Sequence[str]) -> str:
    columns = list(stored)
    if rows.position and rows.position not in columns:
        columns.append(rows.position)
    columns.append(rows.link)
    return insert_row(engine, rows.table, columns, rows.key).text


def _load_body(view: str) -> List[str]:
    return [
        "_cursor = _conn.cursor()",
        "self._cbcs_load_line_lookups(_conn)",
        "_cursor.execute(self._cbcs_line_select, (_key,))",
        "_fetched = _cursor.fetchall()",
        "_model = self.%s.model()" % view,
        "if _model is None:",
        "    return",
        "_model.blockSignals(True)",
        "_model.removeRows(0, _model.rowCount())",
        "_snapshot = []",
        "for _item in _fetched:",
        "    _raw = {}",
        "    for _i, _name in enumerate(self._cbcs_line_select_names):",
        "        _raw[_name] = self._cbcs_line_in(_name, _item[_i])",
        "    _snap = {self._cbcs_line_key: _raw.get(self._cbcs_line_key)}",
        "    for _name in self._cbcs_line_stored:",
        "        _snap[_name] = _raw.get(_name)",
        "    if self._cbcs_line_position:",
        "        _snap[self._cbcs_line_position] = _raw.get(self._cbcs_line_position)",
        "    _snapshot.append(_snap)",
        "    _cells = []",
        "    for _i, _name in enumerate(self._cbcs_line_names):",
        "        _kind = self._cbcs_line_kinds[_i]",
        "        _value = None if _kind == %s else _raw.get(_name)" % py_string("calc"),
        "        _text = %s if _value is None else str(_value)" % py_string(""),
        "        if _kind == %s:" % py_string("lookup"),
        "            _label = self._cbcs_line_lookup_label(_name, _value)",
        "            if _label:",
        "                _text = _label",
        "        _cell = QStandardItem(_text)",
        "        _cell.setData(_value, self._cbcs_line_role)",
        "        _cell.setData(_raw.get(self._cbcs_line_key), self._cbcs_line_key_role)",
        "        if _kind == %s or self._cbcs_line_locked[_i]:" % py_string("calc"),
        "            _cell.setEditable(False)",
        "        if _kind == %s:" % py_string("calc"),
        "            _cell.setForeground(self.%s.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text))" % view,
        "        _cells.append(_cell)",
        "    _model.appendRow(_cells)",
        "_model.blockSignals(False)",
        "self._cbcs_line_snapshot = tuple(_snapshot)",
        "self._cbcs_deleted_line_keys = []",
        "self._cbcs_recompute_lines()",
    ]


def _save_body(view: str, engine: str, rows: Rows, stored: Sequence[str]) -> List[str]:
    del view, engine, rows, stored
    return [
        "_ops = _cbcs_plan_lines(",
        "    self._cbcs_line_snapshot,",
        "    self._cbcs_line_rows(),",
        "    tuple(self._cbcs_deleted_line_keys),",
        "    self._cbcs_line_key,",
        "    self._cbcs_line_position,",
        "    self._cbcs_line_stored,",
        "    self._cbcs_line_unique,",
        ")",
        "_cursor = _conn.cursor()",
        "for _op in _ops:",
        "    _kind = _op[0]",
        "    if _kind == %s:" % py_string("delete"),
        "        _cursor.execute(self._cbcs_line_delete, (self._cbcs_line_out(self._cbcs_line_key, _op[1]),))",
        "    elif _kind == %s:" % py_string("update"),
        "        _sets = []",
        "        _params = []",
        "        for _column, _value in _op[2]:",
        "            _sets.append(self._cbcs_line_assign[_column])",
        "            _params.append(self._cbcs_line_out(_column, _value))",
        "        _params.append(self._cbcs_line_out(self._cbcs_line_key, _op[1]))",
        "        _cursor.execute(self._cbcs_line_update + %s.join(_sets) + self._cbcs_line_where, _params)" % py_string(", "),
        "    elif _kind == %s or _kind == %s:" % (py_string("park"), py_string("position")),
        "        _cursor.execute(self._cbcs_line_position_sql, (self._cbcs_line_out(self._cbcs_line_position, _op[2]), self._cbcs_line_out(self._cbcs_line_key, _op[1])))",
        "    elif _kind == %s:" % py_string("insert"),
        "        _params = []",
        "        for _column, _value in _op[1]:",
        "            _params.append(self._cbcs_line_out(_column, _value))",
        "        _params.append(self._cbcs_line_out(self._cbcs_line_link, _parent))",
        "        _cursor.execute(self._cbcs_line_insert, _params)",
    ]


def _dirty_body() -> List[str]:
    return [
        "if self._cbcs_deleted_line_keys:",
        "    return True",
        "return _cbcs_lines_differ(self._cbcs_line_snapshot, self._cbcs_line_rows(), self._cbcs_line_key, self._cbcs_line_stored)",
    ]


def _clear_body(view: str) -> List[str]:
    return [
        "self._cbcs_deleted_line_keys = []",
        "_model = self.%s.model()" % view,
        "if _model is not None:",
        "    _model.blockSignals(True)",
        "    _model.removeRows(0, _model.rowCount())",
        "    _model.blockSignals(False)",
        "self._cbcs_line_snapshot = ()",
    ]


def _delete_link_body() -> List[str]:
    return [
        "_cursor = _conn.cursor()",
        "_cursor.execute(self._cbcs_line_delete_link, (self._cbcs_line_out(self._cbcs_line_link, _key),))",
    ]


def _validate_body(view: str) -> List[str]:
    return [
        "_model = self.%s.model()" % view,
        "if _model is None:",
        "    return True",
        "for _r in range(_model.rowCount()):",
        "    for _c, _name in enumerate(self._cbcs_line_names):",
        "        if self._cbcs_line_kinds[_c] == %s or self._cbcs_line_nullable[_c]:" % py_string("calc"),
        "            continue",
        "        _cell = _model.item(_r, _c)",
        "        _value = None if _cell is None else _cell.data(self._cbcs_line_role)",
        "        if _value is None or _value == %s:" % py_string(""),
        "            _message = %s %% (_r + 1, self._cbcs_line_headers[_c])" % py_string("Line %d: %s is required"),
        "            if _cell is not None:",
        "                _cell.setToolTip(_message)",
        "                _cell.setBackground(QBrush(QColor(192, 57, 43)))",
        "                _cell.setForeground(QBrush(QColor(%s)))" % py_string("white"),
        "            self.%s.setCurrentIndex(_model.index(_r, _c))" % view,
        "            self.%s.setFocus()" % view,
        "            return False",
        "        if _cell is not None and _cell.toolTip():",
        "            _cell.setToolTip(%s)" % py_string(""),
        "            _cell.setBackground(QBrush())",
        "            _cell.setForeground(QBrush())",
        "return True",
    ]


def _add_body(view: str, columns: Sequence[_Col]) -> List[str]:
    names = [column.name for column in columns if not column.calculated]
    lines = [
        "_model = self.%s.model()" % view,
        "if _model is None:",
        "    return",
        "_row = {}",
    ]
    for column in columns:
        if column.calculated:
            continue
        expr = _row_expr(column.default, names) if column.default else "None"
        lines.append("_row[%s] = %s" % (py_string(column.name), expr))
    lines.extend(
        [
            "_cells = []",
            "for _i, _name in enumerate(self._cbcs_line_names):",
            "    _kind = self._cbcs_line_kinds[_i]",
            "    _value = None if _kind == %s else _row.get(_name)" % py_string("calc"),
            "    _text = %s if _value is None else str(_value)" % py_string(""),
            "    if _kind == %s and _value is not None:" % py_string("lookup"),
            "        _label = self._cbcs_line_lookup_label(_name, _value)",
            "        if _label:",
            "            _text = _label",
            "    _cell = QStandardItem(_text)",
            "    _cell.setData(_value, self._cbcs_line_role)",
            "    _cell.setData(None, self._cbcs_line_key_role)",
            "    if _kind == %s or self._cbcs_line_locked[_i]:" % py_string("calc"),
            "        _cell.setEditable(False)",
            "    if _kind == %s:" % py_string("calc"),
            "        _cell.setForeground(self.%s.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text))" % view,
            "    _cells.append(_cell)",
            "_model.appendRow(_cells)",
            "_index = _model.index(_model.rowCount() - 1, 0)",
            "self.%s.setCurrentIndex(_index)" % view,
            "self.%s.setFocus()" % view,
            "self._cbcs_recompute_lines()",
        ]
    )
    return lines


def _delete_row_body(view: str) -> List[str]:
    return [
        "_model = self.%s.model()" % view,
        "if _model is None:",
        "    return",
        "_index = self.%s.currentIndex()" % view,
        "_row = _index.row() if _index.isValid() else _model.rowCount() - 1",
        "if _row < 0:",
        "    return",
        "_box = QMessageBox(self._form)",
        "_box.setIcon(QMessageBox.Icon.Question)",
        "_box.setWindowTitle(%s)" % py_string("Delete line"),
        "_box.setText(%s %% (_row + 1))" % py_string("Delete line %d?"),
        "_delete = _box.addButton(%s, QMessageBox.ButtonRole.AcceptRole)" % py_string("Delete"),
        "_box.addButton(%s, QMessageBox.ButtonRole.RejectRole)" % py_string("Cancel"),
        "_box.exec()",
        "if _box.clickedButton() is not _delete:",
        "    return",
        "_cell = _model.item(_row, 0)",
        "_key = None if _cell is None else _cell.data(self._cbcs_line_key_role)",
        "if _key is not None:",
        "    self._cbcs_deleted_line_keys.append(_key)",
        "_model.removeRow(_row)",
    ]


def _read_body(view: str) -> List[str]:
    return [
        "_found = []",
        "for _row in self._cbcs_line_rows():",
        "    _copy = dict(_row)",
        "    _found.append(_copy)",
        "_model = self.%s.model()" % view,
        "if _model is None:",
        "    return _found",
        "for _r, _copy in enumerate(_found):",
        "    for _c, _name in enumerate(self._cbcs_line_names):",
        "        if self._cbcs_line_kinds[_c] != %s:" % py_string("calc"),
        "            continue",
        "        _cell = _model.item(_r, _c)",
        "        _copy[_name] = None if _cell is None else _cell.data(self._cbcs_line_role)",
        "return _found",
    ]


def _grid_body(view: str) -> List[str]:
    return [
        "_names = getattr(self, %s, ())" % py_string("_cbcs_line_names"),
        "if _name not in _names:",
        "    return []",
        "_index = _names.index(_name)",
        "_model = self.%s.model()" % view,
        "if _model is None:",
        "    return []",
        "_values = []",
        "for _r in range(_model.rowCount()):",
        "    _cell = _model.item(_r, _index)",
        "    _values.append(None if _cell is None else _cell.data(self._cbcs_line_role))",
        "return _values",
    ]


def _rows_body(view: str) -> List[str]:
    return [
        "_found = []",
        "_model = self.%s.model()" % view,
        "_count = 0 if _model is None else _model.rowCount()",
        "for _r in range(_count):",
        "    _dict = self._cbcs_line_dict(_r)",
        "    _row = {self._cbcs_line_key: _dict.get(self._cbcs_line_key)}",
        "    for _name in self._cbcs_line_stored:",
        "        _row[_name] = _dict.get(_name)",
        "    _found.append(_row)",
        "return tuple(_found)",
    ]


def _dict_body(view: str) -> List[str]:
    return [
        "_model = self.%s.model()" % view,
        "_row = {}",
        "if _model is None:",
        "    return _row",
        "for _i, _name in enumerate(self._cbcs_line_names):",
        "    if self._cbcs_line_kinds[_i] == %s:" % py_string("calc"),
        "        continue",
        "    _cell = _model.item(_r, _i)",
        "    _row[_name] = None if _cell is None else _cell.data(self._cbcs_line_role)",
        "_cell = _model.item(_r, 0)",
        "_row[self._cbcs_line_key] = None if _cell is None else _cell.data(self._cbcs_line_key_role)",
        "return _row",
    ]


def _convert_body(families, nulls, engine: str, outbound: bool) -> List[str]:
    lines = []
    first = True
    for name, family in families.items():
        word = "if" if first else "elif"
        first = False
        lines.append("%s _column == %s:" % (word, py_string(name)))
        lines.extend("    " + line for line in _family_lines(family, nulls.get(name, True), engine, outbound))
    lines.append("return _value")
    return lines


def _family_lines(family: str, nullable: bool, engine: str, outbound: bool) -> List[str]:
    if not outbound:
        lines = ["if _value is None:", "    return None"]
        if family == "int":
            lines.append("return int(_value)")
        elif family == "decimal":
            lines.extend(["if isinstance(_value, Decimal):", "    return _value", "return Decimal(str(_value))"])
        elif family == "bool":
            lines.extend(
                [
                    "if isinstance(_value, str):",
                    "    return _value not in (%s, %s, %s, %s)" % (py_string(""), py_string("0"), py_string("false"), py_string("False")),
                    "return True if _value else False",
                ]
            )
        elif family == "date":
            lines.extend(
                [
                    "if isinstance(_value, datetime):",
                    "    return _value.date()",
                    "if isinstance(_value, date):",
                    "    return _value",
                    "return date.fromisoformat(str(_value)[:10])",
                ]
            )
        elif family == "text":
            lines.extend(
                [
                    "if isinstance(_value, bytes):",
                    "    return _value.decode(%s)" % py_string("utf-8"),
                    "return str(_value)",
                ]
            )
        else:
            lines.append("return _value")
        return lines
    if family == "text":
        lines = [
            "if isinstance(_value, bytes):",
            "    _value = _value.decode(%s)" % py_string("utf-8"),
            "if _value is None:",
            "    return None" if nullable else "    return %s" % py_string(""),
        ]
        if nullable:
            lines.extend(["if _value == %s:" % py_string(""), "    return None"])
        lines.append("return str(_value)")
        return lines
    if family == "int":
        return ["if _value is None or _value == %s:" % py_string(""), "    return None", "return int(_value)"]
    if family == "decimal":
        lines = [
            "if _value is None or _value == %s:" % py_string(""),
            "    return None",
            "if not isinstance(_value, Decimal):",
            "    _value = Decimal(str(_value))",
            "return _value" if engine == "postgres" else "return str(_value)",
        ]
        return lines
    if family == "bool":
        if engine == "postgres":
            return ["if _value is None:", "    return None", "return True if _value else False"]
        return ["if _value is None:", "    return None", "return 1 if _value else 0"]
    if family == "date":
        lines = [
            "if _value is None or _value == %s:" % py_string(""),
            "    return None",
            "if isinstance(_value, datetime):",
            "    _text = _value.date().isoformat()",
            "elif isinstance(_value, date):",
            "    _text = _value.isoformat()",
            "else:",
            "    _text = str(_value)[:10]",
            "return date.fromisoformat(_text[:10])" if engine == "postgres" else "return _text",
        ]
        return lines
    return ["return _value"]


def _recompute_body(view: str, columns: Sequence[_Col]) -> List[str]:
    names = [column.name for column in columns]
    lines = [
        "_model = self.%s.model()" % view,
        "if _model is None:",
        "    return",
        "_held = self._cbcs_line_guard",
        "self._cbcs_line_guard = True",
        "try:",
        "    for _r in range(_model.rowCount()):",
        "        _row = self._cbcs_line_dict(_r)",
    ]
    emitted = False
    for index, column in enumerate(columns):
        if not column.calculated:
            continue
        emitted = True
        expr = _row_expr(column.formula, names)
        lines.extend(
            [
                "        _value = %s" % expr,
                "        _row[%s] = _value" % py_string(column.name),
                "        _cell = _model.item(_r, %d)" % index,
                "        if _cell is not None:",
                "            _cell.setData(_value, self._cbcs_line_role)",
                "            _cell.setText(%s if _value is None else str(_value))" % py_string(""),
                "            _cell.setEditable(False)",
                "            _cell.setForeground(self.%s.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text))" % view,
            ]
        )
    if not emitted:
        lines.append("        pass")
    lines.extend(["finally:", "    self._cbcs_line_guard = _held"])
    return lines


def _changed_body() -> List[str]:
    return [
        "if self._cbcs_line_guard:",
        "    return",
        "self._cbcs_recompute_lines()",
        "if getattr(self, %s, False):" % py_string("_cbcs_refreshing"),
        "    return",
        "_refresh = getattr(self, %s, None)" % py_string("cbcs_refresh"),
        "if _refresh is not None:",
        "    _refresh()",
    ]


def _editor_body() -> List[str]:
    return [
        "_kind = self._cbcs_line_kinds[_index.column()]",
        "_name = self._cbcs_line_names[_index.column()]",
        "if _kind == %s:" % py_string("lookup"),
        "    _box = QComboBox(_parent)",
        "    _box.addItem(%s, None)" % py_string("(choose)"),
        "    for _key, _label in self._cbcs_line_lookup.get(_name, ()):",
        "        _box.addItem(str(_label), _key)",
        "    return _box",
        "if _kind == %s:" % py_string("int"),
        "    _spin = QSpinBox(_parent)",
        "    _spin.setRange(-2147483647, 2147483647)",
        "    return _spin",
        "if _kind == %s:" % py_string("decimal"),
        "    _spin = QDoubleSpinBox(_parent)",
        "    _spin.setDecimals(2)",
        "    _spin.setRange(-1000000000000, 1000000000000)",
        "    return _spin",
        "return QLineEdit(_parent)",
    ]


def _editor_data_body() -> List[str]:
    return [
        "_value = _index.data(self._cbcs_line_role)",
        "_kind = self._cbcs_line_kinds[_index.column()]",
        "if _kind == %s:" % py_string("int"),
        "    _editor.setValue(0 if _value is None else int(_value))",
        "    return",
        "if _kind == %s:" % py_string("decimal"),
        "    _editor.setValue(0 if _value is None else float(_value))",
        "    return",
        "if _kind == %s:" % py_string("lookup"),
        "    _found = _editor.findData(_value)",
        "    _editor.setCurrentIndex(0 if _found < 0 else _found)",
        "    return",
        "_editor.setText(%s if _value is None else str(_value))" % py_string(""),
    ]


def _commit_body() -> List[str]:
    return [
        "_kind = self._cbcs_line_kinds[_index.column()]",
        "_nullable = self._cbcs_line_nullable[_index.column()]",
        "if _kind == %s:" % py_string("int"),
        "    _value = int(_editor.value())",
        "    _text = str(_value)",
        "elif _kind == %s:" % py_string("decimal"),
        "    _value = Decimal(str(_editor.value()))",
        "    _text = str(_value)",
        "elif _kind == %s:" % py_string("lookup"),
        "    _value = _editor.currentData()",
        "    _text = %s if _value is None else _editor.currentText()" % py_string(""),
        "else:",
        "    _text = _editor.text()",
        "    _value = None if _text == %s and _nullable else _text" % py_string(""),
        "_model.blockSignals(True)",
        "_cell = _model.item(_index.row(), _index.column())",
        "if _cell is not None:",
        "    _cell.setData(_value, self._cbcs_line_role)",
        "    _cell.setText(_text)",
        "_model.blockSignals(False)",
        "self._cbcs_line_changed()",
    ]


def _also_body() -> List[str]:
    return ["return self._cbcs_line_also_map.get((_column, _key, _name))"]


def _label_body() -> List[str]:
    return [
        "for _id, _label in self._cbcs_line_lookup.get(_name, ()):",
        "    if _id == _key:",
        "        return str(_label)",
        "return %s" % py_string(""),
    ]


def _lookup_body(columns: Sequence[_Col], engine: str) -> List[str]:
    del engine
    return [
        "self._cbcs_line_lookup = {}",
        "self._cbcs_line_also_map = {}",
        "_cursor = _conn.cursor()",
        "for _name, _sql, _show, _also in self._cbcs_line_lookups:",
        "    _cursor.execute(_sql)",
        "    _pairs = []",
        "    for _item in _cursor.fetchall():",
        "        _key = _item[0]",
        "        _label = _item[1] if len(_item) > 1 else _item[0]",
        "        _pairs.append((_key, _label))",
        "        for _offset, _also_name in enumerate(_also):",
        "            _raw = _item[_offset + 2] if len(_item) > _offset + 2 else None",
        "            self._cbcs_line_also_map[(_name, _key, _also_name)] = _raw",
        "    self._cbcs_line_lookup[_name] = tuple(_pairs)",
    ]


def _record(doc: UiDocument) -> Optional[RecordSource]:
    root = getattr(doc, "root", None)
    prop = getattr(root, "prop", None)
    if not callable(prop):
        return None
    entry = prop("cbcsData")
    if entry is None or not isinstance(getattr(entry, "value", None), StringValue):
        return None
    found = read_data(entry.value.text).value
    if isinstance(found, RecordSource):
        return found
    return None


def _grids(doc: UiDocument, ctx: CodegenContext) -> List[Tuple[str, Rows]]:
    found = []
    for node in _widgets(doc):
        name = node.object_name or ""
        if name not in ctx.attribute_names or not compat.is_name(name):
            continue
        entry = node.prop("cbcsRows")
        if entry is None or not isinstance(entry.value, StringValue) or not entry.value.text.strip():
            continue
        rows, error = read_rows(entry.value.text)
        if error is not None or rows is None:
            continue
        found.append((name, rows))
    return found


def _names_ok(rows: Rows, view: str) -> bool:
    del view
    names = [rows.table, rows.link, rows.key]
    if rows.order:
        names.append(rows.order)
    if rows.position:
        names.append(rows.position)
    for column in rows.columns:
        if isinstance(column, DataColumn):
            names.append(column.column)
        elif isinstance(column, CalcColumn):
            names.append(column.name)
    return all(is_identifier(name) for name in names if name)


def _columns(doc: UiDocument, source: RecordSource, rows: Rows, engine: str) -> Tuple[_Col, ...]:
    table = _line_table(doc, source.connection, rows.table)
    found = []
    for column in rows.columns:
        if isinstance(column, CalcColumn):
            found.append(
                _Col(
                    column.name,
                    column.header or column.name,
                    "calc",
                    "decimal" if column.kind == "money" else "text",
                    True,
                    True,
                    True,
                    column.formula,
                    "",
                    None,
                )
            )
            continue
        if not isinstance(column, DataColumn):
            continue
        schema_column = _schema_column(table, column.column)
        declared = schema_column.type if schema_column is not None else ""
        nullable = True if schema_column is None else schema_column.nullable
        kind = describe(
            declared,
            engine=engine,
            column_name=column.column,
            references_table=schema_column.references.table if schema_column is not None and schema_column.references else "",
            nullable=nullable,
        )
        family = kind.direction or "text"
        editor = _editor_kind(column, family)
        found.append(
            _Col(
                column.column,
                column.header or column.column,
                editor,
                family,
                nullable,
                False,
                column.read_only,
                "",
                column.default,
                column.lookup,
            )
        )
    return tuple(found)


def _editor_kind(column: DataColumn, family: str) -> str:
    if column.lookup is not None:
        return "lookup"
    if column.kind == "whole" or family == "int":
        return "int"
    if column.kind in ("money", "decimal", "number") or family == "decimal":
        return "decimal"
    return "text"


def _family_of(name: str, columns: Sequence[_Col], rows: Rows, table: object, engine: str) -> str:
    for column in columns:
        if column.name == name:
            return column.family
    schema_column = _schema_column(table, name)
    if schema_column is not None:
        kind = describe(schema_column.type, engine=engine, column_name=name, nullable=schema_column.nullable)
        return kind.direction or "text"
    if name in (rows.key, rows.position, rows.link):
        return "int"
    return "text"


def _nullable_of(name: str, columns: Sequence[_Col], rows: Rows) -> bool:
    for column in columns:
        if column.name == name:
            return column.nullable
    if name == rows.key:
        return False
    return True


def _line_table(doc: UiDocument, connection: str, table: str):
    schema = schema_for(doc, connection)
    if schema is None:
        return None
    for item in schema.tables:
        if item.name == table:
            return item
    return None


def _schema_column(table, name: str):
    if table is None:
        return None
    for column in table.columns:
        if column.name == name:
            return column
    return None


def _row_expr(text: str, names: Sequence[str]) -> str:
    stripped = text.strip()
    if not stripped:
        return "None"
    try:
        parsed = parse_text(stripped, FormulaEnv.for_test())
        if parsed.tree is None:
            raise ValueError(stripped)
        return _walk(parsed.tree, set(names))
    except Exception:
        return "None"


def _walk(node: object, names: set) -> str:
    if isinstance(node, Lit):
        return _lit(node.value)
    if isinstance(node, Ref):
        if node.name not in names:
            raise ValueError(node.name)
        return "_row.get(%s)" % py_string(node.name)
    if isinstance(node, Attr) and isinstance(node.base, Ref) and node.base.name in names:
        return "self._cbcs_line_also(%s, _row.get(%s), %s)" % (
            py_string(node.base.name),
            py_string(node.base.name),
            py_string(node.name),
        )
    if isinstance(node, Unary) and node.op == "-":
        inner = _walk(node.x, names)
        return "(None if (%s) is None else -(%s))" % (inner, inner)
    if isinstance(node, Bin) and node.op in ("*", "+", "-", "/"):
        left = _walk(node.a, names)
        right = _walk(node.b, names)
        return "(None if (%s) is None or (%s) is None else (%s) %s (%s))" % (left, right, left, node.op, right)
    raise ValueError("column formula")


def _lit(value: object) -> str:
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return py_string(value)
    return "None"


def _widgets(doc: UiDocument):
    try:
        return tuple(doc.iter_widgets())
    except Exception:
        return ()


EXPANDER = RowsExpander()
