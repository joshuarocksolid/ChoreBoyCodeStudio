"""Record navigation, save, and the unsaved-changes prompt (CONTRACTS.md section 19.5).

SQL text comes from ``engine.data.sql``. This module concatenates those pieces.
A form that is not a record source contributes nothing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from app.features.form_builder.engine.codegen.expanders.form_events import _GUARDS, register_close_guard
from app.features.form_builder.engine.codegen.literals import py_string
from app.features.form_builder.engine.codegen.logic_hooks import CodegenContext, Contribution, Method
from app.features.form_builder.engine.data.source import Hooks, RecordSource, read_bind, read_bind_mode, read_data, singular
from app.features.form_builder.engine.data.sql import (
    assignment_piece,
    conflict_piece,
    delete_row,
    find_keys,
    insert_row,
    key_clause,
    load_one,
    select_keys,
    update_head,
)
from app.features.form_builder.engine.data.types import describe
from app.features.form_builder.engine.logic import compat
from app.features.form_builder.engine.logic.storage import FORMULA_KEYS
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import CStringValue, StringValue

_GUARD_ID = "record.leave"
_WIDGET_IO = {
    "QLineEdit": "text",
    "QPlainTextEdit": "plain",
    "QTextEdit": "plain",
    "QSpinBox": "int",
    "QDoubleSpinBox": "decimal",
    "QDateEdit": "date",
    "QTimeEdit": "text",
    "QDateTimeEdit": "text",
    "QCheckBox": "bool",
    "QComboBox": "data",
}


@dataclass(frozen=True)
class _Field:
    widget: str
    io: str
    column: str
    family: str
    nullable: bool
    writable: bool
    display: str
    points_to: str


def _leave_lines(doc: UiDocument, ctx: CodegenContext) -> Tuple[str, ...]:
    """Lines for the close guard. Empty unless this form is a record source.

    Form events inserts these before its own ``event.type()`` test, so the
    lines test the event themselves.
    """

    del ctx
    if _source(doc) is None:
        return ()
    return (
        "if event.type() == QEvent.Type.Close or (event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape and isinstance(obj, QDialog)):",
        "    if not self.ui._cbcs_confirm_leave():",
        "        if event.type() == QEvent.Type.Close:",
        "            event.ignore()",
        "        return True",
    )


def _install_guard() -> None:
    if any(guard_id == _GUARD_ID for _order, guard_id, _fn in _GUARDS):
        return
    register_close_guard(400, _GUARD_ID, _leave_lines)


_install_guard()


class RecordExpander:
    expander_id = "record"
    level = 4
    order = 400

    def contribute(self, doc: UiDocument, ctx: CodegenContext) -> Contribution:
        source = _source(doc)
        if source is None:
            return Contribution()
        _install_guard()
        engine = _engine(ctx, source.connection)
        fields = _fields(doc, ctx, source, engine)
        record_word = source.record_word or singular(source.table)
        order = source.order or ((source.key, "asc"),)
        search = source.search or tuple(field.column for field in fields if field.family == "text" and field.writable)
        check = source.conflicts != "overwrite"
        hooks = source.hooks or Hooks()
        methods = _methods(source, fields, engine, record_word, order, search, check, hooks)
        imports = _imports(fields, not _closing_generates(doc))
        setup: List[str] = []
        if not _closing_generates(doc):
            setup.extend(_own_filter(ctx.form_param))
        connects: List[Tuple[str, str]] = []
        if _refresh_will_exist(doc, ctx):
            connects = [(field.widget, "cbcs_refresh") for field in fields if field.writable]
        ordered: List[Tuple[int, str]] = [
            (10, "self._cbcs_record = {}"),
            (10, "self._cbcs_keys = []"),
            (10, "self._cbcs_index = -1"),
            (10, "self._cbcs_key = None"),
            (10, "self._cbcs_saved_fields = {}"),
            (10, "self._cbcs_loaded = {}"),
            (10, "self._cbcs_filtered = False"),
            (10, "self._cbcs_new = False"),
            (10, "self._cbcs_ready = False"),
            (10, "self._cbcs_refreshing = False"),
        ]
        open_line = _open_line(source.open_at)
        if open_line:
            ordered.append((890, open_line))
        return Contribution(
            imports=tuple(imports),
            setup_lines=tuple(setup),
            methods=tuple(methods),
            needs_form=True,
            connects=tuple(connects),
            ordered_setup=tuple(ordered),
        )


def _methods(source, fields, engine, record_word, order, search, check, hooks) -> List[Method]:
    noun = record_word
    table = source.table
    key = source.key
    connection = source.connection
    columns = tuple(field.column for field in fields)
    load_columns = columns if key in columns else columns + (key,)
    writable = tuple(field for field in fields if field.writable and field.column != key)
    # A bound key is written only when the person typed one. The insert list is the other columns.
    insert_columns = tuple(field.column for field in writable)
    pieces = _sql(engine, table, key, noun, order, search, load_columns, insert_columns, writable, check)
    bodies = {
        "cbcs_open": ("key=None", _open_body(pieces, connection)),
        "_cbcs_show": ("_index", _show_body(pieces, connection, fields, hooks)),
        "_cbcs_start_new": ("", _new_body(fields, hooks)),
        "cbcs_read_fields": ("", _read_body(fields)),
        "cbcs_write_fields": ("_row", _write_body(fields)),
        "_cbcs_snapshot": ("", ["return getattr(self, %s, {})" % _q("_cbcs_saved_fields")]),
        "_cbcs_is_dirty": ("", _dirty_body(writable)),
        "_cbcs_bind": ("_column, _value", _bind_body(fields, engine)),
        "_cbcs_from": ("_column, _value", _from_body(fields)),
        "_cbcs_fill_record": ("_raw", _fill_body(load_columns)),
        "_cbcs_confirm_leave": ("", _confirm_body(noun)),
        "cbcs_confirm_leave": ("", ["return self._cbcs_confirm_leave()"]),
        "cbcs_is_dirty": ("", ["return self._cbcs_is_dirty()"]),
        "cbcs_current_key": ("", ["return getattr(self, %s, None)" % _q("_cbcs_key")]),
        "_cbcs_like_pattern": ("_text", _pattern_body()),
        "_cbcs_show_db_error": ("_error", _error_body(noun, fields)),
        "_cbcs_ask_delete": ("", _delete_ask_body(noun)),
        "_cbcs_tell_deleted": ("", _deleted_body(noun)),
        "_cbcs_conflict": ("", _conflict_body(noun, source.conflicts == "overwrite")),
        "cbcs_save": ("", _save_body(hooks)),
        "_cbcs_write": ("_overwrite", _write_sql_body(pieces, connection, fields, writable, check, hooks)),
        "cbcs_delete": ("", _delete_body(pieces, connection, hooks)),
        "cbcs_new": ("", _verb_new()),
        "cbcs_revert": ("", _revert_body()),
        "cbcs_reload": ("", ["self.cbcs_revert()"]),
        "cbcs_first": ("", _move_body("first")),
        "cbcs_previous": ("", _move_body("previous")),
        "cbcs_next": ("", _move_body("next")),
        "cbcs_last": ("", _move_body("last")),
        "cbcs_find": ("", _find_body(pieces, connection)),
        "cbcs_show_all": ("", _show_all_body()),
        "_cbcs_form_position": ("", _position_body()),
        "_cbcs_form_count": ("", ["return len(getattr(self, %s, ()) or ())" % _q("_cbcs_keys")]),
        "_cbcs_form_is_new": ("", ["return True if getattr(self, %s, False) else False" % _q("_cbcs_new")]),
        "_cbcs_form_is_dirty": ("", ["return self._cbcs_is_dirty()"]),
        "_cbcs_form_is_filtered": ("", ["return True if getattr(self, %s, False) else False" % _q("_cbcs_filtered")]),
        "_cbcs_open_last": ("", ["self.cbcs_open()", "if self._cbcs_keys:", "    self._cbcs_show(len(self._cbcs_keys) - 1)"]),
        "_cbcs_open_new": ("", ["self.cbcs_open()", "self._cbcs_start_new()"]),
        "_cbcs_find_note": ("_count", _find_note_body()),
    }
    methods = []
    for name, (params, lines) in bodies.items():
        methods.append(Method(name=name, body="\n".join(lines), source_ref="record", params=params))
    return methods


def _sql(engine, table, key, noun, order, search, load_columns, insert_columns, writable, check):
    conflict = tuple(field.column for field in writable)
    tail = key_clause(engine, key)
    if check:
        for column in conflict:
            tail += " AND " + conflict_piece(engine, column)
    return {
        "keys": select_keys(engine, table, key, order).text,
        "load": load_one(engine, table, load_columns, key, noun).text,
        "insert": insert_row(engine, table, insert_columns, key).text,
        "delete": delete_row(engine, table, key).text,
        "find": find_keys(engine, table, key, order, search).text,
        "head": update_head(engine, table) + " ",
        "tail": tail,
        "assign": {field.column: assignment_piece(engine, field.column) for field in writable},
        "load_columns": load_columns,
        "insert_columns": insert_columns,
        "search": tuple(search),
        "engine": engine,
        "exists": load_one(engine, table, (key,), key, noun).text,
    }


def _open_body(pieces, connection) -> List[str]:
    return [
        "import cbcs_connections",
        "with cbcs_connections.work(%s) as _conn:" % _q(connection),
        "    _cursor = _conn.cursor()",
        "    _cursor.execute(%s)" % _q(pieces["keys"]),
        "    self._cbcs_keys = [_item[0] for _item in _cursor.fetchall()]",
        "self._cbcs_filtered = False",
        "self._cbcs_find_note(None)",
        "if key is not None and key in self._cbcs_keys:",
        "    self._cbcs_show(self._cbcs_keys.index(key))",
        "elif self._cbcs_keys:",
        "    self._cbcs_show(0)",
        "else:",
        "    self._cbcs_start_new()",
    ]


def _show_body(pieces, connection, fields, hooks) -> List[str]:
    lines = [
        "if _index < 0 or _index >= len(self._cbcs_keys):",
        "    self._cbcs_start_new()",
        "    return",
        "_key = self._cbcs_keys[_index]",
        "import cbcs_connections",
        "with cbcs_connections.work(%s) as _conn:" % _q(connection),
        "    _cursor = _conn.cursor()",
        "    _cursor.execute(%s, (_key,))" % _q(pieces["load"]),
        "    _fetched = _cursor.fetchone()",
        "if _fetched is None:",
        "    _kept = []",
        "    for _item in self._cbcs_keys:",
        "        if _item != _key:",
        "            _kept.append(_item)",
        "    self._cbcs_keys = _kept",
        "    if _kept and _index < len(_kept):",
        "        self._cbcs_show(_index)",
        "    elif _kept:",
        "        self._cbcs_show(len(_kept) - 1)",
        "    else:",
        "        self._cbcs_start_new()",
        "    return",
        "_raw = {}",
    ]
    for index, column in enumerate(pieces["load_columns"]):
        lines.append("_raw[%s] = _fetched[%d]" % (_q(column), index))
    lines.extend(
        [
            "self._cbcs_loaded = _raw",
            "self._cbcs_fill_record(_raw)",
            "self.cbcs_write_fields(_raw)",
            "self._cbcs_saved_fields = self.cbcs_read_fields()",
            "self._cbcs_ready = True",
            "self._cbcs_new = False",
            "self._cbcs_key = _key",
            "self._cbcs_index = _index",
            "_load_lines = getattr(self, %s, None)" % _q("_cbcs_load_lines"),
            "if _load_lines is not None:",
            "    import cbcs_connections",
            "    with cbcs_connections.work(%s) as _conn:" % _q(connection),
            "        _load_lines(_conn, _key)",
        ]
    )
    lines.extend(_call_event("cbcsOnRecordLoaded", False))
    lines.extend(_call_hook(hooks.after_load, False))
    lines.extend(_refresh_call())
    return lines


def _new_body(fields, hooks) -> List[str]:
    lines = [
        "self._cbcs_new = True",
        "self._cbcs_key = None",
        "self._cbcs_index = -1",
        "self._cbcs_loaded = {}",
        "self._cbcs_record = {}",
        "self.cbcs_write_fields({})",
        "self._cbcs_saved_fields = self.cbcs_read_fields()",
        "self._cbcs_ready = True",
    ]
    lines.extend(_call_event("cbcsOnNewRecord", False))
    lines.extend(_call_hook(hooks.new_record, False))
    lines.extend(_refresh_call())
    return lines


def _read_body(fields: Sequence[_Field]) -> List[str]:
    lines = ["_fields = {}"]
    for field in fields:
        lines.extend(_read_field(field))
    lines.append("return _fields")
    return lines


def _read_field(field: _Field) -> List[str]:
    widget = "self.%s" % field.widget
    key = "_fields[%s]" % _q(field.column)
    if field.io == "text":
        lines = ["_text = %s.text()" % widget]
    elif field.io == "plain":
        lines = ["_text = %s.toPlainText()" % widget]
    elif field.io == "int":
        return ["%s = int(%s.value())" % (key, widget)]
    elif field.io == "decimal":
        return ["%s = Decimal(str(%s.value()))" % (key, widget)]
    elif field.io == "bool":
        return ["%s = True if %s.isChecked() else False" % (key, widget)]
    elif field.io == "date":
        return [
            "_day = %s.date()" % widget,
            "if _day.isValid():",
            "    %s = _day.toPython()" % key,
            "else:",
            "    %s = None" % key,
        ]
    elif field.io == "data":
        return ["%s = %s.currentData()" % (key, widget)]
    else:
        lines = ["_text = %s.text()" % widget]
    if field.family == "text" and field.nullable:
        lines.extend(["if _text == %s:" % _q(""), "    %s = None" % key, "else:", "    %s = _text" % key])
    else:
        lines.append("%s = _text" % key)
    return lines


def _write_body(fields: Sequence[_Field]) -> List[str]:
    lines = [
        "_was = getattr(self, %s, False)" % _q("_cbcs_refreshing"),
        "self._cbcs_refreshing = True",
        "try:",
    ]
    for field in fields:
        for line in _write_field(field):
            lines.append("    " + line)
    lines.extend(["finally:", "    self._cbcs_refreshing = _was"])
    return lines


def _write_field(field: _Field) -> List[str]:
    widget = "self.%s" % field.widget
    lines = [
        "%s.blockSignals(True)" % widget,
        "try:",
        "    _value = _row.get(%s) if _row else None" % _q(field.column),
    ]
    if field.io == "text":
        lines.extend(["    if _value is None:", "        %s.setText(%s)" % (widget, _q("")), "    else:", "        %s.setText(str(_value))" % widget])
    elif field.io == "plain":
        lines.extend(
            [
                "    if _value is None:",
                "        %s.setPlainText(%s)" % (widget, _q("")),
                "    else:",
                "        %s.setPlainText(str(_value))" % widget,
            ]
        )
    elif field.io == "int":
        lines.extend(
            [
                "    if _value is None or _value == %s:" % _q(""),
                "        %s.setValue(%s.minimum())" % (widget, widget),
                "    else:",
                "        %s.setValue(int(_value))" % widget,
            ]
        )
    elif field.io == "decimal":
        lines.extend(
            [
                "    if _value is None or _value == %s:" % _q(""),
                "        %s.setValue(0.0)" % widget,
                "    else:",
                "        %s.setValue(float(_value))" % widget,
            ]
        )
    elif field.io == "bool":
        lines.append("    %s.setChecked(True if _value else False)" % widget)
    elif field.io == "date":
        lines.extend(
            [
                "    if _value is None or _value == %s:" % _q(""),
                "        %s.setDate(QDate())" % widget,
                "    elif isinstance(_value, datetime):",
                "        _day = _value.date()",
                "        %s.setDate(QDate(_day.year, _day.month, _day.day))" % widget,
                "    elif isinstance(_value, date):",
                "        %s.setDate(QDate(_value.year, _value.month, _value.day))" % widget,
                "    else:",
                "        _day = date.fromisoformat(str(_value)[:10])",
                "        %s.setDate(QDate(_day.year, _day.month, _day.day))" % widget,
            ]
        )
    elif field.io == "data":
        lines.extend(
            [
                "    _picked = -1",
                "    _i = 0",
                "    while _i < %s.count():" % widget,
                "        if %s.itemData(_i) == _value:" % widget,
                "            _picked = _i",
                "            break",
                "        _i = _i + 1",
                "    %s.setCurrentIndex(_picked)" % widget,
            ]
        )
    else:
        lines.append("    %s.setText(%s if _value is None else str(_value))" % (widget, _q("")))
    lines.extend(["finally:", "    %s.blockSignals(False)" % widget])
    return lines


def _dirty_body(writable: Sequence[_Field]) -> List[str]:
    lines = [
        "if not getattr(self, %s, False):" % _q("_cbcs_ready"),
        "    return False",
        "_fields = self.cbcs_read_fields()",
        "_saved = self._cbcs_saved_fields",
    ]
    for field in writable:
        lines.extend(
            [
                "if _fields.get(%s) != _saved.get(%s):" % (_q(field.column), _q(field.column)),
                "    return True",
            ]
        )
    lines.extend(
        [
            "_lines = getattr(self, %s, False)" % _q("_cbcs_lines_dirty"),
            "if callable(_lines):",
            "    _lines = _lines()",
            "return True if _lines else False",
        ]
    )
    return lines


def _bind_body(fields: Sequence[_Field], engine: str) -> List[str]:
    lines = []
    first = True
    for field in fields:
        if not field.writable:
            continue
        word = "if" if first else "elif"
        first = False
        lines.append("%s _column == %s:" % (word, _q(field.column)))
        for line in _bind_family(field, engine):
            lines.append("    " + line)
    if first:
        lines.append("return _value")
    else:
        lines.append("return _value")
    return lines


def _bind_family(field: _Field, engine: str) -> List[str]:
    family = field.family
    if family == "text":
        lines = [
            "if isinstance(_value, bytes):",
            "    _value = _value.decode(%s)" % _q("utf-8"),
            "if _value is None:",
            "    return %s" % (_q("") if not field.nullable else "None"),
        ]
        if field.nullable:
            lines.extend(["if _value == %s:" % _q(""), "    return None"])
        lines.append("return str(_value)")
        return lines
    if family == "int":
        return [
            "if _value is None or _value == %s:" % _q(""),
            "    return None",
            "return int(_value)",
        ]
    if family == "decimal":
        lines = [
            "if _value is None or _value == %s:" % _q(""),
            "    return None",
            "if not isinstance(_value, Decimal):",
            "    _value = Decimal(str(_value))",
        ]
        if engine == "postgres":
            lines.append("return _value")
        else:
            lines.append("return str(_value)")
        return lines
    if family == "bool":
        if engine == "postgres":
            return ["if _value is None:", "    return None", "return True if _value else False"]
        return ["if _value is None:", "    return None", "return 1 if _value else 0"]
    if family == "date":
        lines = [
            "if _value is None or _value == %s:" % _q(""),
            "    return None",
            "if isinstance(_value, datetime):",
            "    _text = _value.date().isoformat()",
            "elif isinstance(_value, date):",
            "    _text = _value.isoformat()",
            "else:",
            "    _text = str(_value)[:10]",
        ]
        if engine == "postgres":
            lines.append("return date.fromisoformat(_text[:10])")
        else:
            lines.append("return _text")
        return lines
    return ["return _value"]


def _from_body(fields: Sequence[_Field]) -> List[str]:
    lines = []
    first = True
    seen = set()
    for field in fields:
        if field.column in seen:
            continue
        seen.add(field.column)
        word = "if" if first else "elif"
        first = False
        lines.append("%s _column == %s:" % (word, _q(field.column)))
        for line in _from_family(field.family):
            lines.append("    " + line)
    lines.append("return _value")
    return lines


def _from_family(family: str) -> List[str]:
    if family == "int":
        return ["if _value is None or _value == %s:" % _q(""), "    return None", "return int(_value)"]
    if family == "decimal":
        return [
            "if _value is None or _value == %s:" % _q(""),
            "    return None",
            "return _value if isinstance(_value, Decimal) else Decimal(str(_value))",
        ]
    if family == "bool":
        return [
            "if _value is None:",
            "    return None",
            "if isinstance(_value, str):",
            "    return _value not in (%s, %s, %s, %s)" % (_q(""), _q("0"), _q("false"), _q("False")),
            "return True if _value else False",
        ]
    if family == "date":
        return [
            "if _value is None or _value == %s:" % _q(""),
            "    return None",
            "if isinstance(_value, datetime):",
            "    return _value.date()",
            "if isinstance(_value, date):",
            "    return _value",
            "return date.fromisoformat(str(_value)[:10])",
        ]
    return [
        "if _value is None:",
        "    return None",
        "if isinstance(_value, bytes):",
        "    return _value.decode(%s)" % _q("utf-8"),
        "return str(_value)",
    ]


def _fill_body(columns: Sequence[str]) -> List[str]:
    lines = ["self._cbcs_record = {}"]
    for column in columns:
        lines.append("self._cbcs_record[%s] = self._cbcs_from(%s, _raw.get(%s))" % (_q(column), _q(column), _q(column)))
    return lines


def _confirm_body(noun: str) -> List[str]:
    return [
        "if not self._cbcs_is_dirty():",
        "    return True",
        "_answer = QMessageBox.question(",
        "    self._form,",
        "    %s," % _q("Unsaved changes"),
        "    %s," % _q("Save changes to this %s?" % noun),
        "    QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,",
        ")",
        "if _answer == QMessageBox.StandardButton.Save:",
        "    return self.cbcs_save() is True",
        "if _answer == QMessageBox.StandardButton.Discard:",
        "    return True",
        "return False",
    ]


def _pattern_body() -> List[str]:
    return [
        "_escaped = _text.replace(%s, %s).replace(%s, %s).replace(%s, %s)"
        % (_q("\\"), _q("\\\\"), _q("%"), _q("\\%"), _q("_"), _q("\\_")),
        "return %s + _escaped + %s" % (_q("%"), _q("%")),
    ]


def _error_body(noun: str, fields: Sequence[_Field]) -> List[str]:
    labels = []
    points = []
    for field in fields:
        labels.append("%s: %s" % (_q(field.column), _q(field.display)))
        if field.points_to:
            points.append("%s: %s" % (_q(field.column), _q(field.points_to)))
    label_map = "{" + ", ".join(labels) + "}" if labels else "{}"
    point_map = "{" + ", ".join(points) + "}" if points else "{}"
    return [
        "_text = str(_error)",
        "_state = %s" % _q(""),
        "for _attr in (%s, %s):" % (_q("sqlstate"), _q("pgcode")),
        "    _value = getattr(_error, _attr, None)",
        "    if isinstance(_value, str) and _value:",
        "        _state = _value",
        "_diag = getattr(_error, %s, None)" % _q("diag"),
        "if not _state and _diag is not None:",
        "    _value = getattr(_diag, %s, None)" % _q("sqlstate"),
        "    if isinstance(_value, str):",
        "        _state = _value",
        "_column = %s" % _q(""),
        "if %s in _text:" % _q("constraint failed:"),
        "    _tail = _text.split(%s, 1)[1].strip()" % _q("constraint failed:"),
        "    if %s in _tail:" % _q("."),
        "        _column = _tail.split(%s)[-1].strip()" % _q("."),
        "if not _column and _diag is not None:",
        "    _value = getattr(_diag, %s, None)" % _q("column_name"),
        "    if isinstance(_value, str):",
        "        _column = _value",
        "_labels = %s" % label_map,
        "_points = %s" % point_map,
        "_label = _labels.get(_column, _column or %s)" % _q("this field"),
        "_table = _points.get(_column, %s)" % _q("related"),
        "if _state == %s or %s in _text:" % (_q("23505"), _q("UNIQUE constraint failed")),
        "    QMessageBox.warning(self._form, %s, %s %% _label)" % (_q(""), _q("Another %s already uses this %%s." % noun)),
        "    return",
        "if _state == %s or %s in _text:" % (_q("23502"), _q("NOT NULL constraint failed")),
        "    QMessageBox.warning(self._form, %s, %s %% _label)" % (_q(""), _q("%s is required.")),
        "    return",
        "if _state == %s or %s in _text:" % (_q("23503"), _q("FOREIGN KEY constraint failed")),
        "    QMessageBox.warning(self._form, %s, %s %% (_label, _table))"
        % (_q(""), _q("%s must be one of the %s records.")),
        "    return",
        "QMessageBox.warning(self._form, %s, _text)" % _q(""),
    ]


def _delete_ask_body(noun: str) -> List[str]:
    return [
        "_box = QMessageBox(self._form)",
        "_box.setWindowTitle(%s)" % _q(""),
        "_box.setText(%s)" % _q("Delete this %s?" % noun),
        "_delete = _box.addButton(%s, QMessageBox.ButtonRole.AcceptRole)" % _q("Delete"),
        "_box.addButton(%s, QMessageBox.ButtonRole.RejectRole)" % _q("Cancel"),
        "_box.exec()",
        "return _box.clickedButton() is _delete",
    ]


def _deleted_body(noun: str) -> List[str]:
    return [
        "_box = QMessageBox(self._form)",
        "_box.setWindowTitle(%s)" % _q(""),
        "_box.setText(%s)" % _q("This %s was deleted by someone else." % noun),
        "_box.addButton(%s, QMessageBox.ButtonRole.AcceptRole)" % _q("Close"),
        "_box.exec()",
    ]


def _conflict_body(noun: str, allow_overwrite: bool) -> List[str]:
    lines = [
        "_box = QMessageBox(self._form)",
        "_box.setWindowTitle(%s)" % _q(""),
        "_box.setText(%s)" % _q("Someone else changed this %s since you opened it." % noun),
        "_reload = _box.addButton(%s, QMessageBox.ButtonRole.AcceptRole)" % _q("Reload their version"),
    ]
    if allow_overwrite:
        lines.append("_keep = _box.addButton(%s, QMessageBox.ButtonRole.ActionRole)" % _q("Keep mine and save"))
    else:
        lines.append("_keep = None")
    lines.extend(
        [
            "_box.addButton(%s, QMessageBox.ButtonRole.RejectRole)" % _q("Cancel"),
            "_box.exec()",
            "_clicked = _box.clickedButton()",
            "if _clicked is _reload:",
            "    self.cbcs_reload()",
            "    return False",
            "if _keep is not None and _clicked is _keep:",
            "    return self._cbcs_write(True)",
            "return False",
        ]
    )
    return lines


def _save_body(hooks: Hooks) -> List[str]:
    lines = [
        "if not self._cbcs_new and not self._cbcs_is_dirty():",
        "    return True",
        "_validate = getattr(self, %s, None)" % _q("cbcs_validate"),
        "if _validate is not None and _validate() is False:",
        "    return False",
    ]
    lines.extend(_call_event("cbcsOnBeforeSave", True))
    lines.extend(_call_hook(hooks.before_save, True))
    lines.append("return self._cbcs_write(False)")
    return lines


def _write_sql_body(pieces, connection, fields, writable, check, hooks) -> List[str]:
    lines = [
        "import cbcs_connections",
        "_fields = self.cbcs_read_fields()",
        "_inserted = False",
        "class _CbcsStop(Exception):",
        "    pass",
        "try:",
        "    with cbcs_connections.work(%s) as _conn:" % _q(connection),
        "        _cursor = _conn.cursor()",
        "        try:",
        "            if self._cbcs_new or self._cbcs_key is None:",
        "                _params = []",
    ]
    for column in pieces["insert_columns"]:
        lines.append("                _params.append(self._cbcs_bind(%s, _fields.get(%s)))" % (_q(column), _q(column)))
    lines.append("                _cursor.execute(%s, tuple(_params))" % _q(pieces["insert"]))
    if pieces["engine"] == "postgres":
        lines.append("                _key = _cursor.fetchone()[0]")
    else:
        lines.append("                _key = _cursor.lastrowid")
    lines.extend(
        [
            "                _inserted = True",
            "                self._cbcs_key = _key",
            "            else:",
            "                _sets = []",
            "                _params = []",
        ]
    )
    for field in writable:
        lines.extend(
            [
                "                if _fields.get(%s) != self._cbcs_saved_fields.get(%s):" % (_q(field.column), _q(field.column)),
                "                    _sets.append(%s)" % _q(pieces["assign"][field.column]),
                "                    _params.append(self._cbcs_bind(%s, _fields.get(%s)))" % (_q(field.column), _q(field.column)),
            ]
        )
    lines.extend(
        [
            "                if _sets:",
            "                    _params.append(self._cbcs_key)",
        ]
    )
    if check:
        lines.extend(
            [
                "                    if not _overwrite:",
                "                        _sql = %s + %s.join(_sets) + %s" % (_q(pieces["head"]), _q(", "), _q(pieces["tail"])),
            ]
        )
        for field in writable:
            lines.append("                        _params.append(self._cbcs_loaded.get(%s))" % _q(field.column))
        lines.extend(
            [
                "                    else:",
                "                        _sql = %s + %s.join(_sets) + %s" % (_q(pieces["head"]), _q(", "), _q(key_tail_only(pieces))),
            ]
        )
    else:
        lines.append(
            "                    _sql = %s + %s.join(_sets) + %s" % (_q(pieces["head"]), _q(", "), _q(key_tail_only(pieces)))
        )
    lines.extend(
        [
            "                    _cursor.execute(_sql, tuple(_params))",
            "                    if _cursor.rowcount == 0:",
            "                        _cursor.execute(%s, (self._cbcs_key,))" % _q(pieces["exists"]),
            "                        if _cursor.fetchone() is None:",
            "                            raise _CbcsStop(%s)" % _q("deleted"),
        ]
    )
    if check:
        lines.extend(
            [
                "                        if not _overwrite:",
                "                            raise _CbcsStop(%s)" % _q("conflict"),
            ]
        )
    lines.extend(
        [
            "                _key = self._cbcs_key",
            "            getattr(self, %s, lambda *a: None)(_conn, self._cbcs_key)" % _q("_cbcs_save_lines"),
            "            _cursor.execute(%s, (self._cbcs_key,))" % _q(pieces["load"]),
            "            _fetched = _cursor.fetchone()",
            "            if _fetched is None:",
            "                raise _CbcsStop(%s)" % _q("deleted"),
            "            _raw = {}",
        ]
    )
    for index, column in enumerate(pieces["load_columns"]):
        lines.append("            _raw[%s] = _fetched[%d]" % (_q(column), index))
    lines.extend(
        [
            "            self._cbcs_loaded = _raw",
            "            self._cbcs_fill_record(_raw)",
            "            self.cbcs_write_fields(_raw)",
            "            getattr(self, %s, lambda *a: None)(_conn, self._cbcs_key)" % _q("_cbcs_load_lines"),
            "        except _CbcsStop:",
            "            raise",
            "        except Exception as _error:",
            "            self._cbcs_show_db_error(_error)",
            "            raise _CbcsStop(%s)" % _q("db"),
        "except _CbcsStop as _stopped:",
        "    if _stopped.args and _stopped.args[0] == %s:" % _q("conflict"),
        "        return self._cbcs_conflict()",
        "    if _stopped.args and _stopped.args[0] == %s:" % _q("deleted"),
        "        self._cbcs_tell_deleted()",
        "        return False",
        "    return False",
        "self._cbcs_saved_fields = self.cbcs_read_fields()",
        "self._cbcs_ready = True",
        "self._cbcs_new = False",
        "if _inserted or not self._cbcs_filtered:",
        "    with cbcs_connections.work(%s) as _conn:" % _q(connection),
        "        _cursor = _conn.cursor()",
        "        _cursor.execute(%s)" % _q(pieces["keys"]),
        "        self._cbcs_keys = [_item[0] for _item in _cursor.fetchall()]",
        "    if _inserted:",
        "        self._cbcs_filtered = False",
        "if self._cbcs_key in self._cbcs_keys:",
        "    self._cbcs_index = self._cbcs_keys.index(self._cbcs_key)",
        ]
    )
    lines.extend(["    " + line if False else line for line in _call_event("cbcsOnAfterSave", False)])
    lines.extend(_call_hook(hooks.after_save, False))
    lines.extend(_call_hook(hooks.after_load, False))
    lines.extend(_refresh_call())
    lines.append("return True")
    return lines


def key_tail_only(pieces) -> str:
    # The checked tail starts with WHERE. The unchecked tail is the same WHERE without AND pieces.
    tail = pieces["tail"]
    marker = " AND "
    if marker in tail:
        return tail.split(marker, 1)[0]
    return tail


def _delete_body(pieces, connection, hooks) -> List[str]:
    lines = [
        "if self._cbcs_new or self._cbcs_key is None:",
        "    return False",
        "if not self._cbcs_ask_delete():",
        "    return False",
    ]
    lines.extend(_call_event("cbcsOnBeforeDelete", True))
    lines.extend(_call_hook(hooks.before_delete, True))
    lines.extend(
        [
            "import cbcs_connections",
            "_key = self._cbcs_key",
            "_index = self._cbcs_index",
            "try:",
            "    with cbcs_connections.work(%s) as _conn:" % _q(connection),
            "        _cursor = _conn.cursor()",
            "        try:",
            "            _cursor.execute(%s, (_key,))" % _q(pieces["delete"]),
            "        except Exception as _error:",
            "            self._cbcs_show_db_error(_error)",
            "            raise",
            "except Exception:",
            "    return False",
            "_kept = []",
            "for _item in self._cbcs_keys:",
            "    if _item != _key:",
            "        _kept.append(_item)",
            "self._cbcs_keys = _kept",
            "if _kept and _index < len(_kept):",
            "    self._cbcs_show(_index)",
            "elif _kept:",
            "    self._cbcs_show(len(_kept) - 1)",
            "else:",
            "    self._cbcs_start_new()",
        ]
    )
    lines.extend(_call_hook(hooks.after_delete, False))
    lines.append("return True")
    return lines


def _verb_new() -> List[str]:
    return [
        "if not self._cbcs_confirm_leave():",
        "    return",
        "self._cbcs_start_new()",
    ]


def _revert_body() -> List[str]:
    return [
        "if self._cbcs_new or self._cbcs_key is None:",
        "    self._cbcs_start_new()",
        "    return",
        "self._cbcs_show(self._cbcs_index)",
    ]


def _move_body(kind: str) -> List[str]:
    lines = [
        "if not self._cbcs_confirm_leave():",
        "    return",
    ]
    if kind == "first":
        lines.extend(["if self._cbcs_keys:", "    self._cbcs_show(0)"])
    elif kind == "last":
        lines.extend(["if self._cbcs_keys:", "    self._cbcs_show(len(self._cbcs_keys) - 1)"])
    elif kind == "previous":
        lines.extend(["if self._cbcs_index > 0:", "    self._cbcs_show(self._cbcs_index - 1)"])
    else:
        lines.extend(
            [
                "_index = self._cbcs_index",
                "_next = 0 if _index < 0 else _index + 1",
                "if _next < len(self._cbcs_keys):",
                "    self._cbcs_show(_next)",
            ]
        )
    return lines


def _find_body(pieces, connection) -> List[str]:
    count = len(pieces["search"])
    params = ", ".join(["_pattern"] * count) if count else ""
    lines = [
        "if not self._cbcs_confirm_leave():",
        "    return",
        "_text, _ok = QInputDialog.getText(self._form, %s, %s)" % (_q("Find"), _q("Find")),
        "if not _ok:",
        "    return",
        "if _text == %s:" % _q(""),
        "    self.cbcs_open(self._cbcs_key)",
        "    return",
        "_pattern = self._cbcs_like_pattern(_text)",
        "import cbcs_connections",
        "with cbcs_connections.work(%s) as _conn:" % _q(connection),
        "    _cursor = _conn.cursor()",
    ]
    if count:
        lines.append("    _cursor.execute(%s, (%s))" % (_q(pieces["find"]), params))
    else:
        lines.append("    _cursor.execute(%s)" % _q(pieces["find"]))
    lines.extend(
        [
            "    self._cbcs_keys = [_item[0] for _item in _cursor.fetchall()]",
            "self._cbcs_filtered = True",
            "self._cbcs_find_note(len(self._cbcs_keys))",
            "if self._cbcs_keys:",
            "    self._cbcs_show(0)",
            "else:",
            "    self._cbcs_key = None",
            "    self._cbcs_index = -1",
            "    self._cbcs_new = False",
            "    self._cbcs_record = {}",
            "    self.cbcs_write_fields({})",
            "    self._cbcs_saved_fields = self.cbcs_read_fields()",
            "    self._cbcs_ready = True",
        ]
    )
    return lines


def _show_all_body() -> List[str]:
    return [
        "if not self._cbcs_confirm_leave():",
        "    return",
        "_key = self._cbcs_key",
        "self.cbcs_open(_key)",
    ]


def _find_note_body() -> List[str]:
    return [
        "_label = getattr(self, %s, None)" % _q("findLabel"),
        "if _label is None or not hasattr(_label, %s):" % _q("setText"),
        "    return",
        "if _count is None:",
        "    _label.setText(%s)" % _q(""),
        "    return",
        "_label.setText(%s %% _count)" % _q("Showing %s matches. [Show all]"),
    ]


def _position_body() -> List[str]:
    return [
        "if getattr(self, %s, False):" % _q("_cbcs_new"),
        "    return 0",
        "_keys = getattr(self, %s, None)" % _q("_cbcs_keys"),
        "if not _keys:",
        "    return 0",
        "_index = getattr(self, %s, -1)" % _q("_cbcs_index"),
        "if _index < 0 or _index >= len(_keys):",
        "    return 0",
        "return _index + 1",
    ]


def _refresh_call() -> List[str]:
    return [
        "if hasattr(self, %s) and not getattr(self, %s, False):" % (_q("cbcs_refresh"), _q("_cbcs_refreshing")),
        "    self.cbcs_refresh()",
    ]


def _call_event(name: str, cancel: bool) -> List[str]:
    if cancel:
        return [
            "_event = getattr(self, %s, None)" % _q(name),
            "if _event is not None and _event() is False:",
            "    return False",
        ]
    return [
        "_event = getattr(self, %s, None)" % _q(name),
        "if _event is not None:",
        "    _event()",
    ]


def _call_hook(name: str, cancel: bool) -> List[str]:
    if not name or not compat.is_name(name):
        return []
    if cancel:
        return [
            "if hasattr(self._form, %s) and self._form.%s() is False:" % (_q(name), name),
            "    return False",
        ]
    return [
        "if hasattr(self._form, %s):" % _q(name),
        "    self._form.%s()" % name,
    ]


def _own_filter(form_param: str) -> List[str]:
    return [
        "class _CbcsCloseGuard(QObject):",
        "    def __init__(self, ui, form):",
        "        super().__init__(form)",
        "        self.ui = ui",
        "        form.installEventFilter(self)",
        "    def eventFilter(self, obj, event):",
        "        if event.type() == QEvent.Type.Close or (event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape and isinstance(obj, QDialog)):",
        "            if not self.ui._cbcs_confirm_leave():",
        "                if event.type() == QEvent.Type.Close:",
        "                    event.ignore()",
        "                return True",
        "        return False",
        "self._cbcs_close_guard = _CbcsCloseGuard(self, %s)" % form_param,
    ]


def _imports(fields: Sequence[_Field], own_filter: bool) -> List[Tuple[str, str]]:
    found = [
        ("PySide6.QtWidgets", "QMessageBox"),
        ("PySide6.QtWidgets", "QInputDialog"),
    ]
    families = {field.family for field in fields}
    ios = {field.io for field in fields}
    if "decimal" in families or "decimal" in ios:
        found.append(("decimal", "Decimal"))
    if "date" in families or "date" in ios:
        found.append(("datetime", "date"))
        found.append(("datetime", "datetime"))
        found.append(("PySide6.QtCore", "QDate"))
    if own_filter:
        found.extend(
            [
                ("PySide6.QtCore", "QObject"),
                ("PySide6.QtCore", "QEvent"),
                ("PySide6.QtCore", "Qt"),
                ("PySide6.QtWidgets", "QDialog"),
            ]
        )
    return found


def _open_line(open_at: Optional[str]) -> Optional[str]:
    if open_at in ("none", "nothing"):
        return None
    if open_at == "last":
        return "self._cbcs_open_last()"
    if open_at == "new":
        return "self._cbcs_open_new()"
    return "self.cbcs_open()"


def _closing_generates(doc: UiDocument) -> bool:
    from app.features.form_builder.engine.codegen.expanders.steps import _generates
    from app.features.form_builder.engine.logic.events_codec import read_list
    from app.features.form_builder.engine.logic.storage import signal_property

    root = doc.root.object_name
    if not isinstance(root, str) or not compat.is_name(root):
        return False
    entry = doc.root.prop(signal_property("closing"))
    if entry is None or not isinstance(entry.value, StringValue):
        return False
    return _generates(read_list(entry.value.text))


def _refresh_will_exist(doc: UiDocument, ctx: CodegenContext) -> bool:
    if not _mentions_form_or_record(doc):
        return False
    from app.features.form_builder.engine.logic.formula_env import env_for
    from app.features.form_builder.engine.logic.rules import rule_graph
    from app.features.form_builder.engine.ui4.defaults import QtClassTable

    graph = rule_graph(doc, env_for(doc, ctx.window, QtClassTable.shared()))
    return bool(graph.order())


def _mentions_form_or_record(doc: UiDocument) -> bool:
    for node in _widgets(doc):
        for key in FORMULA_KEYS:
            value = node.value(key)
            if isinstance(value, (StringValue, CStringValue)) and ("form." in value.text or "record." in value.text):
                return True
    return False


def _fields(doc: UiDocument, ctx: CodegenContext, source: RecordSource, engine: str) -> Tuple[_Field, ...]:
    table = _schema_table(doc, source)
    found = []
    for node in _widgets(doc):
        name = node.object_name or ""
        if name not in ctx.attribute_names or not compat.is_name(name):
            continue
        entry = node.prop("cbcsBind")
        if entry is None or not isinstance(entry.value, StringValue) or not entry.value.text.strip():
            continue
        column = read_bind(entry.value.text).column
        if not column:
            continue
        io = _WIDGET_IO.get(node.class_name or "")
        if io is None:
            continue
        mode = node.prop("cbcsBindMode")
        read_only = False
        if mode is not None and isinstance(mode.value, StringValue):
            read_only = read_bind_mode(mode.value.text).read_only
        calculated = False
        value = node.value("cbcsValue")
        if isinstance(value, (StringValue, CStringValue)) and value.text.strip():
            calculated = True
        family, nullable, points = _family(table, column, engine, io)
        found.append(
            _Field(
                name,
                io,
                column,
                family,
                nullable,
                not read_only and not calculated,
                column.replace("_", " "),
                points,
            )
        )
    return tuple(found)


def _family(table, column: str, engine: str, io: str) -> Tuple[str, bool, str]:
    widget_family = {"int": "int", "decimal": "decimal", "date": "date", "bool": "bool"}.get(io, "text")
    if table is None:
        return widget_family, True, ""
    for spec in table.columns:
        if spec.name != column:
            continue
        kind = describe(
            spec.type,
            engine=engine,
            column_name=spec.name,
            references_table=spec.references.table if spec.references is not None else "",
            nullable=spec.nullable,
        )
        points = spec.references.table if spec.references is not None else ""
        family = kind.direction or widget_family
        if io == "date" and family == "text":
            family = "date"
        return family, spec.nullable, points
    return widget_family, True, ""


def _schema_table(doc: UiDocument, source: RecordSource):
    from app.features.form_builder.engine.data.schema import schema_for

    schema = schema_for(doc, source.connection)
    if schema is None:
        return None
    for table in schema.tables:
        if table.name == source.table:
            return table
    return None


def _engine(ctx: CodegenContext, connection: str) -> str:
    root = _project_root(ctx.forms_dir)
    if root is None:
        return "sqlite"
    path = os.path.join(root, "connections.json")
    if not os.path.isfile(path):
        return "sqlite"
    try:
        from app.features.form_builder.engine.data.connections import read_connections

        handle = open(path, "r", encoding="utf-8")
        try:
            text = handle.read()
        finally:
            handle.close()
        found, _error = read_connections(text, project_root=root)
    except OSError:
        return "sqlite"
    if found is None:
        return "sqlite"
    for item in found.connections:
        if item.name == connection and item.engine in ("sqlite", "postgres"):
            return item.engine
    return "sqlite"


def _project_root(forms_dir: Optional[str]) -> Optional[str]:
    if not forms_dir:
        return None
    path = forms_dir
    for _step in range(4):
        if os.path.isfile(os.path.join(path, "connections.json")):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return forms_dir


def _source(doc: UiDocument) -> Optional[RecordSource]:
    root = getattr(doc, "root", None)
    prop = getattr(root, "prop", None)
    if not callable(prop):
        return None
    entry = prop("cbcsData")
    if entry is None or not isinstance(getattr(entry, "value", None), StringValue):
        return None
    text = entry.value.text
    if not text.strip():
        return None
    found = read_data(text).value
    if isinstance(found, RecordSource):
        return found
    return None


def _widgets(doc: UiDocument):
    try:
        return tuple(doc.iter_widgets())
    except Exception:
        return ()


def _q(text: str) -> str:
    return py_string(text)


EXPANDER = RecordExpander()
