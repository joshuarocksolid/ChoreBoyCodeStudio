"""Lookup combos (CONTRACTS.md section 19.1, order 380).

One SELECT fills each combo. The key is the item's data. Also columns sit on
``_CBCS_ALSO_ROLE`` (Qt user role 256, plus one). A missing key stays visible
as ``(unknown #…)`` so the record still round-trips.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from app.features.form_builder.engine.codegen.literals import py_string
from app.features.form_builder.engine.codegen.logic_hooks import CodegenContext, Contribution, Method
from app.features.form_builder.engine.codegen.lookup_plan import LookupPlan, also_indexes, lookup_plans, select_columns
from app.features.form_builder.engine.data.source import singular
from app.features.form_builder.engine.data.sql import IdentifierError, select_lookup
from app.features.form_builder.engine.ui4.document import UiDocument

# Qt.ItemDataRole.UserRole is 256. The next role holds the also dict.
_ALSO_ROLE = 257


class LookupsExpander:
    expander_id = "lookups"
    level = 3
    order = 380

    def contribute(self, doc: UiDocument, ctx: CodegenContext) -> Contribution:
        plans = lookup_plans(doc, ctx.attribute_names)
        if not plans:
            if _refresh_requested(doc) or _lines_present(doc):
                body = "\n".join(_line_reload_lines()) if _lines_present(doc) else "return None"
                return Contribution(
                    methods=(Method("cbcs_load_lookups", body, "cbcsLookup", params="fields=None"),)
                )
            return Contribution()
        from app.features.form_builder.engine.codegen.expanders.record import _engine

        engine, _problem = _engine(ctx, plans[0].connection)
        if engine is None:
            return Contribution()
        ready = []
        for plan in plans:
            try:
                statement = select_lookup(
                    engine,
                    plan.table,
                    plan.key,
                    plan.show,
                    plan.also,
                    plan.order,
                )
            except IdentifierError:
                continue
            columns = _select_columns(plan)
            ready.append((plan, statement.text, columns.index(plan.show), _also_indexes(plan, columns)))
        if not ready:
            if _lines_present(doc):
                return Contribution(
                    methods=(
                        Method(
                            "cbcs_load_lookups",
                            "\n".join(_line_reload_lines()),
                            "cbcsLookup",
                            params="fields=None",
                        ),
                    )
                )
            return Contribution()
        imports: List[Tuple[str, str]] = []
        if any(plan.editable for plan, _sql, _show_at, _index in ready):
            imports.append(("PySide6.QtWidgets", "QCompleter"))
            imports.append(("PySide6.QtCore", "Qt"))
        tables = ", ".join(
            "%s: %s" % (py_string(plan.widget), py_string(plan.table)) for plan, _sql, _show_at, _index in ready
        )
        body = [
            "import cbcs_connections",
            "_CBCS_ALSO_ROLE = %d" % _ALSO_ROLE,
            "self._cbcs_lookup_tables = {%s}" % tables,
            "if isinstance(fields, str):",
            "    fields = (fields,)",
            "self._cbcs_lookup_filling = True",
            "try:",
        ]
        for plan, sql, show_at, indexes in ready:
            body.extend(_indent(_one_lookup(plan, sql, show_at, indexes)))
        body.extend(
            [
                "finally:",
                "    self._cbcs_lookup_filling = False",
            ]
        )
        if _lines_present(doc):
            body.extend(_line_reload_lines())
        body.extend(
            [
                "if getattr(self, %s, False) and hasattr(self, %s) and not getattr(self, %s, False):"
                % (py_string("_cbcs_ready"), py_string("cbcs_refresh"), py_string("_cbcs_refreshing")),
                "    self.cbcs_refresh()",
            ]
        )
        methods = [
            Method("cbcs_load_lookups", "\n".join(body), "cbcsLookup", params="fields=None"),
            Method("_cbcs_select_lookup", "\n".join(_select_body()), "cbcsLookup", params="name, value"),
            Method("_cbcs_drop_unknown", "\n".join(_drop_body()), "cbcsLookup", params="combo, value"),
            Method("_cbcs_same_key", "\n".join(_same_body()), "cbcsLookup", params="left, right"),
            Method("_cbcs_also", "\n".join(_also_body()), "cbcsLookup", params="name, column"),
        ]
        if any(plan.editable for plan, _sql, _show_at, _index in ready):
            methods.append(Method("_cbcs_lookup_keep", "\n".join(_keep_body()), "cbcsLookup", params="combo"))
        return Contribution(imports=tuple(imports), methods=tuple(methods))


EXPANDER = LookupsExpander()


def _open_lines(doc: UiDocument, ctx: CodegenContext) -> Tuple[str, ...]:
    """Load lookups before the first show, and only when this form has one."""

    if not lookup_plans(doc, ctx.attribute_names):
        return ()
    return (
        "_load_lookups = getattr(self, %s, None)" % py_string("cbcs_load_lookups"),
        "if _load_lookups is not None:",
        "    _load_lookups()",
    )


def _install_open_hook() -> None:
    from app.features.form_builder.engine.codegen.expanders.record import register_open_hook

    register_open_hook(_open_lines)


_install_open_hook()


def _indent(lines: Sequence[str], spaces: int = 4) -> List[str]:
    pad = " " * spaces
    return [pad + line if line else line for line in lines]


def _refresh_requested(doc: UiDocument) -> bool:
    walk = getattr(doc, "iter_widgets", None)
    if not callable(walk):
        return False
    try:
        nodes = tuple(walk())
    except Exception:
        return False
    for node in nodes:
        getter = getattr(node, "properties", None)
        found = getter() if callable(getter) else ()
        if not isinstance(found, tuple):
            continue
        for prop in found:
            if not str(getattr(prop, "name", "")).startswith("cbcsOn"):
                continue
            text = getattr(getattr(prop, "value", None), "text", "")
            if isinstance(text, str) and '"refreshLookups"' in text:
                return True
    return False


def _select_columns(plan: LookupPlan) -> List[str]:
    return select_columns(plan.key, plan.show, plan.also)


def _also_indexes(plan: LookupPlan, columns: Sequence[str]) -> Tuple[Tuple[str, int], ...]:
    return also_indexes(plan.also, columns)


def _lines_present(doc: UiDocument) -> bool:
    from app.features.form_builder.engine.codegen.expanders.record import _has_lines

    return _has_lines(doc)


def _line_reload_lines() -> List[str]:
    return [
        "_reload_lines = getattr(self, %s, None)" % py_string("_cbcs_reload_line_lookups"),
        "if _reload_lines is not None:",
        "    _reload_lines()",
    ]


def _one_lookup(plan: LookupPlan, sql: str, show_at: int, indexes: Sequence[Tuple[str, int]]) -> List[str]:
    blank = plan.blank
    if not blank and plan.nullable:
        blank = "(choose a %s)" % singular(plan.table)
    lines = [
        "if fields is None or %s in fields:" % py_string(plan.widget),
        "    _combo = self.%s" % plan.widget,
        "    _current = _combo.currentData()",
        "    with cbcs_connections.work(%s) as _conn:" % py_string(plan.connection),
        "        _cursor = _conn.cursor()",
        "        _cursor.execute(%s)" % py_string(sql),
        "        _rows = _cursor.fetchall()",
        "    _combo.blockSignals(True)",
        "    try:",
        "        _combo.clear()",
    ]
    if blank:
        lines.append("        _combo.addItem(%s, None)" % py_string(blank))
    lines.extend(
        [
            "        for _row in _rows:",
            "            _shown = _row[%d] if len(_row) > %d else None" % (show_at, show_at),
            "            _combo.addItem(%s if _shown is None else str(_shown), _row[0])" % py_string(""),
            "            _extra = {}",
        ]
    )
    for name, index in indexes:
        lines.append(
            "            _extra[%s] = self._cbcs_from(%s, _row[%d] if len(_row) > %d else None)"
            % (py_string(name), py_string(name), index, index)
        )
    if indexes:
        lines.append("            _combo.setItemData(_combo.count() - 1, _extra, _CBCS_ALSO_ROLE)")
    lines.extend(
        [
            "        self._cbcs_select_lookup(%s, _current)" % py_string(plan.widget),
        ]
    )
    if plan.editable:
        lines.extend(_editable_lines(plan.widget))
    lines.extend(
        [
            "    finally:",
            "        _combo.blockSignals(False)",
        ]
    )
    return lines


def _editable_lines(widget: str) -> List[str]:
    return [
        "        _policy = getattr(getattr(_combo.__class__, %s, _combo.__class__), %s, None)"
        % (py_string("InsertPolicy"), py_string("NoInsert")),
        "        if _policy is None:",
        "            _policy = getattr(_combo.__class__, %s, None)" % py_string("NoInsert"),
        "        if _policy is not None:",
        "            _combo.setInsertPolicy(_policy)",
        "        _guards = getattr(self, %s, None)" % py_string("_cbcs_lookup_guards"),
        "        if _guards is None:",
        "            _guards = {}",
        "            self._cbcs_lookup_guards = _guards",
        "        if not _guards.get(%s):" % py_string(widget),
        "            _guards[%s] = True" % py_string(widget),
        "            _edit = _combo.lineEdit()",
        "            if _edit is not None:",
        "                _edit.editingFinished.connect(lambda combo=_combo: self._cbcs_lookup_keep(combo))",
        "        _known = getattr(self, %s, None)" % py_string("_cbcs_completers"),
        "        if _known is None:",
        "            _known = {}",
        "            self._cbcs_completers = _known",
        "        _completer = _known.get(%s)" % py_string(widget),
        "        if _completer is None:",
        "            _completer = QCompleter(_combo.model(), _combo)",
        "            _completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)",
        "            _completer.setFilterMode(Qt.MatchFlag.MatchContains)",
        "            _combo.setCompleter(_completer)",
        "            _known[%s] = _completer" % py_string(widget),
        "        else:",
        "            _completer.setModel(_combo.model())",
    ]


def _select_body() -> List[str]:
    return [
        "_combo = getattr(self, name, None)",
        "if _combo is None:",
        "    return",
        "self._cbcs_drop_unknown(_combo, value)",
        "_found = -1",
        "_i = 0",
        "while _i < _combo.count():",
        "    _data = _combo.itemData(_i)",
        "    if _data == value or (value is not None and self._cbcs_same_key(_data, value)):",
        "        _found = _i",
        "        break",
        "    _i = _i + 1",
        "if _found >= 0:",
        "    _combo.setCurrentIndex(_found)",
        "    return",
        "if value is None:",
        "    _combo.setCurrentIndex(-1)",
        "    return",
        "_combo.addItem(%s %% value, value)" % py_string("(unknown #%s)"),
        "_combo.setCurrentIndex(_combo.count() - 1)",
        "_seen = getattr(self, %s, None)" % py_string("_cbcs_lookup_missing"),
        "if _seen is None:",
        "    _seen = {}",
        "    self._cbcs_lookup_missing = _seen",
        "_mark = (name, str(value))",
        "if _mark not in _seen:",
        "    _seen[_mark] = True",
        "    _trace = getattr(self, %s, None)" % py_string("_cbcs_trace"),
        "    if _trace is not None:",
        "        _table = getattr(self, %s, {}).get(name, %s)" % (py_string("_cbcs_lookup_tables"), py_string("")),
        "        _trace(%s, name, %s %% (name, value, _table))"
        % (py_string("lookup"), py_string("Lookup %s: key %s isn't in %s")),
    ]


def _drop_body() -> List[str]:
    return [
        "_i = combo.count() - 1",
        "while _i >= 0:",
        "    _text = str(combo.itemText(_i))",
        "    _data = combo.itemData(_i)",
        "    _same = value is not None and (_data == value or self._cbcs_same_key(_data, value))",
        "    if _text.startswith(%s) and not _same:" % py_string("(unknown #"),
        "        combo.removeItem(_i)",
        "    _i = _i - 1",
    ]


def _keep_body() -> List[str]:
    return [
        "if getattr(self, %s, False):" % py_string("_cbcs_lookup_filling"),
        "    return",
        "_edit = combo.lineEdit()",
        "if _edit is None:",
        "    return",
        "_text = _edit.text()",
        "_match = combo.findText(_text)",
        "if _match >= 0:",
        "    if combo.currentIndex() != _match:",
        "        combo.setCurrentIndex(_match)",
        "    return",
        "_index = combo.currentIndex()",
        "if _index >= 0:",
        "    combo.setEditText(combo.itemText(_index))",
    ]


def _same_body() -> List[str]:
    return [
        "if left is None or right is None:",
        "    return False",
        "if type(left) is bool or type(right) is bool:",
        "    return left is right",
        "if left == right:",
        "    return True",
        "return str(left) == str(right)",
    ]


def _also_body() -> List[str]:
    return [
        "_CBCS_ALSO_ROLE = %d" % _ALSO_ROLE,
        "_combo = getattr(self, name, None)",
        "if _combo is None:",
        "    return None",
        "_index = _combo.currentIndex()",
        "if _index < 0:",
        "    return None",
        "_extra = _combo.itemData(_index, _CBCS_ALSO_ROLE)",
        "if not isinstance(_extra, dict):",
        "    return None",
        "return _extra.get(column)",
    ]
