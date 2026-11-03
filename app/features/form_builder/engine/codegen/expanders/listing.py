"""List screens (CONTRACTS.md section 19.1, order 430).

Search, the cutoff line, and ``cbcs_open_record``. SQL text comes from ``sql.py``.
"""

from __future__ import annotations

import os
from typing import Iterable, List, Optional, Sequence, Tuple, cast

from app.features.form_builder.engine.codegen.literals import py_string
from app.features.form_builder.engine.codegen.logic_hooks import (
    CodegenContext,
    Contribution,
    Method,
)
from app.features.form_builder.engine.data.listing import FILTER_SIGNAL, VALUE_READ
from app.features.form_builder.engine.data.source import ListSource, read_data
from app.features.form_builder.engine.data.sql import (
    IdentifierError,
    list_read,
    select_source_error,
)
from app.features.form_builder.engine.diagnostics import CODES, DiagnosticLocation, FormDiagnostic
from app.features.form_builder.engine.logic import compat
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import StringValue

import app.features.form_builder.engine.diagnostic_codes.fb3xx_data  # noqa: F401

class ListingExpander:
    expander_id = "listing"
    level = 4
    order = 430

    def contribute(self, doc: UiDocument, ctx: CodegenContext) -> Contribution:
        source = _source(doc)
        if source is None:
            return Contribution()
        engine, problem = _engine(ctx, source.connection)
        if engine is None:
            return Contribution(diagnostics=(_diagnostic(doc, problem or "FB301", name=source.connection),))
        sql_error = select_source_error(source.sql) if source.sql.strip() else None
        if sql_error:
            return Contribution(
                diagnostics=(_diagnostic(doc, "FB314", message=sql_error),),
                methods=(_method("cbcs_refresh_list", _refuse_body(sql_error)), _method("cbcs_open_record", ["return"], "which")),
                ordered_setup=((895, "self.cbcs_refresh_list()"),),
                needs_form=True,
            )
        search, filters = _usable(ctx, source)
        key = source.open.key if source.open is not None else ""
        try:
            made = list_read(
                engine,
                source.table,
                source.columns,
                source.sql,
                search,
                filters,
                source.order,
                source.limit,
                key,
            )
        except IdentifierError as exc:
            return Contribution(diagnostics=(_diagnostic(doc, "FB307", name=str(exc)),))
        except ValueError as exc:
            return Contribution(diagnostics=(_diagnostic(doc, "FB314", message=str(exc)),))
        table = _table_name(doc, ctx)
        open_stem = source.open.form if source.open is not None else ""
        methods = [
            _method("cbcs_refresh_list", _refresh_body(made, source.connection, source.limit)),
            _method("cbcs_open_record", _open_body(open_stem), "which"),
            _method("_cbcs_arm_list", _arm_body(ctx, source, table, filters)),
            _method("_cbcs_list_params", _params_body(ctx, source, search, filters)),
            _method("_cbcs_fill_list", _fill_body(made.columns, made.key, source.limit, table), "_fetched, _names, _count, _keep"),
            _method("_cbcs_selected_key", _selected_body(table)),
            _method("_cbcs_reselect", _reselect_body(table), "_key"),
            _method("_cbcs_ensure_limit_label", _label_body(table)),
            _method("_cbcs_list_failed", _failed_body(table), "_exc"),
            _method("_cbcs_after_record", ["self.cbcs_refresh_list()"]),
            _method("_cbcs_record_window", _window_body(open_stem)),
        ]
        if search:
            methods.append(_method("_cbcs_like_pattern", _pattern_body(), "_text"))
        return Contribution(
            imports=_imports(),
            methods=tuple(methods),
            ordered_setup=((895, "self._cbcs_arm_list()"), (895, "self.cbcs_refresh_list()")),
            needs_form=True,
        )


def _method(name: str, lines: Sequence[str], params: str = "") -> Method:
    return Method(name, "\n".join(lines), "cbcsData", params)


