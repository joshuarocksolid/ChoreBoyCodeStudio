"""Lines grid (CONTRACTS.md section 19.1, order 420).

The model is the edit surface. ``_cbcs_plan_lines`` decides the write. Record
load, save, and dirty already call the method names this module fills in.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import List, Mapping, Optional, Sequence, Tuple

from app.features.form_builder.engine.codegen.expanders.record import _bind_clock, _engine, _from_family, register_open_hook
from app.features.form_builder.engine.codegen.literals import py_string
from app.features.form_builder.engine.codegen.logic_hooks import CodegenContext, Contribution, Method
from app.features.form_builder.engine.codegen.lookup_plan import also_indexes, select_columns
from app.features.form_builder.engine.data.lines import compile_line_formula, link_position_unique, type_for_kind
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
    insert_line_at_next_position,
    insert_row,
    key_clause,
    name_usable,
    select_lines,
    select_lookup,
    set_line_position,
    update_head,
)
from app.features.form_builder.engine.data.types import describe, stores_whole_integer
from app.features.form_builder.engine.logic import compat
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
    scale: int = -1


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
            source.connection,
            link_position_unique(keys, rows.link, rows.position),
            table,
            _row_attrs(doc, source.connection, columns, engine),
            _carried_families(doc, source.connection, columns, engine),
        )


def _contribution(
    view: str,
    rows: Rows,
    columns: Sequence[_Col],
    engine: str,
    connection: str,
    unique: bool,
    table: object,
    attrs: Optional[Mapping[str, Mapping[str, object]]] = None,
    carried: Sequence[Tuple[str, str, str]] = (),
) -> Contribution:
    hidden = {rows.key, rows.link, rows.position}
    stored = tuple(column.name for column in columns if not column.calculated and column.name not in hidden)
    stamp = _append_position(rows, table, engine)
    select_names = (rows.key,) + stored
    if rows.position and rows.position not in select_names:
        select_names = select_names + (rows.position,)
    families = {name: _family_of(name, columns, rows, table, engine) for name in select_names}
    nulls = {name: _nullable_of(name, columns, rows) for name in select_names}
    select_sql = select_lines(engine, rows.table, select_names, rows.link, rows.order or rows.position, rows.key)
    methods = [
        _method("_cbcs_load_lines", "_conn, _key", _load_body(view)),
        _method("_cbcs_save_lines", "_conn, _parent", _save_body(view, engine, rows, stored, stamp)),
        _method("_cbcs_lines_dirty", "", _dirty_body()),
        _method("_cbcs_clear_lines", "", _clear_body(view)),
        _method("_cbcs_delete_lines", "_conn, _key", _delete_link_body()),
        _method("_cbcs_validate_lines", "", _validate_body(view)),
        _method("_cbcs_add_row", "", _add_body(view, columns, attrs or {})),
        _method("_cbcs_delete_row", "", _delete_row_body(view)),
        _method("cbcs_read_lines", "", _read_body(view)),
        _method("_cbcs_grid_column", "_name", _grid_body(view)),
        _method("_cbcs_commit_line_editor", "", _commit_editor_body(view)),
        _method("_cbcs_line_rows", "", _rows_body(view)),
        _method("_cbcs_line_dict", "_r", _dict_body(view)),
        _method("_cbcs_line_out", "_column, _value", _convert_body(families, nulls, engine, True)),
        _method("_cbcs_line_in", "_column, _value", _convert_body(families, nulls, engine, False)),
        _method("_cbcs_recompute_lines", "", _recompute_body(view, columns, attrs or {})),
        _method("_cbcs_line_changed", "*_args", _changed_body()),
        _method("_cbcs_line_editor", "_parent, _index", _editor_body()),
        _method("_cbcs_line_editor_data", "_editor, _index", _editor_data_body()),
        _method("_cbcs_line_commit", "_editor, _model, _index", _commit_body()),
        _method("_cbcs_line_show", "_column, _value", _show_body()),
        _method("_cbcs_line_defaults", "_row_index, _before", _defaults_body(view, columns, attrs or {})),
        _method("_cbcs_line_also", "_column, _key, _name", _also_body()),
        _method("_cbcs_line_lookup_label", "_name, _key", _label_body()),
        _method("_cbcs_load_line_lookups", "_conn", _lookup_body(columns, engine)),
        _method("_cbcs_line_from", "_table, _column, _value", _line_from_body(carried)),
        _method("_cbcs_reload_line_lookups", "", _reload_body(connection)),
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
        ("PySide6.QtWidgets", "QCheckBox"),
        ("PySide6.QtWidgets", "QHeaderView"),
        ("PySide6.QtWidgets", "QComboBox"),
        ("PySide6.QtWidgets", "QDateEdit"),
        ("PySide6.QtWidgets", "QDateTimeEdit"),
        ("PySide6.QtWidgets", "QDoubleSpinBox"),
        ("PySide6.QtWidgets", "QLineEdit"),
        ("PySide6.QtWidgets", "QMessageBox"),
        ("PySide6.QtWidgets", "QSpinBox"),
        ("PySide6.QtWidgets", "QStyledItemDelegate"),
        ("PySide6.QtWidgets", "QTimeEdit"),
        ("PySide6.QtCore", "QDate"),
        ("PySide6.QtCore", "QDateTime"),
        ("PySide6.QtCore", "QTime"),
    ]
    families_used = set(families.values())
    if "decimal" in families_used or any(column.scale >= 0 or column.kind == "decimal" for column in columns):
        imports.append(("decimal", "Decimal"))
    if families_used.intersection(("date", "time", "datetime")) or any(column.kind in ("date", "time", "datetime") for column in columns):
        imports.extend((("datetime", "date"), ("datetime", "datetime"), ("datetime", "time")))
    if any(column.kind == "time" and column.nullable for column in columns):
        imports.extend(
            (
                ("PySide6.QtCore", "QObject"),
                ("PySide6.QtCore", "QEvent"),
                ("PySide6.QtWidgets", "QMenu"),
            )
        )
    helpers = ["_cbcs_line_plan"]
    for _column, compiled in _formulas(columns, attrs or {}):
        for helper in compiled[1]:
            if helper not in helpers:
                helpers.append(helper)
        if compiled[4] and "_cbcs_is_blank" not in helpers:
            helpers.append("_cbcs_is_blank")
        for imported in compiled[2]:
            if imported not in imports:
                imports.append(imported)
    setup = _setup(view, rows, columns, select_names, stored, unique, select_sql, engine, stamp)
    return Contribution(
        imports=tuple(imports),
        setup_lines=tuple(setup),
        methods=tuple(methods),
        helpers=tuple(helpers),
        needs_form=True,
    )


def _method(name: str, params: str, lines: Sequence[str]) -> Method:
    return Method(name=name, body="\n".join(lines), source_ref="rows", params=params)


def _setup(view, rows, columns, select_names, stored, unique, select_sql, engine, stamp=""):
    headers = ", ".join(py_string(column.header) for column in columns)
    names = ", ".join(py_string(column.name) for column in columns)
    kinds = ", ".join(py_string(column.kind) for column in columns)
    nullable = ", ".join("True" if column.nullable else "False" for column in columns)
    locked = ", ".join("True" if column.locked or column.calculated else "False" for column in columns)
    scales = ", ".join(str(column.scale) for column in columns)
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
            column.lookup.order,
        )
        selected = select_columns(column.lookup.key, column.lookup.show, column.lookup.also)
        show_at = selected.index(column.lookup.show)
        indexes = also_indexes(column.lookup.also, selected)
        if indexes:
            also = "(%s,)" % ", ".join("(%s, %d)" % (py_string(name), index) for name, index in indexes)
        else:
            also = "()"
        lookups.append(
            "(%s, %s, %s, %d, %s)"
            % (
                py_string(column.name),
                py_string(statement.text),
                py_string(column.lookup.table),
                show_at,
                also,
            )
        )
    stretch_at = _stretch_index(columns)
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
        "    def initStyleOption(self, option, index):",
        "        super(_CbcsLineDelegate, self).initStyleOption(option, index)",
        "        if self._ui._cbcs_line_kinds[index.column()] == %s:" % py_string("calc"),
        "            _color = option.palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.PlaceholderText)",
        "            option.palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Text, _color)",
        "            option.palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Text, _color)",
        "_model = QStandardItemModel(self.%s)" % view,
        "_model.setHorizontalHeaderLabels((%s,))" % headers,
        "self.%s.setModel(_model)" % view,
        "self.%s.setItemDelegate(_CbcsLineDelegate(self))" % view,
        "self.%s.horizontalHeader().setStretchLastSection(False)" % view,
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
        "_header = self.%s.horizontalHeader()" % view,
        "_resize = getattr(QHeaderView, 'ResizeMode', QHeaderView)",
        "_stretch = getattr(_resize, 'Stretch')",
        "_interactive = getattr(_resize, 'Interactive')",
        "_header.setSectionResizeMode(%d, _stretch)" % stretch_at,
        "for _i in range(len(self._cbcs_line_names)):",
        "    if _i != %d:" % stretch_at,
        "        self.%s.resizeColumnToContents(_i)" % view,
        "        _header.setSectionResizeMode(_i, _interactive)",
        "self._cbcs_line_headers = (%s,)" % headers,
        "self._cbcs_line_kinds = (%s,)" % kinds,
        "self._cbcs_line_nullable = (%s,)" % nullable,
        "self._cbcs_line_locked = (%s,)" % locked,
        "self._cbcs_line_scales = (%s,)" % scales,
        "for _i, _scale in enumerate(self._cbcs_line_scales):",
        "    if _scale >= 0:",
        "        _model.setHeaderData(_i, Qt.Orientation.Horizontal, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, Qt.ItemDataRole.TextAlignmentRole)",
        "self._cbcs_line_stored = (%s,)" % stored_list,
        "self._cbcs_line_select_names = (%s,)" % select_list,
        "self._cbcs_line_select = %s" % py_string(select_sql.text),
        "self._cbcs_line_delete = %s" % py_string(delete_row(engine, rows.table, rows.key).text),
        "self._cbcs_line_delete_link = %s" % py_string(delete_lines_for_link(engine, rows.table, rows.link).text),
        "self._cbcs_line_position_sql = %s"
        % py_string(set_line_position(engine, rows.table, rows.position or rows.key, rows.key).text if rows.position else ""),
        "self._cbcs_line_insert = %s" % py_string(_insert_sql(engine, rows, stored, stamp)),
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


def _append_position(rows: Rows, table: object, engine: str) -> str:
    """An integer position column that is not renumbered. Empty when there is none.

    Nullable and NOT NULL share this path, so a new line gets
    ``COALESCE(MAX(position), 0) + 1`` instead of NULL. A text column with
    the same name stays an ordinary grid column.
    """

    if rows.position or table is None:
        return ""
    shown = set()
    for column in rows.columns:
        if isinstance(column, DataColumn):
            shown.add(column.column)
        elif isinstance(column, CalcColumn):
            shown.add(column.name)
    by_name = {column.name: column for column in getattr(table, "columns", ()) or ()}
    for candidate in ("line_no", "position", "sort"):
        column = by_name.get(candidate)
        if column is None or candidate in shown or not name_usable(candidate):
            continue
        declared = str(getattr(column, "type", "") or "")
        if not stores_whole_integer(declared, engine):
            continue
        return candidate
    return ""


def _insert_sql(engine: str, rows: Rows, stored: Sequence[str], stamp: str = "") -> str:
    if stamp:
        return insert_line_at_next_position(engine, rows.table, stored, rows.key, rows.link, stamp).text
    columns = list(stored)
    if rows.position and rows.position not in columns:
        columns.append(rows.position)
    columns.append(rows.link)
    return insert_row(engine, rows.table, columns, rows.key).text


def _load_body(view: str) -> List[str]:
    return [
        "_cursor = _conn.cursor()",
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
        "        _text = self._cbcs_line_show(_i, _value)",
        "        if _kind == %s:" % py_string("lookup"),
        "            _label = self._cbcs_line_lookup_label(_name, _value)",
        "            if _label:",
        "                _text = _label",
        "        _cell = QStandardItem(_text)",
        "        _cell.setData(_value, self._cbcs_line_role)",
        "        _cell.setData(_raw.get(self._cbcs_line_key), self._cbcs_line_key_role)",
        "        if _kind == %s or self._cbcs_line_locked[_i]:" % py_string("calc"),
        "            _cell.setEditable(False)",
        "        if self._cbcs_line_scales[_i] >= 0:",
        "            _cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)",
        "        _cells.append(_cell)",
        "    _model.appendRow(_cells)",
        "_model.blockSignals(False)",
        "self._cbcs_line_snapshot = tuple(_snapshot)",
        "self._cbcs_deleted_line_keys = []",
        "self._cbcs_recompute_lines()",
    ]


def _save_body(view: str, engine: str, rows: Rows, stored: Sequence[str], stamp: str = "") -> List[str]:
    del view, engine, rows, stored
    insert = [
        "    elif _kind == %s:" % py_string("insert"),
        "        _params = []",
        "        for _column, _value in _op[1]:",
        "            _params.append(self._cbcs_line_out(_column, _value))",
    ]
    if stamp:
        insert.append("        _params.append(self._cbcs_line_out(self._cbcs_line_link, _parent))")
    insert.extend(
        [
            "        _params.append(self._cbcs_line_out(self._cbcs_line_link, _parent))",
            "        _cursor.execute(self._cbcs_line_insert, _params)",
        ]
    )
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
    ] + insert


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


def _commit_editor_body(view: str) -> List[str]:
    return [
        "_view = self.%s" % view,
        "_index = _view.currentIndex()",
        "if _index.isValid():",
        "    _editor = _view.indexWidget(_index)",
        "    if _editor is not None:",
        "        _view.commitData(_editor)",
    ]


def _validate_body(view: str) -> List[str]:
    return [
        "self._cbcs_commit_line_editor()",
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


def _add_body(view: str, columns: Sequence[_Col], attrs: Optional[Mapping[str, Mapping[str, object]]] = None) -> List[str]:
    lines = [
        "_model = self.%s.model()" % view,
        "if _model is None:",
        "    return",
        "_row = {}",
    ]
    for column in columns:
        if column.calculated:
            continue
        expr = "None"
        if column.default:
            compiled = _compiled(column.default, columns, _type_kind(column), attrs)
            expr = compiled[0] or "None"
        lines.append("_row[%s] = %s" % (py_string(column.name), expr))
    lines.extend(
        [
            "_cells = []",
            "for _i, _name in enumerate(self._cbcs_line_names):",
            "    _kind = self._cbcs_line_kinds[_i]",
            "    _value = None if _kind == %s else _row.get(_name)" % py_string("calc"),
            "    _text = self._cbcs_line_show(_i, _value)",
            "    if _kind == %s and _value is not None:" % py_string("lookup"),
            "        _label = self._cbcs_line_lookup_label(_name, _value)",
            "        if _label:",
            "            _text = _label",
            "    _cell = QStandardItem(_text)",
            "    _cell.setData(_value, self._cbcs_line_role)",
            "    _cell.setData(None, self._cbcs_line_key_role)",
            "    if _kind == %s or self._cbcs_line_locked[_i]:" % py_string("calc"),
            "        _cell.setEditable(False)",
            "    if self._cbcs_line_scales[_i] >= 0:",
            "        _cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)",
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
        "self._cbcs_commit_line_editor()",
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
        lines.extend("    " + line for line in _family_lines(family, nulls.get(name, True), engine, outbound, name))
    lines.append("return _value")
    return lines


def _family_lines(family: str, nullable: bool, engine: str, outbound: bool, column: str = "") -> List[str]:
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
                    "if _value == %s:" % py_string(""),
                    "    return None",
                    "if isinstance(_value, datetime):",
                    "    return _value.date()",
                    "if isinstance(_value, date):",
                    "    return _value",
                    "try:",
                    "    return date.fromisoformat(str(_value)[:10])",
                    "except ValueError:",
                    "    _note = getattr(self, %s, None)" % py_string("_cbcs_note_unparsed"),
                    "    if _note is not None:",
                    "        _note(_column, %s, _value)" % py_string("date"),
                    "    return None",
                ]
            )
        elif family in ("time", "datetime"):
            return _from_family(family, column)
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
    if family == "time":
        return _bind_clock(engine, "time")
    if family == "datetime":
        return _bind_clock(engine, "datetime")
    return ["return _value"]


def _recompute_body(view: str, columns: Sequence[_Col], attrs: Optional[Mapping[str, Mapping[str, object]]] = None) -> List[str]:
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
        compiled = _compiled(column.formula, columns, _type_kind(column), attrs)
        expr = compiled[0] or "None"
        lines.extend(
            [
                "        try:",
                "            _value = %s" % expr,
                "            _tip = %s" % py_string(""),
            ]
        )
        for denom in compiled[4]:
            lines.extend(
                [
                    "            if not _cbcs_is_blank(%s) and Decimal(%s) == 0:" % (denom, denom),
                    "                _value = None",
                    "                _tip = %s" % py_string("Can't divide by zero"),
                ]
            )
        lines.extend(
            [
                "        except Exception as _error:",
                "            _value = None",
                "            _tip = str(_error)",
                "            if %s in _tip.lower():" % py_string("zero"),
                "                _tip = %s" % py_string("Can't divide by zero"),
            ]
        )
        lines.extend(
            [
                "        _row[%s] = _value" % py_string(column.name),
                "        _cell = _model.item(_r, %d)" % index,
                "        if _cell is not None:",
                "            _cell.setData(_value, self._cbcs_line_role)",
                "            _cell.setText(self._cbcs_line_show(%d, _value))" % index,
                "            _cell.setToolTip(_tip)",
                "            _cell.setEditable(False)",
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
        "_nullable = self._cbcs_line_nullable[_index.column()]",
        "_scale = self._cbcs_line_scales[_index.column()]",
        "if _kind == %s:" % py_string("lookup"),
        "    _box = QComboBox(_parent)",
        "    _box.addItem(%s, None)" % py_string("(choose)"),
        "    for _key, _label in self._cbcs_line_lookup.get(_name, ()):",
        "        _box.addItem(str(_label), _key)",
        "    return _box",
        "if _kind == %s:" % py_string("bool"),
        "    _check = QCheckBox(_parent)",
        "    if _nullable:",
        "        _check.setTristate(True)",
        "    return _check",
        "if _kind == %s:" % py_string("int"),
        "    _spin = QSpinBox(_parent)",
        "    _spin.setRange(-2147483647, 2147483647)",
        "    if _nullable:",
        "        _spin.setMinimum(_spin.minimum() - 1)",
        "        _spin.setSpecialValueText(%s)" % py_string(" "),
        "    return _spin",
        "if _kind == %s:" % py_string("decimal"),
        "    _spin = QDoubleSpinBox(_parent)",
        "    _spin.setDecimals(_scale if _scale > 0 else 2)",
        "    _spin.setRange(-1000000000000, 1000000000000)",
        "    if _nullable:",
        "        _spin.setMinimum(_spin.minimum() - _spin.singleStep())",
        "        _spin.setSpecialValueText(%s)" % py_string(" "),
        "    return _spin",
        "if _kind == %s:" % py_string("date"),
        "    _edit = QDateEdit(_parent)",
        "    _edit.setDisplayFormat(%s)" % py_string("yyyy-MM-dd"),
        "    _edit.setCalendarPopup(True)",
        "    if _nullable:",
        "        _edit.setMinimumDate(_edit.minimumDate().addDays(-1))",
        "        _edit.setSpecialValueText(%s)" % py_string(" "),
        "    return _edit",
        "if _kind == %s:" % py_string("time"),
        "    _edit = QTimeEdit(_parent)",
        "    _edit.setDisplayFormat(%s)" % py_string("HH:mm:ss"),
        "    if _nullable:",
        "        def _touch(_t, _w=_edit):",
        "            if getattr(_w, %s, False):" % py_string("_cbcs_time_arming"),
        "                return",
        "            if not _w.property(%s):" % py_string("cbcsTimeBlank"),
        "                return",
        "            _w.setProperty(%s, False)" % py_string("cbcsTimeBlank"),
        "            _w.setSpecialValueText(%s)" % py_string(""),
        "        _edit.timeChanged.connect(_touch)",
        "        class _CbcsTimeClear(QObject):",
        "            def __init__(self, widget):",
        "                super().__init__(widget)",
        "                self._widget = widget",
        "                widget.installEventFilter(self)",
        "                _line = widget.lineEdit()",
        "                if _line is not None:",
        "                    _line.installEventFilter(self)",
        "                    _line.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)",
        "                    _line.customContextMenuRequested.connect(self._menu)",
        "            def _blank(self):",
        "                _w = self._widget",
        "                _w._cbcs_time_arming = True",
        "                _w.setProperty(%s, True)" % py_string("cbcsTimeBlank"),
        "                _w.setSpecialValueText(%s)" % py_string(" "),
        "                _w.setTime(_w.minimumTime())",
        "                _w._cbcs_time_arming = False",
        "            def _menu(self, _pos):",
        "                _line = self._widget.lineEdit()",
        "                if _line is None:",
        "                    return",
        "                _menu = _line.createStandardContextMenu()",
        "                _menu.addAction(%s, self._blank)" % py_string("Clear"),
        "                _menu.popup(_line.mapToGlobal(_pos))",
        "            def eventFilter(self, _watched, _event):",
        "                if _event.type() == QEvent.Type.KeyPress and _event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):",
        "                    _line = self._widget.lineEdit()",
        "                    if _line is not None and _line.text() and _line.selectedText() == _line.text():",
        "                        self._blank()",
        "                        return True",
        "                return False",
        "        _edit._cbcs_time_clear = _CbcsTimeClear(_edit)",
        "    return _edit",
        "if _kind == %s:" % py_string("datetime"),
        "    _edit = QDateTimeEdit(_parent)",
        "    _edit.setDisplayFormat(%s)" % py_string("yyyy-MM-dd HH:mm:ss"),
        "    _edit.setCalendarPopup(True)",
        "    if _nullable:",
        "        _edit.setMinimumDateTime(_edit.minimumDateTime().addSecs(-1))",
        "        _edit.setSpecialValueText(%s)" % py_string(" "),
        "    return _edit",
        "return QLineEdit(_parent)",
    ]


def _editor_data_body() -> List[str]:
    return [
        "_value = _index.data(self._cbcs_line_role)",
        "_kind = self._cbcs_line_kinds[_index.column()]",
        "_nullable = self._cbcs_line_nullable[_index.column()]",
        "if _kind == %s:" % py_string("bool"),
        "    if _value is None and _nullable:",
        "        _editor.setCheckState(Qt.CheckState.PartiallyChecked)",
        "    else:",
        "        _editor.setChecked(True if _value else False)",
        "    return",
        "if _kind == %s:" % py_string("int"),
        "    if _value is None and _nullable:",
        "        _editor.setValue(_editor.minimum())",
        "    else:",
        "        _editor.setValue(0 if _value is None else int(_value))",
        "    return",
        "if _kind == %s:" % py_string("decimal"),
        "    if _value is None and _nullable:",
        "        _editor.setValue(_editor.minimum())",
        "    else:",
        "        _editor.setValue(0.0 if _value is None else float(_value))",
        "    return",
        "if _kind == %s:" % py_string("date"),
        "    if _value is None or _value == %s:" % py_string(""),
        "        if _nullable or _value is None or _value == %s:" % py_string(""),
        "            _editor.setDate(_editor.minimumDate())",
        "            return",
        "    try:",
        "        if isinstance(_value, datetime):",
        "            _day = _value.date()",
        "        elif isinstance(_value, date):",
        "            _day = _value",
        "        else:",
        "            _day = date.fromisoformat(str(_value)[:10])",
        "    except ValueError:",
        "        _note = getattr(self, %s, None)" % py_string("_cbcs_note_unparsed"),
        "        if _note is not None:",
        "            _names = getattr(self, %s, ())" % py_string("_cbcs_line_names"),
        "            _col = _names[_index.column()] if _index.column() < len(_names) else %s" % py_string("date"),
        "            _note(_col, %s, _value)" % py_string("date"),
        "        _editor.setDate(_editor.minimumDate())",
        "        return",
        "    _editor.setDate(QDate(_day.year, _day.month, _day.day))",
        "    return",
        "if _kind == %s:" % py_string("time"),
        "    if _value is None and _nullable:",
        "        _editor._cbcs_time_arming = True",
        "        _editor.setProperty(%s, True)" % py_string("cbcsTimeBlank"),
        "        _editor.setSpecialValueText(%s)" % py_string(" "),
        "        _editor.setTime(_editor.minimumTime())",
        "        _editor._cbcs_time_arming = False",
        "        return",
        "    try:",
        "        if isinstance(_value, datetime):",
        "            _clock = _value.time()",
        "        elif isinstance(_value, time):",
        "            _clock = _value",
        "        else:",
        "            _clock = time.fromisoformat(str(_value or %s))" % py_string("00:00:00"),
        "    except ValueError:",
        "        _note = getattr(self, %s, None)" % py_string("_cbcs_note_unparsed"),
        "        if _note is not None:",
        "            _names = getattr(self, %s, ())" % py_string("_cbcs_line_names"),
        "            _col = _names[_index.column()] if _index.column() < len(_names) else %s" % py_string("time"),
        "            _note(_col, %s, _value)" % py_string("time"),
        "        _editor._cbcs_time_arming = True",
        "        _editor.setProperty(%s, True)" % py_string("cbcsTimeBlank"),
        "        _editor.setSpecialValueText(%s)" % py_string(" "),
        "        _editor.setTime(_editor.minimumTime())",
        "        _editor._cbcs_time_arming = False",
        "        return",
        "    _editor.setProperty(%s, False)" % py_string("cbcsTimeBlank"),
        "    _editor.setSpecialValueText(%s)" % py_string(""),
        "    _editor.setTime(QTime(_clock.hour, _clock.minute, _clock.second))",
        "    return",
        "if _kind == %s:" % py_string("datetime"),
        "    if _value is None and _nullable:",
        "        _editor.setDateTime(_editor.minimumDateTime())",
        "        return",
        "    try:",
        "        _stamp = _value if isinstance(_value, datetime) else datetime.fromisoformat(str(_value).replace('T', ' '))",
        "    except ValueError:",
        "        _note = getattr(self, %s, None)" % py_string("_cbcs_note_unparsed"),
        "        if _note is not None:",
        "            _names = getattr(self, %s, ())" % py_string("_cbcs_line_names"),
        "            _col = _names[_index.column()] if _index.column() < len(_names) else %s" % py_string("when"),
        "            _note(_col, %s, _value)" % py_string("date and time"),
        "        _editor.setDateTime(_editor.minimumDateTime())",
        "        return",
        "    _editor.setDateTime(QDateTime(_stamp.year, _stamp.month, _stamp.day, _stamp.hour, _stamp.minute, _stamp.second))",
        "    return",
        "if _kind == %s:" % py_string("lookup"),
        "    _found = _editor.findData(_value)",
        "    if _found < 0 and _value is not None:",
        "        _errors = getattr(self, %s, None)" % py_string("_cbcs_line_lookup_error"),
        "        _reason = _errors.get(_name) if isinstance(_errors, dict) else None",
        "        if _reason:",
        "            _editor.addItem(str(_reason), _value)",
        "        else:",
        "            _editor.addItem(%s %% _value, _value)" % py_string("(unknown #%s)"),
        "        _found = _editor.findData(_value)",
        "    _editor.setCurrentIndex(0 if _found < 0 else _found)",
        "    return",
        "_editor.setText(%s if _value is None else str(_value))" % py_string(""),
    ]


def _commit_body() -> List[str]:
    return [
        "_kind = self._cbcs_line_kinds[_index.column()]",
        "_nullable = self._cbcs_line_nullable[_index.column()]",
        "_before = self._cbcs_line_dict(_index.row())",
        "if _kind == %s:" % py_string("bool"),
        "    _state = _editor.checkState()",
        "    if _nullable and _state == Qt.CheckState.PartiallyChecked:",
        "        _value = None",
        "    else:",
        "        _value = True if _editor.isChecked() else False",
        "elif _kind == %s:" % py_string("int"),
        "    if _nullable and _editor.value() == _editor.minimum():",
        "        _value = None",
        "    else:",
        "        _value = int(_editor.value())",
        "elif _kind == %s:" % py_string("decimal"),
        "    if _nullable and _editor.value() == _editor.minimum():",
        "        _value = None",
        "    else:",
        "        _value = Decimal(str(_editor.value()))",
        "elif _kind == %s:" % py_string("date"),
        "    _day = _editor.date()",
        "    if _nullable and _day == _editor.minimumDate():",
        "        _value = None",
        "    elif _day.isValid():",
        "        _value = _day.toPython()",
        "    else:",
        "        _value = None if _nullable else _index.data(self._cbcs_line_role)",
        "elif _kind == %s:" % py_string("time"),
        "    if _nullable and _editor.property(%s):" % py_string("cbcsTimeBlank"),
        "        _value = None",
        "    else:",
        "        _value = _editor.time().toPython()",
        "elif _kind == %s:" % py_string("datetime"),
        "    _stamp = _editor.dateTime()",
        "    if _nullable and _stamp == _editor.minimumDateTime():",
        "        _value = None",
        "    elif _stamp.isValid():",
        "        _value = _stamp.toPython()",
        "    else:",
        "        _value = None if _nullable else _index.data(self._cbcs_line_role)",
        "elif _kind == %s:" % py_string("lookup"),
        "    _value = _editor.currentData()",
        "else:",
        "    _text_in = _editor.text()",
        "    _value = None if _text_in == %s and _nullable else _text_in" % py_string(""),
        "_text = self._cbcs_line_show(_index.column(), _value)",
        "_model.blockSignals(True)",
        "_cell = _model.item(_index.row(), _index.column())",
        "if _cell is not None:",
        "    _cell.setData(_value, self._cbcs_line_role)",
        "    _cell.setText(_text)",
        "    if self._cbcs_line_scales[_index.column()] >= 0:",
        "        _cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)",
        "_model.blockSignals(False)",
        "self._cbcs_line_defaults(_index.row(), _before)",
        "self._cbcs_line_changed()",
    ]


def _also_body() -> List[str]:
    return ["return self._cbcs_line_also_map.get((_column, _key, _name))"]


def _label_body() -> List[str]:
    return [
        "_errors = getattr(self, %s, None)" % py_string("_cbcs_line_lookup_error"),
        "if isinstance(_errors, dict):",
        "    _reason = _errors.get(_name)",
        "    if _reason:",
        "        return str(_reason)",
        "for _id, _label in self._cbcs_line_lookup.get(_name, ()):",
        "    if _id == _key:",
        "        return str(_label)",
        "if _key is None:",
        "    return %s" % py_string(""),
        "return %s %% _key" % py_string("(unknown #%s)"),
    ]


def _lookup_body(columns: Sequence[_Col], engine: str) -> List[str]:
    del columns, engine
    return [
        "_lookup = {}",
        "_also_map = {}",
        "_errors = {}",
        "_cursor = _conn.cursor()",
        "for _name, _sql, _table, _show_at, _also in self._cbcs_line_lookups:",
        "    try:",
        "        _cursor.execute(_sql)",
        "    except Exception as _error:",
        "        _text = str(_error).strip().splitlines()",
        "        _errors[_name] = _text[0] if _text else %s" % py_string("Couldn't load this list."),
        "        continue",
        "    _pairs = []",
        "    for _item in _cursor.fetchall():",
        "        _key = _item[0]",
        "        _label = _item[_show_at] if len(_item) > _show_at else _item[0]",
        "        _pairs.append((_key, _label))",
        "        for _also_name, _index in _also:",
        "            _raw = _item[_index] if len(_item) > _index else None",
        "            _also_map[(_name, _key, _also_name)] = self._cbcs_line_from(_table, _also_name, _raw)",
        "    _lookup[_name] = tuple(_pairs)",
        "self._cbcs_line_lookup = _lookup",
        "self._cbcs_line_also_map = _also_map",
        "self._cbcs_line_lookup_error = _errors",
        "if _errors:",
        "    raise RuntimeError(next(iter(_errors.values())))",
    ]


def _reload_body(connection: str) -> List[str]:
    return [
        "import cbcs_connections",
        "try:",
        "    with cbcs_connections.work(%s) as _conn:" % py_string(connection),
        "        self._cbcs_load_line_lookups(_conn)",
        "except Exception as _error:",
        "    _tell = getattr(self, %s, None)" % py_string("_cbcs_show_db_error"),
        "    if _tell is not None:",
        "        _tell(_error)",
        "    else:",
        "        QMessageBox.warning(self._form, %s, str(_error))" % py_string(""),
    ]


def _line_from_body(carried: Sequence[Tuple[str, str, str]]) -> List[str]:
    lines = []
    first = True
    for table, column, family in carried:
        word = "if" if first else "elif"
        first = False
        lines.append("%s _table == %s and _column == %s:" % (word, py_string(table), py_string(column)))
        for line in _from_family(family, column):
            lines.append("    " + line)
    lines.append("return _value")
    return lines


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
    return all(name_usable(name) for name in names if name)


def _stretch_index(columns: Sequence[_Col]) -> int:
    """The first text column that is not a lookup. The last column when there is none."""

    for index, column in enumerate(columns):
        if column.kind != "lookup" and column.family == "text":
            return index
    return max(0, len(columns) - 1)


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
        scale = -1
        if editor == "int":
            scale = 0
        elif editor == "decimal":
            shown = getattr(kind, "decimals", None)
            scale = 2 if shown is None else int(shown)
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
                scale,
            )
        )
    number_scales = [item.scale for item in found if item.scale > 0]
    finished = []
    for item in found:
        if item.calculated and item.family == "decimal":
            finished.append(replace(item, scale=max(number_scales) if number_scales else 2))
        else:
            finished.append(item)
    return tuple(finished)


def _editor_kind(column: DataColumn, family: str) -> str:
    if column.lookup is not None:
        return "lookup"
    if family == "bool" or column.kind == "yesno":
        return "bool"
    if family == "date":
        return "date"
    if family == "time":
        return "time"
    if family == "datetime":
        return "datetime"
    if column.kind == "whole" or family == "int":
        return "int"
    if column.kind in ("money", "decimal", "number") or family == "decimal":
        return "decimal"
    return "text"


def _family_of(name: str, columns: Sequence[_Col], rows: Rows, table: object, engine: str) -> str:
    del rows
    for column in columns:
        if column.name == name:
            return column.family
    schema_column = _schema_column(table, name)
    if schema_column is None:
        return ""
    kind = describe(schema_column.type, engine=engine, column_name=name, nullable=schema_column.nullable)
    return kind.direction or ""


def _nullable_of(name: str, columns: Sequence[_Col], rows: Rows) -> bool:
    for column in columns:
        if column.name == name:
            return column.nullable
    if name == rows.key:
        return False
    return True


def _carried_families(doc: UiDocument, connection: str, columns: Sequence[_Col], engine: str) -> Tuple[Tuple[str, str, str], ...]:
    """``(lookup table, column, family)`` for carried columns whose schema is known."""

    found = []
    seen = set()
    chosen = engine if engine in ("sqlite", "postgres") else "sqlite"
    for column in columns:
        lookup = column.lookup
        if lookup is None or not lookup.also:
            continue
        table = _line_table(doc, connection, lookup.table)
        for name in lookup.also:
            key = (lookup.table, name)
            if key in seen:
                continue
            spec = _schema_column(table, name)
            if spec is None:
                continue
            seen.add(key)
            kind = describe(spec.type, engine=chosen, column_name=name, nullable=spec.nullable)
            found.append((lookup.table, name, kind.direction or "text"))
    return tuple(found)


def _row_attrs(doc: UiDocument, connection: str, columns: Sequence[_Col], engine: str) -> dict:
    """Lookup-table types for ``column.attr``. A missing schema leaves the map empty."""

    found = {}
    chosen = engine if engine in ("sqlite", "postgres") else "sqlite"
    for column in columns:
        lookup = column.lookup
        if lookup is None or not lookup.also:
            continue
        table = _line_table(doc, connection, lookup.table)
        typed = {}
        for name in lookup.also:
            spec = _schema_column(table, name)
            if spec is None:
                continue
            kind = describe(spec.type, engine=chosen, column_name=name, nullable=spec.nullable)
            typed[name] = type_for_kind(kind.kind)
        found[column.name] = typed
    return found


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


def _type_kind(column: _Col) -> str:
    if column.calculated:
        return "money" if column.scale >= 0 else "text"
    if column.kind == "int":
        return "whole"
    if column.kind == "decimal":
        return "money" if column.scale == 2 else "decimal"
    if column.kind == "bool":
        return "yesno"
    return column.kind or "text"


def _pairs(columns: Sequence[_Col]) -> Tuple[Tuple[str, str], ...]:
    return tuple((column.name, _type_kind(column)) for column in columns)


def _compiled(text: str, columns: Sequence[_Col], target: str, attrs: Optional[Mapping[str, Mapping[str, object]]] = None):
    return compile_line_formula(text, _pairs(columns), target, attrs)


def _formulas(columns: Sequence[_Col], attrs: Optional[Mapping[str, Mapping[str, object]]] = None):
    found = []
    for column in columns:
        text = column.formula or column.default
        if text:
            found.append((column, _compiled(text, columns, _type_kind(column), attrs)))
    return found


def _show_body() -> List[str]:
    return [
        "if _value is None:",
        "    return %s" % py_string(""),
        "_scale = self._cbcs_line_scales[_column]",
        "if _scale < 0:",
        "    if isinstance(_value, bool):",
        "        return %s if _value else %s" % (py_string("Yes"), py_string("No")),
        "    if hasattr(_value, 'isoformat'):",
        "        if hasattr(_value, 'year') and hasattr(_value, 'hour'):",
        "            return _value.isoformat(sep=%s)" % py_string(" "),
        "        return _value.isoformat()",
        "    return str(_value)",
        "if _scale == 0:",
        "    return str(int(_value))",
        "_number = _value if isinstance(_value, Decimal) else Decimal(str(_value))",
        "_places = Decimal('1').scaleb(-_scale)",
        "return format(_number.quantize(_places), 'f')",
    ]


def _defaults_body(view: str, columns: Sequence[_Col], attrs: Optional[Mapping[str, Mapping[str, object]]] = None) -> List[str]:
    lines = [
        "_model = self.%s.model()" % view,
        "if _model is None:",
        "    return",
        "_row = self._cbcs_line_dict(_row_index)",
    ]
    emitted = False
    for index, column in enumerate(columns):
        if not column.default or column.calculated:
            continue
        compiled = _compiled(column.default, columns, _type_kind(column), attrs)
        reads = [name for name, _kind in _pairs(columns) if name in column.default and name != column.name]
        if not compiled[0] or not reads:
            continue
        emitted = True
        lines.append("_changed = False")
        for name in reads:
            lines.append(
                "if _before.get(%s) != _row.get(%s):" % (py_string(name), py_string(name))
            )
            lines.append("    _changed = True")
        lines.extend(
            [
                "if _changed:",
                "    _old_row = _row",
                "    _row = _before",
                "    _previous = %s" % compiled[0],
                "    _row = _old_row",
                "    _next = %s" % compiled[0],
                "    _cell = _model.item(_row_index, %d)" % index,
                "    _current = None if _cell is None else _cell.data(self._cbcs_line_role)",
                "    if _cell is not None and (_current is None or _current == %s or _current == _previous):" % py_string(""),
                "        _cell.setData(_next, self._cbcs_line_role)",
                "        _cell.setText(self._cbcs_line_show(%d, _next))" % index,
            ]
        )
    if not emitted:
        lines.append("return")
    return lines


def _widgets(doc: UiDocument):
    try:
        return tuple(doc.iter_widgets())
    except Exception:
        return ()


def _open_line_lookups(doc: UiDocument, ctx: CodegenContext) -> Tuple[str, ...]:
    """Load line lookups once, before the first record.

    A parent lookup already calls ``cbcs_load_lookups`` on open, and that method
    reloads the grid lists too. This hook covers a grid that is the only lookup.
    """

    from app.features.form_builder.engine.codegen.lookup_plan import lookup_plans

    if lookup_plans(doc, ctx.attribute_names):
        return ()
    for _name, rows in _grids(doc, ctx):
        for column in rows.columns:
            if isinstance(column, DataColumn) and column.lookup is not None:
                return (
                    "_reload_lines = getattr(self, %s, None)" % py_string("_cbcs_reload_line_lookups"),
                    "if _reload_lines is not None:",
                    "    _reload_lines()",
                )
    return ()


def _install_line_lookup_hook() -> None:
    register_open_hook(_open_line_lookups)


_install_line_lookup_hook()


EXPANDER = RowsExpander()
