"""FB313 and FB307 for a lines grid.

FB313: the lines link must point at the form's table.
FB307: a name in ``cbcsRows`` that ``quote_ident`` refuses, including a
whitespace-only name, is reported on that grid.
FB320 already lives in ``engine/data/check.py``. The link check is skipped
when the schema cache is absent, same as the other schema checks.
"""

from __future__ import annotations

from typing import Iterable, Optional

from app.features.form_builder.engine.data.check import DataCheck
from app.features.form_builder.engine.data.schema import schema_for
from app.features.form_builder.engine.data.lines import compile_line_formula, type_for_kind
from app.features.form_builder.engine.data.types import describe
from app.features.form_builder.engine.data.source import CalcColumn, DataColumn, read_data, read_rows
from app.features.form_builder.engine.data.sql import name_usable
from app.features.form_builder.engine.diagnostics import CODES, DiagnosticLocation, FormDiagnostic
from app.features.form_builder.engine.ui4.values import StringValue

import app.features.form_builder.engine.diagnostic_codes.fb1xx_formula  # noqa: F401
import app.features.form_builder.engine.diagnostic_codes.fb3xx_data  # noqa: F401


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if not callable(add):
        return
    add(DataCheck("lines-names", _names, 250))
    add(DataCheck("lines-link", _link, 260))
    add(DataCheck("lines-formula", _formulas, 270))


def _names(doc: object, connections: object, schema: object) -> Iterable[FormDiagnostic]:
    del connections, schema
    info = CODES["FB307"]
    found = []
    for node, rows in _grids(doc):
        for name in _row_names(rows):
            if name_usable(name):
                continue
            found.append(
                FormDiagnostic(
                    info.code,
                    info.severity,
                    info.title.format(name=name),
                    DiagnosticLocation(
                        getattr(node, "id", None),
                        getattr(node, "object_name", None),
                        "cbcsRows",
                        ("cbcsRows",),
                    ),
                    "data.check",
                )
            )
    return tuple(found)


def _row_names(rows: object) -> Iterable[str]:
    names = []
    for field in ("table", "link", "key", "order", "position"):
        value = getattr(rows, field, "")
        if isinstance(value, str) and value:
            names.append(value)
    for column in getattr(rows, "columns", ()) or ():
        if isinstance(column, DataColumn) and column.column:
            names.append(column.column)
        elif isinstance(column, CalcColumn) and column.name:
            names.append(column.name)
    return names


def _link(doc: object, connections: object, schema: object) -> Iterable[FormDiagnostic]:
    del connections
    source = _record(doc)
    if source is None:
        return ()
    cached = schema if schema is not None else schema_for(doc, source.connection)
    if cached is None:
        return ()
    found = []
    for node, rows in _grids(doc):
        line_table = _table(cached, rows.table)
        if line_table is None:
            continue
        column = _column(line_table, rows.link)
        target = ""
        if column is not None and column.references is not None:
            target = column.references.table
        if target == source.table:
            continue
        info = CODES["FB313"]
        message = (
            info.title.replace("{link}", rows.link)
            .replace("{table}", rows.table)
            .replace("{source table}", source.table)
        )
        found.append(
            FormDiagnostic(
                info.code,
                info.severity,
                message,
                DiagnosticLocation(getattr(node, "id", None), getattr(node, "object_name", None), "cbcsRows", ("cbcsRows",)),
                "data.check",
            )
        )
    return tuple(found)


def _record(doc: object):
    root = getattr(doc, "root", None)
    prop = getattr(root, "prop", None)
    if not callable(prop):
        return None
    entry = prop("cbcsData")
    value = getattr(entry, "value", None)
    text = getattr(value, "text", "")
    if not isinstance(text, str) or not text.strip():
        return None
    found = read_data(text).value
    table = getattr(found, "table", None)
    connection = getattr(found, "connection", None)
    if isinstance(table, str) and isinstance(connection, str):
        return found
    return None


def _grids(doc: object):
    walk = getattr(doc, "iter_widgets", None)
    if not callable(walk):
        return ()
    found = []
    try:
        nodes = tuple(walk())
    except Exception:
        return ()
    for node in nodes:
        entry = node.prop("cbcsRows") if hasattr(node, "prop") else None
        value = getattr(entry, "value", None)
        if not isinstance(value, StringValue) or not value.text.strip():
            continue
        rows, error = read_rows(value.text)
        if error is None and rows is not None:
            found.append((node, rows))
    return tuple(found)


def _lookup_attrs(schema: object, rows: object) -> dict:
    found = {}
    engine = getattr(schema, "engine", "sqlite")
    chosen = engine if engine in ("sqlite", "postgres") else "sqlite"
    for column in getattr(rows, "columns", ()) or ():
        lookup = getattr(column, "lookup", None)
        if lookup is None or not getattr(lookup, "also", ()):
            continue
        table = _table(schema, lookup.table)
        typed = {}
        for name in lookup.also:
            spec = None
            for item in getattr(table, "columns", ()) or ():
                if getattr(item, "name", None) == name:
                    spec = item
                    break
            if spec is None:
                continue
            kind = describe(
                spec.type,
                engine=chosen,
                column_name=name,
                nullable=getattr(spec, "nullable", True),
            )
            typed[name] = type_for_kind(kind.kind)
        found[column.column] = typed
    return found


def _table(schema: object, name: Optional[str]):
    if name is None:
        return None
    for table in getattr(schema, "tables", ()) or ():
        if getattr(table, "name", None) == name:
            return table
    return None


def _formulas(doc: object, connections: object, schema: object) -> Iterable[FormDiagnostic]:
    del connections
    found = []
    for node, rows in _grids(doc):
        attrs = _lookup_attrs(schema, rows)
        pairs = []
        pending = []
        for column in rows.columns:
            if isinstance(column, DataColumn):
                kind = column.kind or "text"
                pairs.append((column.column, kind))
                if column.default:
                    pending.append((column.default, kind))
            elif isinstance(column, CalcColumn):
                kind = "money" if column.kind == "money" else "text"
                pairs.append((column.name, kind))
                pending.append((column.formula, kind))
        for text, kind in pending:
            if not text:
                continue
            _source, _helpers, _imports, problems, _denoms = compile_line_formula(text, pairs, kind, attrs)
            for code in problems:
                info = CODES.get(code)
                if info is None:
                    continue
                found.append(
                    FormDiagnostic(
                        info.code,
                        info.severity,
                        info.title,
                        DiagnosticLocation(
                            getattr(node, "id", None),
                            getattr(node, "object_name", None),
                            "cbcsRows",
                            ("cbcsRows",),
                        ),
                        "data.check",
                    )
                )
    return found


def _column(table: object, name: str):
    for column in getattr(table, "columns", ()) or ():
        if getattr(column, "name", None) == name:
            return column
    return None