def _imports() -> Tuple[Tuple[str, str], ...]:
    return (
        ("PySide6.QtCore", "QTimer"),
        ("PySide6.QtCore", "Qt"),
        ("PySide6.QtGui", "QKeySequence"),
        ("PySide6.QtGui", "QShortcut"),
        ("PySide6.QtGui", "QStandardItem"),
        ("PySide6.QtGui", "QStandardItemModel"),
        ("PySide6.QtWidgets", "QAbstractItemView"),
        ("PySide6.QtWidgets", "QLabel"),
    )


def _refresh_body(made, connection: str, limit: Optional[int]) -> List[str]:
    del limit
    count_sql = py_string(made.total.text)
    rows_sql = py_string(made.rows.text)
    lines = [
        "_keep = self._cbcs_selected_key()",
        "_params = self._cbcs_list_params()",
        "try:",
        "    import cbcs_connections",
        "    with cbcs_connections.work(%s) as _conn:" % py_string(connection),
        "        _cursor = _conn.cursor()",
    ]
    lines.extend(_execute(count_sql, "        "))
    lines.extend(
        [
            "        _row = _cursor.fetchone()",
            "        _count = 0 if _row is None or _row[0] is None else int(_row[0])",
        ]
    )
    lines.extend(_execute(rows_sql, "        "))
    lines.extend(
        [
            "        _names = [(_item[0] if _item[0] is not None else %s) for _item in (_cursor.description or ())]" % py_string(""),
            "        _fetched = _cursor.fetchall()",
            "except Exception as _exc:",
            "    self._cbcs_list_failed(_exc)",
            "    return",
            "self._cbcs_fill_list(_fetched, _names, _count, _keep)",
        ]
    )
    return lines


def _execute(literal: str, indent: str) -> List[str]:
    return [
        "%sif _params:" % indent,
        "%s    _cursor.execute(%s, _params)" % (indent, literal),
        "%selse:" % indent,
        "%s    _cursor.execute(%s)" % (indent, literal),
    ]


def _refuse_body(message: str) -> List[str]:
    return [
        "self._cbcs_limit_label = getattr(self, %s, None)" % py_string("limitLabel"),
        "if self._cbcs_limit_label is None:",
        "    return",
        "self._cbcs_limit_label.setText(%s)" % py_string(message),
        "self._cbcs_limit_label.show()",
    ]


def _params_body(ctx: CodegenContext, source: ListSource, search: Sequence[str], filters: Sequence[str]) -> List[str]:
    lines = ["_values = []"]
    widget = source.search_field
    if search and widget and compat.is_name(widget):
        lines.extend(
            [
                "_text = self.%s.text() if hasattr(self, %s) else %s" % (widget, py_string(widget), py_string("")),
                "if _text:",
                "    _pattern = self._cbcs_like_pattern(_text)",
                "    _any = 0",
                "else:",
                "    _pattern = %s" % py_string("%"),
                "    _any = 1",
            ]
        )
        for _column in search:
            lines.append("_values.append(_pattern)")
        lines.append("_values.append(_any)")
    fields = {item.column: item.field for item in source.filters}
    for column in filters:
        lines.append("_raw = %s" % _value_expr(fields.get(column, ""), _class(ctx, fields.get(column, ""))))
        lines.append("_blank = _raw is None or _raw == %s" % py_string(""))
        lines.append("_values.append(None if _blank else _raw)")
        lines.append("_values.append(1 if _blank else 0)")
    lines.append("return tuple(_values)")
    return lines


def _pattern_body() -> List[str]:
    # Same escapes as like_pattern. The running form cannot import the engine.
    return [
        "_escaped = _text.replace(%s, %s).replace(%s, %s).replace(%s, %s)"
        % (py_string("\\"), py_string("\\\\"), py_string("%"), py_string("\\%"), py_string("_"), py_string("\\_")),
        "return %s + _escaped + %s" % (py_string("%"), py_string("%")),
    ]


