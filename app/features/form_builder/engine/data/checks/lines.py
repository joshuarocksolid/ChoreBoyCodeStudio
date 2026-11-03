"""FB313. The lines link must point at the form's table.

FB320 already lives in ``engine/data/check.py``. Skipped when the schema cache
is absent, same as the other schema checks.
"""

from __future__ import annotations

from typing import Iterable, Optional

from app.features.form_builder.engine.data.check import DataCheck
from app.features.form_builder.engine.data.schema import schema_for
from app.features.form_builder.engine.data.source import read_data, read_rows
from app.features.form_builder.engine.diagnostics import CODES, DiagnosticLocation, FormDiagnostic
from app.features.form_builder.engine.ui4.values import StringValue

import app.features.form_builder.engine.diagnostic_codes.fb3xx_data  # noqa: F401


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if not callable(add):
        return
    add(DataCheck("lines-link", _link, 260))


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


def _table(schema: object, name: Optional[str]):
    if name is None:
        return None
    for table in getattr(schema, "tables", ()) or ():
        if getattr(table, "name", None) == name:
            return table
    return None


def _column(table: object, name: str):
    for column in getattr(table, "columns", ()) or ():
        if getattr(column, "name", None) == name:
            return column
    return None

