"""Record navigation, save, and the unsaved-changes prompt (CONTRACTS.md section 19.5).

SQL text comes from ``engine.data.sql``. This module concatenates those pieces.
A form that is not a record source contributes nothing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

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
from app.features.form_builder.engine.data.types import describe, is_sqlite_rowid
from app.features.form_builder.engine.diagnostics import CODES, DiagnosticLocation, FormDiagnostic

import app.features.form_builder.engine.diagnostic_codes.fb3xx_data  # noqa: F401
from app.features.form_builder.engine.logic import compat
from app.features.form_builder.engine.logic.storage import FORMULA_KEYS
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import CStringValue, StringValue

_GUARD_ID = "record.leave"
# Lines inserted into cbcs_open after the key list is loaded, before the first show.
# Empty for a form with no lookup, so the generated text matches M8.2.
_OPEN_HOOKS = []
_WIDGET_IO = {
    "QLineEdit": "text",
    "QPlainTextEdit": "plain",
    "QTextEdit": "plain",
    "QSpinBox": "int",
    "QDoubleSpinBox": "decimal",
    "QDateEdit": "date",
    "QTimeEdit": "time",
    "QDateTimeEdit": "datetime",
    "QCheckBox": "bool",
    "QComboBox": "data",
}

_NULL_TEXT = " "


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
    error_label: str = ""
    item_data: bool = True
    lookup: bool = False


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


def register_open_hook(fn: Callable) -> None:
    """Add lines to ``cbcs_open`` after the key list loads. Idempotent."""

    if fn not in _OPEN_HOOKS:
        _OPEN_HOOKS.append(fn)


class RecordExpander:
    expander_id = "record"
    level = 4
    order = 400

    def contribute(self, doc: UiDocument, ctx: CodegenContext) -> Contribution:
        source = _source(doc)
        if source is None:
            return Contribution()
        engine, problem = _engine(ctx, source.connection)
        if engine is None:
            return Contribution(diagnostics=(_connection_diagnostic(doc, problem or "FB301", source.connection),))
        _install_guard()
        fields = _fields(doc, ctx, source, engine)
        record_word = source.record_word or singular(source.table)
        order = source.order or ((source.key, "asc"),)
        search = source.search or tuple(field.column for field in fields if field.family == "text" and field.writable)
        # The conflict clause stays on. "Keep mine" is a separate source setting.
        check = True
        allow_keep = bool(source.allow_overwrite or source.conflicts == "overwrite")
        hooks = source.hooks or Hooks()
        rowid = _uses_rowid(engine, _schema_table(doc, source), source.key, fields)
        has_lines = _has_lines(doc)
        prelude = []
        for fn in _OPEN_HOOKS:
            extra = fn(doc, ctx)
            if extra:
                prelude.extend(extra)
        also = _also_families(doc, ctx, engine)
        methods = _methods(
            source, fields, engine, record_word, order, search, check, hooks, allow_keep, rowid, has_lines, prelude, also
        )
        imports = _imports(fields, not _closing_generates(doc), also)
        setup: List[str] = []
        setup.extend(_null_markers(fields))
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


def _methods(source, fields, engine, record_word, order, search, check, hooks, allow_keep, rowid, has_lines: bool = False, prelude=(), also=()) -> List[Method]:
    noun = record_word
    table = source.table
    key = source.key
    connection = source.connection
    columns = tuple(field.column for field in fields)
    load_columns = columns if key in columns else columns + (key,)
    writable = tuple(field for field in fields if field.writable and field.column != key)
    # A typed key that is not the SQLite rowid alias belongs in the INSERT.
    typed_key = any(field.column == key and field.writable for field in fields) and not rowid
    insert_columns = ((key,) if typed_key else ()) + tuple(field.column for field in writable)
    pieces = _sql(engine, table, key, noun, order, search, load_columns, insert_columns, writable, check, rowid)
    bodies = {
        "cbcs_open": ("key=None", _open_body(pieces, connection, prelude)),
        "_cbcs_show": ("_index", _show_body(pieces, connection, fields, hooks)),
        "_cbcs_start_new": ("", _new_body(fields, hooks, has_lines)),
        "cbcs_read_fields": ("", _read_body(fields)),
        "cbcs_write_fields": ("_row", _write_body(fields)),
        "_cbcs_snapshot": ("", ["return getattr(self, %s, {})" % _q("_cbcs_saved_fields")]),
        "_cbcs_is_dirty": ("", _dirty_body(writable)),
        "_cbcs_bind": ("_column, _value", _bind_body(fields, engine)),
        "_cbcs_from": ("_column, _value", _from_body(fields, also)),
        "_cbcs_fill_record": ("_raw", _fill_body(load_columns)),
        "_cbcs_confirm_leave": ("", _confirm_body(noun)),
        "cbcs_confirm_leave": ("", ["return self._cbcs_confirm_leave()"]),
        "cbcs_is_dirty": ("", ["return self._cbcs_is_dirty()"]),
        "cbcs_current_key": ("", ["return getattr(self, %s, None)" % _q("_cbcs_key")]),
        "_cbcs_like_pattern": ("_text", _pattern_body()),
        "_cbcs_db_parts": ("_error", _db_parts_body()),
        "_cbcs_show_db_error": ("_error", _error_body(noun, fields)),
        "_cbcs_ask_delete": ("", _delete_ask_body(noun)),
        "_cbcs_tell_deleted": ("", _deleted_body(noun)),
        "_cbcs_clear_errors": ("", _clear_errors_body(fields)),
        "_cbcs_show_field": ("_widget, _label, _message", _show_field_body()),
        "_cbcs_conflict": ("", _conflict_body(noun, allow_keep)),
        "cbcs_save": ("", _save_body(hooks)),
        "_cbcs_write": ("_overwrite", _write_sql_body(pieces, connection, fields, writable, check, hooks)),
        "cbcs_delete": ("", _delete_body(pieces, connection, hooks, has_lines and source.delete_lines is not False)),
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


def _sql(engine, table, key, noun, order, search, load_columns, insert_columns, writable, check, rowid):
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
        "key": key,
        "rowid": bool(rowid),
    }


def _open_body(pieces, connection, prelude=()) -> List[str]:
    lines = [
        "import cbcs_connections",
        "with cbcs_connections.work(%s) as _conn:" % _q(connection),
        "    _cursor = _conn.cursor()",
        "    _cursor.execute(%s)" % _q(pieces["keys"]),
        "    self._cbcs_keys = [_item[0] for _item in _cursor.fetchall()]",
        "self._cbcs_filtered = False",
        "self._cbcs_find_note(None)",
    ]
    lines.extend(prelude)
    lines.extend(
        [
            "if key is not None and key in self._cbcs_keys:",
            "    self._cbcs_show(self._cbcs_keys.index(key))",
            "elif self._cbcs_keys:",
            "    self._cbcs_show(0)",
            "else:",
            "    self._cbcs_start_new()",
        ]
    )
    return lines


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
            "self._cbcs_clear_errors()",
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


def _new_body(fields, hooks, clear_lines: bool = False) -> List[str]:
    lines = [
        "self._cbcs_new = True",
        "self._cbcs_key = None",
        "self._cbcs_index = -1",
        "self._cbcs_loaded = {}",
        "self._cbcs_record = {}",
        "self._cbcs_clear_errors()",
        "self.cbcs_write_fields({})",
        "self._cbcs_saved_fields = self.cbcs_read_fields()",
    ]
    if clear_lines:
        lines.extend(
            [
                "_clear_lines = getattr(self, %s, None)" % _q("_cbcs_clear_lines"),
                "if _clear_lines is not None:",
                "    _clear_lines()",
            ]
        )
    lines.append("self._cbcs_ready = True")
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
        return _read_number(field, key, "int")
    elif field.io == "decimal":
        return _read_number(field, key, "Decimal(str(%s.value()))" % widget)
    elif field.io == "bool":
        return _read_bool(field, key)
    elif field.io == "date":
        return _read_date(field, key)
    elif field.io == "time":
        return _read_minimum(field, key, "%s.time()" % widget, "%s.minimumTime()" % widget, "%s.time().toPython()" % widget)
    elif field.io == "datetime":
        return _read_minimum(
            field,
            key,
            "%s.dateTime()" % widget,
            "%s.minimumDateTime()" % widget,
            "%s.dateTime().toPython()" % widget,
        )
    elif field.io == "data":
        if field.item_data:
            return ["%s = %s.currentData()" % (key, widget)]
        lines = ["_text = %s.currentText()" % widget]
    else:
        lines = ["_text = %s.text()" % widget]
    if field.family == "text" and field.nullable:
        lines.extend(["if _text == %s:" % _q(""), "    %s = None" % key, "else:", "    %s = _text" % key])
    else:
        lines.append("%s = _text" % key)
    return lines


def _read_number(field: _Field, key: str, expression: str) -> List[str]:
    widget = "self.%s" % field.widget
    if expression == "int":
        value = "int(%s.value())" % widget
    else:
        value = expression
    if not field.nullable:
        return ["%s = %s" % (key, value)]
    return [
        "if %s.value() == %s.minimum():" % (widget, widget),
        "    %s = None" % key,
        "else:",
        "    %s = %s" % (key, value),
    ]


def _read_bool(field: _Field, key: str) -> List[str]:
    widget = "self.%s" % field.widget
    if not field.nullable:
        return ["%s = True if %s.isChecked() else False" % (key, widget)]
    return [
        "_state = %s.checkState()" % widget,
        "if _state == Qt.CheckState.PartiallyChecked:",
        "    %s = None" % key,
        "else:",
        "    %s = True if %s.isChecked() else False" % (key, widget),
    ]


def _read_date(field: _Field, key: str) -> List[str]:
    widget = "self.%s" % field.widget
    lines = ["_day = %s.date()" % widget]
    if field.nullable:
        lines.extend(
            [
                "if _day == %s.minimumDate():" % widget,
                "    %s = None" % key,
                "elif _day.isValid():",
                "    %s = _day.toPython()" % key,
                "else:",
                "    %s = None" % key,
            ]
        )
        return lines
    return lines + [
        "if _day.isValid():",
        "    %s = _day.toPython()" % key,
        "else:",
        "    %s = None" % key,
    ]


def _read_minimum(field: _Field, key: str, current: str, minimum: str, value: str) -> List[str]:
    if not field.nullable:
        return ["%s = %s" % (key, value)]
    return [
        "if %s == %s:" % (current, minimum),
        "    %s = None" % key,
        "else:",
        "    %s = %s" % (key, value),
    ]


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
    if field.io == "int":
        lines.extend(_write_number(widget, "int(_value)", field.nullable))
    elif field.io == "decimal":
        lines.extend(_write_number(widget, "float(_value)", field.nullable))
    elif field.io == "bool":
        lines.extend(_write_bool(widget, field.nullable))
    elif field.io == "date":
        lines.extend(_write_date(widget, field.nullable))
    elif field.io == "time":
        lines.extend(_write_time(widget, field.nullable))
    elif field.io == "datetime":
        lines.extend(_write_datetime(widget, field.nullable))
    elif field.io == "data":
        lines.extend(_write_combo(field.widget, field.item_data, field.lookup))
    else:
        lines.append("    %s.setText(%s if _value is None else str(_value))" % (widget, _q("")))
    lines.extend(["finally:", "    %s.blockSignals(False)" % widget])
    return lines


def _write_number(widget: str, cast: str, nullable: bool) -> List[str]:
    if nullable:
        blank = "        %s.setValue(%s.minimum())" % (widget, widget)
    elif cast.startswith("int"):
        blank = "        %s.setValue(0)" % widget
    else:
        blank = "        %s.setValue(0.0)" % widget
    return [
        "    if _value is None or _value == %s:" % _q(""),
        blank,
        "    else:",
        "        %s.setValue(%s)" % (widget, cast),
    ]


def _write_bool(widget: str, nullable: bool) -> List[str]:
    if not nullable:
        return ["    %s.setChecked(True if _value else False)" % widget]
    return [
        "    if _value is None:",
        "        %s.setCheckState(Qt.CheckState.PartiallyChecked)" % widget,
        "    else:",
        "        %s.setChecked(True if _value else False)" % widget,
    ]


def _write_date(widget: str, nullable: bool) -> List[str]:
    blank = "        %s.setDate(%s.minimumDate())" % (widget, widget) if nullable else "        %s.setDate(%s.minimumDate())" % (widget, widget)
    return [
        "    if _value is None or _value == %s:" % _q(""),
        blank,
        "    elif isinstance(_value, datetime):",
        "        _day = _value.date()",
        "        %s.setDate(QDate(_day.year, _day.month, _day.day))" % widget,
        "    elif isinstance(_value, date):",
        "        %s.setDate(QDate(_value.year, _value.month, _value.day))" % widget,
        "    else:",
        "        _day = date.fromisoformat(str(_value)[:10])",
        "        %s.setDate(QDate(_day.year, _day.month, _day.day))" % widget,
    ]


def _write_time(widget: str, nullable: bool) -> List[str]:
    return [
        "    if _value is None or _value == %s:" % _q(""),
        "        %s.setTime(%s.minimumTime())" % (widget, widget) if nullable else "        %s.setTime(QTime(0, 0, 0))",
        "    else:",
        "        if isinstance(_value, datetime):",
        "            _clock = _value.time()",
        "        elif isinstance(_value, time):",
        "            _clock = _value",
        "        else:",
        "            _clock = time.fromisoformat(str(_value))",
        "        %s.setTime(QTime(_clock.hour, _clock.minute, _clock.second, _clock.microsecond // 1000))" % widget,
    ]


def _write_datetime(widget: str, nullable: bool) -> List[str]:
    blank = (
        "        %s.setDateTime(%s.minimumDateTime())" % (widget, widget)
        if nullable
        else "        %s.setDateTime(QDateTime(QDate(2000, 1, 1), QTime(0, 0, 0)))" % widget
    )
    return [
        "    if _value is None or _value == %s:" % _q(""),
        blank,
        "    else:",
        "        if isinstance(_value, datetime):",
        "            _stamp = _value",
        "        elif isinstance(_value, date):",
        "            _stamp = datetime(_value.year, _value.month, _value.day)",
        "        else:",
        "            _stamp = datetime.fromisoformat(str(_value).replace(%s, %s))" % (_q("T"), _q(" ")),
        "        _clock = _stamp.time()",
        "        %s.setDateTime(QDateTime(QDate(_stamp.year, _stamp.month, _stamp.day), QTime(_clock.hour, _clock.minute, _clock.second, _clock.microsecond // 1000)))" % widget,
    ]


def _write_combo(name: str, item_data: bool, lookup: bool = False) -> List[str]:
    widget = "self.%s" % name
    if lookup:
        return ["    self._cbcs_select_lookup(%s, _value)" % _q(name)]
    if item_data:
        return [
            "    _picked = -1",
            "    _i = 0",
            "    while _i < %s.count():" % widget,
            "        if %s.itemData(_i) == _value:" % widget,
            "            _picked = _i",
            "            break",
            "        _i = _i + 1",
            "    %s.setCurrentIndex(_picked)" % widget,
        ]
    return [
        "    if _value is None:",
        "        %s.setCurrentIndex(-1)" % widget,
        "    else:",
        "        _picked = %s.findText(str(_value))" % widget,
        "        if _picked < 0:",
        "            %s.setCurrentText(str(_value))" % widget,
        "        else:",
        "            %s.setCurrentIndex(_picked)" % widget,
    ]


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
    if family == "time":
        return _bind_clock(engine, "time")
    if family == "datetime":
        return _bind_clock(engine, "datetime")
    return ["return _value"]


def _bind_clock(engine: str, family: str) -> List[str]:
    lines = [
        "if _value is None or _value == %s:" % _q(""),
        "    return None",
    ]
    if family == "time":
        lines.extend(
            [
                "if isinstance(_value, datetime):",
                "    _clock = _value.time()",
                "elif isinstance(_value, time):",
                "    _clock = _value",
                "else:",
                "    _clock = time.fromisoformat(str(_value))",
            ]
        )
        if engine == "postgres":
            lines.append("return _clock")
        else:
            lines.append("return _clock.isoformat()")
        return lines
    lines.extend(
        [
            "if isinstance(_value, datetime):",
            "    _stamp = _value",
            "elif isinstance(_value, date):",
            "    _stamp = datetime(_value.year, _value.month, _value.day)",
            "else:",
            "    _stamp = datetime.fromisoformat(str(_value).replace(%s, %s))" % (_q("T"), _q(" ")),
        ]
    )
    if engine == "postgres":
        lines.append("return _stamp")
    else:
        lines.append("return _stamp.isoformat(sep=%s)" % _q(" "))
    return lines


def _from_body(fields: Sequence[_Field], extras: Sequence[Tuple[str, str]] = ()) -> List[str]:
    lines = []
    first = True
    seen = set()
    pairs = [(field.column, field.family) for field in fields]
    pairs.extend(extras)
    for column, family in pairs:
        if column in seen:
            continue
        seen.add(column)
        word = "if" if first else "elif"
        first = False
        lines.append("%s _column == %s:" % (word, _q(column)))
        for line in _from_family(family):
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
    if family == "time":
        return [
            "if _value is None or _value == %s:" % _q(""),
            "    return None",
            "if isinstance(_value, datetime):",
            "    return _value.time()",
            "if isinstance(_value, time):",
            "    return _value",
            "return time.fromisoformat(str(_value))",
        ]
    if family == "datetime":
        return [
            "if _value is None or _value == %s:" % _q(""),
            "    return None",
            "if isinstance(_value, datetime):",
            "    return _value",
            "if isinstance(_value, date):",
            "    return datetime(_value.year, _value.month, _value.day)",
            "return datetime.fromisoformat(str(_value).replace(%s, %s))" % (_q("T"), _q(" ")),
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
    labels = ", ".join("%s: %s" % (_q(field.column), _q(field.display)) for field in fields)
    widgets = ", ".join("%s: self.%s" % (_q(field.column), field.widget) for field in fields)
    marks = ", ".join(
        "%s: self.%s" % (_q(field.column), field.error_label) for field in fields if field.error_label
    )
    points = ", ".join("%s: %s" % (_q(field.column), _q(field.points_to)) for field in fields if field.points_to)
    unique = "Another %s already uses this %%s." % noun
    required = "%s is required."
    points_to = "%s must be one of the %s records."
    return [
        "self._cbcs_clear_errors()",
        "_state, _column, _detail, _constraint, _text = self._cbcs_db_parts(_error)",
        "_labels = {%s}" % labels,
        "_widgets = {%s}" % widgets,
        "_marks = {%s}" % marks,
        "_points = {%s}" % points,
        "if _column not in _labels:",
        "    _best = %s" % _q(""),
        "    for _name in _labels:",
        "        if _name and _constraint and _name in _constraint and len(_name) > len(_best):",
        "            _best = _name",
        "    _column = _best",
        "_label = _labels.get(_column, %s)" % _q(""),
        "_table = _points.get(_column, %s)" % _q(""),
        "_mapped = %s" % _q(""),
        "if _label and (_state == %s or %s in _text):" % (_q("23505"), _q("UNIQUE constraint failed")),
        "    _mapped = %s %% (_label[:1].lower() + _label[1:])" % _q(unique),
        "elif _label and (_state == %s or %s in _text):" % (_q("23502"), _q("NOT NULL constraint failed")),
        "    _mapped = %s %% _label" % _q(required),
        "elif _label and _state == %s:" % _q("23503"),
        "    _mapped = %s %% (_label, _table or %s)" % (_q(points_to), _q("related")),
        "if _mapped:",
        "    _widget = _widgets.get(_column)",
        "    _mark = _marks.get(_column)",
        "    if _widget is not None and _mark is not None:",
        "        self._cbcs_show_field(_widget, _mark, _mapped)",
        "        _widget.setFocus()",
        "        return",
        "    QMessageBox.warning(self._form, %s, _mapped)" % _q(""),
        "    return",
        "if not _text:",
        "    return",
        "QMessageBox.warning(self._form, %s, _text)" % _q(""),
    ]


def _db_parts_body() -> List[str]:
    return [
        "_text = %s" % _q(""),
        "_state = %s" % _q(""),
        "_column = %s" % _q(""),
        "_detail = %s" % _q(""),
        "_constraint = %s" % _q(""),
        "_args = getattr(_error, %s, ())" % _q("args"),
        "_payload = _args[0] if _args else None",
        "if isinstance(_payload, dict):",
        "    _state = _payload.get(%s) or %s" % (_q("C"), _q("")),
        "    _column = _payload.get(%s) or %s" % (_q("c"), _q("")),
        "    _detail = _payload.get(%s) or %s" % (_q("D"), _q("")),
        "    _constraint = _payload.get(%s) or %s" % (_q("n"), _q("")),
        "    _text = _payload.get(%s) or %s" % (_q("M"), _q("")),
        "    if not isinstance(_state, str):",
        "        _state = str(_state or %s)" % _q(""),
        "    if not isinstance(_column, str):",
        "        _column = %s" % _q(""),
        "    if not isinstance(_detail, str):",
        "        _detail = %s" % _q(""),
        "    if not isinstance(_constraint, str):",
        "        _constraint = %s" % _q(""),
        "    if not isinstance(_text, str):",
        "        _text = %s" % _q(""),
        "if not _state:",
        "    for _attr in (%s, %s):" % (_q("sqlstate"), _q("pgcode")),
        "        _value = getattr(_error, _attr, None)",
        "        if isinstance(_value, str) and _value:",
        "            _state = _value",
        "_diag = getattr(_error, %s, None)" % _q("diag"),
        "if _diag is not None:",
        "    if not _state:",
        "        _value = getattr(_diag, %s, None)" % _q("sqlstate"),
        "        if isinstance(_value, str) and _value:",
        "            _state = _value",
        "    if not _column:",
        "        _value = getattr(_diag, %s, None)" % _q("column_name"),
        "        if isinstance(_value, str) and _value:",
        "            _column = _value",
        "    if not _detail:",
        "        _value = getattr(_diag, %s, None)" % _q("message_detail"),
        "        if isinstance(_value, str) and _value:",
        "            _detail = _value",
        "    if not _constraint:",
        "        _value = getattr(_diag, %s, None)" % _q("constraint_name"),
        "        if isinstance(_value, str) and _value:",
        "            _constraint = _value",
        "    if not _text:",
        "        _value = getattr(_diag, %s, None)" % _q("message_primary"),
        "        if isinstance(_value, str) and _value:",
        "            _text = _value",
        "if not _text:",
        "    _shown = str(_error)",
        "    if not (_shown[:1] == %s and _shown[-1:] == %s):" % (_q("{"), _q("}")),
        "        _text = _shown",
        "if not _column and %s in _text:" % _q("constraint failed:"),
        "    _tail = _text.split(%s, 1)[1].strip()" % _q("constraint failed:"),
        "    if %s in _tail and %s not in _text:" % (_q("."), _q("FOREIGN KEY constraint failed")),
        "        _column = _tail.split(%s)[-1].strip().strip(%s)" % (_q("."), _q("'\"")),
        "if not _column and %s in _detail:" % _q("Key ("),
        "    _inside = _detail.split(%s, 1)[1]" % _q("Key ("),
        "    _column = _inside.split(%s, 1)[0].strip().strip(%s)" % (_q(")"), _q('"')),
        "return (_state, _column, _detail, _constraint, _text)",
    ]


def _clear_errors_body(fields: Sequence[_Field]) -> List[str]:
    lines = []
    for field in fields:
        widget = "self.%s" % field.widget
        lines.append("%s.setToolTip(%s)" % (widget, _q("")))
        lines.append("if %s.property(%s):" % (widget, _q("cbcsInvalid")))
        lines.append("    %s.setProperty(%s, False)" % (widget, _q("cbcsInvalid")))
        if field.error_label:
            label = "self.%s" % field.error_label
            lines.append("%s.setText(%s)" % (label, _q("")))
            lines.append("%s.setVisible(False)" % label)
    if not lines:
        lines.append("return None")
    return lines


def _show_field_body() -> List[str]:
    return [
        "if _label is not None:",
        "    _label.setText(_message)",
        "    _label.setVisible(True if _message else False)",
        "_widget.setToolTip(_message)",
        "_showing = True if _message else False",
        "if _widget.property(%s) != _showing:" % _q("cbcsInvalid"),
        "    _widget.setProperty(%s, _showing)" % _q("cbcsInvalid"),
        "    _style = _widget.style()",
        "    _style.unpolish(_widget)",
        "    _style.polish(_widget)",
    ]


def _below_minimum(widget: str, io: str) -> List[str]:
    if io == "int":
        return [
            "if %s.minimum() > -2147483648:" % widget,
            "    %s.setMinimum(%s.minimum() - 1)" % (widget, widget),
        ]
    if io == "decimal":
        return ["%s.setMinimum(%s.minimum() - %s.singleStep())" % (widget, widget, widget)]
    if io == "date":
        return ["%s.setMinimumDate(%s.minimumDate().addDays(-1))" % (widget, widget)]
    if io == "datetime":
        return ["%s.setMinimumDateTime(%s.minimumDateTime().addSecs(-1))" % (widget, widget)]
    # QTime can't go below 00:00:00, so a nullable time keeps midnight as its blank.
    return []


def _null_markers(fields: Sequence[_Field]) -> List[str]:
    lines = []
    for field in fields:
        widget = "self.%s" % field.widget
        if field.nullable and field.io in ("int", "decimal", "date", "time", "datetime"):
            # Blank sits one step below the designed minimum, so every real value stays saveable.
            lines.extend(_below_minimum(widget, field.io))
            lines.append("%s.setSpecialValueText(%s)" % (widget, _q(_NULL_TEXT)))
        if field.nullable and field.io == "bool":
            lines.append("%s.setTristate(True)" % widget)
        if field.error_label:
            lines.append("self.%s.setVisible(False)" % field.error_label)
    return lines


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
        "_db_error = None",
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
    elif pieces["rowid"]:
        lines.append("                _key = _cursor.lastrowid")
    else:
        lines.append(
            "                _key = self._cbcs_bind(%s, _fields.get(%s))" % (_q(pieces["key"]), _q(pieces["key"]))
        )
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
            "            _db_error = _error",
            "            raise",
        "except _CbcsStop as _stopped:",
        "    if _stopped.args and _stopped.args[0] == %s:" % _q("conflict"),
        "        return self._cbcs_conflict()",
        "    if _stopped.args and _stopped.args[0] == %s:" % _q("deleted"),
        "        self._cbcs_tell_deleted()",
        "        return False",
        "    return False",
        "except Exception as _error:",
        "    self._cbcs_show_db_error(_db_error if _db_error is not None else _error)",
        "    return False",
        "self._cbcs_clear_errors()",
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


def _delete_body(pieces, connection, hooks, delete_children: bool = False) -> List[str]:
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
        ]
    )
    if delete_children:
        lines.extend(
            [
                "        _drop_lines = getattr(self, %s, None)" % _q("_cbcs_delete_lines"),
                "        if _drop_lines is not None:",
                "            _drop_lines(_conn, _key)",
            ]
        )
    lines.extend(
        [
            "        _cursor.execute(%s, (_key,))" % _q(pieces["delete"]),
            "except Exception as _error:",
            "    self._cbcs_show_db_error(_error)",
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
    if count == 1:
        lines.append("    _cursor.execute(%s, (_pattern,))" % _q(pieces["find"]))
    elif count:
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


def _imports(fields: Sequence[_Field], own_filter: bool, extras: Sequence[Tuple[str, str]] = ()) -> List[Tuple[str, str]]:
    found = [
        ("PySide6.QtWidgets", "QMessageBox"),
        ("PySide6.QtWidgets", "QInputDialog"),
    ]
    families = {field.family for field in fields}
    families.update(family for _name, family in extras)
    ios = {field.io for field in fields}
    if "decimal" in families or "decimal" in ios:
        found.append(("decimal", "Decimal"))
    if families.intersection(("date", "time", "datetime")) or ios.intersection(("date", "time", "datetime")):
        found.append(("datetime", "date"))
        found.append(("datetime", "datetime"))
        found.append(("datetime", "time"))
    if "date" in families or "date" in ios:
        found.append(("PySide6.QtCore", "QDate"))
    if "time" in families or "time" in ios:
        found.append(("PySide6.QtCore", "QTime"))
    if "datetime" in families or "datetime" in ios:
        found.append(("PySide6.QtCore", "QDate"))
        found.append(("PySide6.QtCore", "QTime"))
        found.append(("PySide6.QtCore", "QDateTime"))
    if any(field.nullable and field.io == "bool" for field in fields):
        found.append(("PySide6.QtCore", "Qt"))
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
    from app.features.form_builder.engine.codegen.lookup_plan import lookup_names

    lookups = set(lookup_names(doc, ctx.attribute_names))
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
        family, nullable, points, kind_read_only, json_column = _family(table, column, engine, io)
        mode = node.prop("cbcsBindMode")
        if mode is not None and isinstance(mode.value, StringValue):
            read_only = read_bind_mode(mode.value.text).read_only
        else:
            read_only = kind_read_only
        if json_column:
            read_only = True
        calculated = False
        value = node.value("cbcsValue")
        if isinstance(value, (StringValue, CStringValue)) and value.text.strip():
            calculated = True
        is_lookup = io == "data" and name in lookups
        item_data = True if is_lookup else (_combo_has_data(node) if io == "data" else True)
        found.append(
            _Field(
                name,
                io,
                column,
                family,
                nullable,
                not read_only and not calculated,
                _display(doc, name),
                points,
                _error_label_name(node, ctx),
                item_data,
                is_lookup,
            )
        )
    return tuple(found)


def _family(table, column: str, engine: str, io: str) -> Tuple[str, bool, str, bool, bool]:
    widget_family = {
        "int": "int",
        "decimal": "decimal",
        "date": "date",
        "time": "time",
        "datetime": "datetime",
        "bool": "bool",
    }.get(io, "text")
    if table is None:
        return widget_family, True, "", False, False
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
        if io in ("date", "time", "datetime") and family == "text":
            family = io
        base = spec.type.strip().lower().split("(", 1)[0].strip()
        return family, spec.nullable, points, bool(kind.read_only), base in ("json", "jsonb")
    return widget_family, True, "", False, False


def _also_families(doc: UiDocument, ctx: CodegenContext, engine: str) -> List[Tuple[str, str]]:
    """Also columns whose schema type ``_cbcs_from`` should convert. Unknown columns stay raw."""

    from app.features.form_builder.engine.codegen.lookup_plan import lookup_plans
    from app.features.form_builder.engine.data.schema import schema_for

    plans = lookup_plans(doc, ctx.attribute_names)
    source = _source(doc)
    connection = plans[0].connection if plans else (source.connection if source is not None else "")
    if not connection:
        return []
    schema = schema_for(doc, connection)
    found: List[Tuple[str, str]] = []
    seen = set()
    for plan in plans:
        columns = {}
        if schema is not None:
            for table in schema.tables:
                if table.name == plan.table:
                    columns = {column.name: column for column in table.columns}
                    break
        for name in plan.also:
            _remember_also(found, seen, columns, name, engine)
    from app.features.form_builder.engine.data.source import DataColumn, read_rows

    try:
        nodes = tuple(doc.iter_widgets())
    except Exception:
        nodes = ()
    for node in nodes:
        prop = getattr(node, "prop", None)
        entry = prop("cbcsRows") if callable(prop) else None
        value = getattr(entry, "value", None)
        text = getattr(value, "text", "")
        if not isinstance(text, str) or not text.strip():
            continue
        rows, error = read_rows(text)
        if error is not None or rows is None:
            continue
        line_columns = {}
        wanted = {item.lookup.table for item in rows.columns if isinstance(item, DataColumn) and item.lookup is not None}
        if schema is not None:
            for table in schema.tables:
                if table.name in wanted:
                    line_columns[table.name] = {column.name: column for column in table.columns}
        for item in rows.columns:
            if not isinstance(item, DataColumn) or item.lookup is None:
                continue
            columns = line_columns.get(item.lookup.table, {})
            for name in item.lookup.also:
                _remember_also(found, seen, columns, name, engine)
    return found


def _remember_also(found: List[Tuple[str, str]], seen: set, columns: dict, name: str, engine: str) -> None:
    from app.features.form_builder.engine.data.types import describe

    if name in seen or name not in columns:
        return
    seen.add(name)
    column = columns[name]
    kind = describe(
        column.type,
        engine=engine if engine in ("sqlite", "postgres") else "sqlite",
        column_name=name,
        nullable=column.nullable,
    )
    found.append((name, kind.direction or "text"))


def _schema_table(doc: UiDocument, source: RecordSource):
    from app.features.form_builder.engine.data.schema import schema_for

    schema = schema_for(doc, source.connection)
    if schema is None:
        return None
    for table in schema.tables:
        if table.name == source.table:
            return table
    return None


def _engine(ctx: CodegenContext, connection: str) -> Tuple[Optional[str], Optional[str]]:
    root = _project_root(ctx.forms_dir)
    if root is None:
        return None, "FB301"
    path = os.path.join(root, "connections.json")
    if not os.path.isfile(path):
        return None, "FB301"
    try:
        from app.features.form_builder.engine.data.connections import read_connections

        handle = open(path, "r", encoding="utf-8")
        try:
            text = handle.read()
        finally:
            handle.close()
        found, _error = read_connections(text, project_root=root)
    except OSError:
        return None, "FB302"
    if found is None:
        return None, "FB302"
    for item in found.connections:
        if item.name == connection and item.engine in ("sqlite", "postgres"):
            return item.engine, None
    return None, "FB301"


def _uses_rowid(engine: str, table, key: str, fields: Sequence[_Field]) -> bool:
    if engine != "sqlite":
        return False
    key_field = next((field for field in fields if field.column == key and field.writable), None)
    if table is None:
        if key_field is not None and key_field.io not in ("int",):
            return False
        return True
    for spec in table.columns:
        if spec.name != key:
            continue
        return is_sqlite_rowid(spec.type, without_rowid=bool(getattr(table, "without_rowid", False)))
    return key_field is None


def _connection_diagnostic(doc: UiDocument, code: str, name: str) -> FormDiagnostic:
    info = CODES[code]
    title = info.title
    message = title.format(name=name) if "{name}" in title else title
    root = doc.root
    return FormDiagnostic(
        code=info.code,
        severity=info.severity,
        message=message,
        location=DiagnosticLocation(
            node_id=getattr(root, "id", None),
            object_name=getattr(root, "object_name", None),
            property="cbcsData",
        ),
        source="codegen",
    )


def _display(doc: UiDocument, name: str) -> str:
    from app.features.form_builder.engine.query.tab_stops import display_name

    text = display_name(doc, name)
    if text.endswith(":"):
        text = text[:-1].rstrip()
    return text or name


def _combo_has_data(node) -> bool:
    """True when a combo item carries a value other than its visible text."""

    try:
        items = node.children("items")
    except Exception:
        return False
    for item in items:
        try:
            props = item.properties()
        except Exception:
            continue
        for entry in props:
            if getattr(entry, "name", "") != "text":
                return True
    return False


def _error_label_name(node, ctx: CodegenContext) -> str:
    value = node.value("cbcsErrorLabel")
    if not isinstance(value, StringValue):
        return ""
    name = value.text.strip()
    if name and compat.is_name(name) and name in ctx.attribute_names:
        return name
    return ""


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


def _has_lines(doc: UiDocument) -> bool:
    """True when a widget carries a lines grid. Delete and New stay quiet without one."""

    walk = getattr(doc, "iter_widgets", None)
    if not callable(walk):
        return False
    try:
        nodes = tuple(walk())
    except Exception:
        return False
    for node in nodes:
        prop = getattr(node, "prop", None)
        if not callable(prop):
            continue
        entry = prop("cbcsRows")
        value = getattr(entry, "value", None)
        text = getattr(value, "text", "")
        if isinstance(text, str) and text.strip():
            return True
    return False


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