def _fill_body(columns: Sequence[str], key: str, limit: Optional[int], table: str) -> List[str]:
    shown = ", ".join(py_string(column) for column in columns)
    lines = [
        "self._cbcs_ensure_limit_label()",
        "_table = getattr(self, %s, None)" % py_string(table),
        "if _table is None:",
        "    return",
        "_shown = (%s,)" % shown if columns else "_shown = ()",
        "_model = QStandardItemModel(self._form)",
        "_model.setHorizontalHeaderLabels(list(_shown))",
        "for _row in _fetched:",
        "    _mapped = {}",
        "    for _index, _name in enumerate(_names):",
        "        if _index < len(_row):",
        "            _mapped[_name] = _row[_index]",
        "    _items = []",
        "    for _column in _shown:",
        "        _value = _mapped.get(_column)",
        "        _items.append(QStandardItem(%s if _value is None else str(_value)))" % py_string(""),
        "    if not _items:",
        "        continue",
    ]
    if key:
        lines.append("    _items[0].setData(_mapped.get(%s), Qt.ItemDataRole.UserRole)" % py_string(key))
    lines.append("    _model.appendRow(_items)")
    lines.append("_table.setModel(_model)")
    if limit is None:
        lines.extend(
            [
                "self._cbcs_limit_label.setText(%s)" % py_string(""),
                "self._cbcs_limit_label.hide()",
            ]
        )
    else:
        lines.extend(
            [
                "if _count > %d:" % limit,
                "    self._cbcs_limit_label.setText(%s %% (format(%d, %s), format(_count, %s)))"
                % (
                    py_string("Showing the first %s of %s. Type more to narrow the list."),
                    limit,
                    py_string(","),
                    py_string(","),
                ),
                "    self._cbcs_limit_label.show()",
                "else:",
                "    self._cbcs_limit_label.setText(%s)" % py_string(""),
                "    self._cbcs_limit_label.hide()",
            ]
        )
    lines.append("self._cbcs_reselect(_keep)")
    return lines


def _selected_body(table: str) -> List[str]:
    return [
        "_table = getattr(self, %s, None)" % py_string(table),
        "if _table is None:",
        "    return None",
        "_model = _table.model()",
        "if _model is None:",
        "    return None",
        "_selection = _table.selectionModel()",
        "if _selection is None:",
        "    return None",
        "_picked = _selection.selectedRows()",
        "if not _picked:",
        "    return None",
        "_item = _model.item(_picked[0].row(), 0)",
        "if _item is None:",
        "    return None",
        "return _item.data(Qt.ItemDataRole.UserRole)",
    ]


def _reselect_body(table: str) -> List[str]:
    return [
        "if _key is None:",
        "    return",
        "_table = getattr(self, %s, None)" % py_string(table),
        "if _table is None or _table.model() is None:",
        "    return",
        "_model = _table.model()",
        "for _row in range(_model.rowCount()):",
        "    _item = _model.item(_row, 0)",
        "    if _item is not None and _item.data(Qt.ItemDataRole.UserRole) == _key:",
        "        _table.selectRow(_row)",
        "        return",
    ]


def _label_body(table: str) -> List[str]:
    return [
        "_label = getattr(self, %s, None)" % py_string("limitLabel"),
        "if _label is None:",
        "    _label = QLabel(self._form)",
        "    _label.setObjectName(%s)" % py_string("limitLabel"),
        "    self.limitLabel = _label",
        "    _table = getattr(self, %s, None)" % py_string(table),
        "    _parent = _table.parentWidget() if _table is not None else None",
        "    _layout = _parent.layout() if _parent is not None else None",
        "    if _layout is not None and _table is not None:",
        "        _index = _layout.indexOf(_table)",
        "        if _index >= 0:",
        "            _layout.insertWidget(_index, _label)",
        "_label.hide()",
        "self._cbcs_limit_label = _label",
    ]


def _failed_body(table: str) -> List[str]:
    return [
        "self._cbcs_ensure_limit_label()",
        "_text = str(_exc).strip().splitlines()",
        "_message = _text[0] if _text else %s" % py_string("Can't read the list."),
        "self._cbcs_limit_label.setText(_message)",
        "self._cbcs_limit_label.show()",
        "_table = getattr(self, %s, None)" % py_string(table),
        "if _table is not None:",
        "    _table.setModel(QStandardItemModel(self._form))",
    ]


def _arm_body(ctx: CodegenContext, source: ListSource, table: str, filters: Sequence[str]) -> List[str]:
    lines = [
        "self._cbcs_open_windows = {}",
        "self._cbcs_list_timer = QTimer(self._form)",
        "self._cbcs_list_timer.setSingleShot(True)",
        "self._cbcs_list_timer.setInterval(250)",
        "self._cbcs_list_timer.timeout.connect(self.cbcs_refresh_list)",
    ]
    search_name = source.search_field
    if search_name and _class(ctx, search_name) == "QLineEdit" and compat.is_name(search_name):
        lines.append(
            "if hasattr(self, %s):" % py_string(search_name)
        )
        lines.append(
            "    self.%s.textChanged.connect(lambda *_args: self._cbcs_list_timer.start())" % search_name
        )
    fields = {item.column: item.field for item in source.filters}
    for column in filters:
        widget = fields.get(column, "")
        signal = FILTER_SIGNAL.get(_class(ctx, widget), "")
        if widget and signal and compat.is_name(widget):
            lines.append("if hasattr(self, %s):" % py_string(widget))
            lines.append("    self.%s.%s.connect(lambda *_args: self._cbcs_list_timer.start())" % (widget, signal))
    lines.append("self._cbcs_ensure_limit_label()")
    if table and compat.is_name(table):
        lines.extend(
            [
                "_table = getattr(self, %s, None)" % py_string(table),
                "if _table is not None:",
                "    _table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)",
                "    _table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)",
                "    _table.doubleClicked.connect(lambda *_args: self.cbcs_open_record(%s))" % py_string("selected"),
                "    _return = QShortcut(QKeySequence(Qt.Key.Key_Return), _table)",
                "    _return.setContext(Qt.ShortcutContext.WidgetShortcut)",
                "    _return.activated.connect(lambda: self.cbcs_open_record(%s))" % py_string("selected"),
                "    _enter = QShortcut(QKeySequence(Qt.Key.Key_Enter), _table)",
                "    _enter.setContext(Qt.ShortcutContext.WidgetShortcut)",
                "    _enter.activated.connect(lambda: self.cbcs_open_record(%s))" % py_string("selected"),
                "    self._cbcs_list_shortcuts = (_return, _enter)",
            ]
        )
    return lines


def _open_body(stem: str) -> List[str]:
    if not stem or not compat.is_name(stem):
        return ["return"]
    return [
        "if which not in (%s, %s):" % (py_string("new"), py_string("selected")),
        "    return",
        "_key = None",
        "if which == %s:" % py_string("selected"),
        "    _key = self._cbcs_selected_key()",
        "    if _key is None:",
        "        return",
        "_window = self._cbcs_record_window()",
        "if _window is None:",
        "    return",
        "_ui = getattr(_window, %s, None)" % py_string("ui"),
        "if _ui is None:",
        "    return",
        "if which == %s:" % py_string("new"),
        "    _opener = getattr(_ui, %s, None)" % py_string("cbcs_new"),
        "    if _opener is None:",
        "        _opener = getattr(_ui, %s, None)" % py_string("_cbcs_start_new"),
        "    if _opener is not None:",
        "        _opener()",
        "elif hasattr(_ui, %s):" % py_string("cbcs_open"),
        "    _ui.cbcs_open(_key)",
        "try:",
        "    _visible = _window.isVisible()",
        "except RuntimeError:",
        "    return",
        "if _visible:",
        "    _window.raise_()",
        "    _window.activateWindow()",
        "    return",
        "if hasattr(_window, %s):" % py_string("exec"),
        "    _window.exec()",
        "else:",
        "    _window.show()",
        "    _window.raise_()",
        "    _window.activateWindow()",
    ]


def _window_body(stem: str) -> List[str]:
    if not stem or not compat.is_name(stem):
        return ["return None"]
    class_name = _window_class(stem)
    return [
        "_found = getattr(self, %s, None)" % py_string("_cbcs_open_windows"),
        "if _found is None:",
        "    self._cbcs_open_windows = {}",
        "    _found = self._cbcs_open_windows",
        "_window = _found.get(%s)" % py_string(stem),
        "if _window is not None:",
        "    try:",
        "        _window.isVisible()",
        "        return _window",
        "    except RuntimeError:",
        "        _window = None",
        "try:",
        "    from forms.%s_window import %s" % (stem, class_name),
        "except Exception as _exc:",
        "    self._cbcs_list_failed(_exc)",
        "    return None",
        "_window = %s(self._form)" % class_name,
        "_found[%s] = _window" % py_string(stem),
        "_done = getattr(_window, %s, None)" % py_string("finished"),
        "if _done is not None:",
        "    _done.connect(lambda *_args: self._cbcs_after_record())",
        "return _window",
    ]


def _window_class(stem: str) -> str:
    parts = [part for part in stem.split("_") if part]
    return "".join(part[:1].upper() + part[1:] for part in parts) + "Window"


def _usable(ctx: CodegenContext, source: ListSource) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    search_name = source.search_field
    search = source.search if search_name and _class(ctx, search_name) == "QLineEdit" else ()
    filters = []
    for item in source.filters:
        if _value_expr(item.field, _class(ctx, item.field)) != py_string(""):
            filters.append(item.column)
    return tuple(search), tuple(filters)


def _value_expr(widget: str, class_name: str) -> str:
    if not widget or not compat.is_name(widget):
        return py_string("")
    found = VALUE_READ.get(class_name)
    if found is None:
        return py_string("")
    getter, pattern = found
    if pattern:
        getter = "%s.toString(%s)" % (getter, py_string(pattern))
    return "self.%s.%s if hasattr(self, %s) else %s" % (widget, getter, py_string(widget), py_string(""))


def _source(doc: UiDocument) -> Optional[ListSource]:
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
    if isinstance(found, ListSource):
        return found
    return None


def _class(ctx: CodegenContext, name: str) -> str:
    facts = ctx.widgets.get(name)
    if facts is None:
        return ""
    return facts.class_name or ""


def _table_name(doc: UiDocument, ctx: CodegenContext) -> str:
    walk = getattr(doc, "iter_widgets", None)
    if not callable(walk):
        return ""
    for node in cast(Iterable[object], walk()):
        if (getattr(node, "class_name", "") or "") != "QTableView":
            continue
        name = getattr(node, "object_name", "") or ""
        if name and compat.is_name(name) and name in ctx.attribute_names:
            return name
    return ""


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


def _diagnostic(doc: UiDocument, code: str, message: str = "", **words: str) -> FormDiagnostic:
    info = CODES[code]
    text = message or (info.title.format(**words) if words else info.title)
    root = getattr(doc, "root", None)
    return FormDiagnostic(
        info.code,
        info.severity,
        text,
        DiagnosticLocation(
            getattr(root, "id", None) if isinstance(getattr(root, "id", None), int) else None,
            getattr(root, "object_name", None) or None,
            "cbcsData",
            ("cbcsData",),
        ),
        "codegen",
    )


EXPANDER = ListingExpander()
