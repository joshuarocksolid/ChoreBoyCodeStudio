"""FB311 and FB312 for lookup combos (CONTRACTS.md section 19.8)."""

from __future__ import annotations

from typing import Iterable, List, Optional

from app.features.form_builder.engine.data.check import DataCheck
from app.features.form_builder.engine.data.schema import ROW_PROBE_LIMIT, Schema, schema_for
from app.features.form_builder.engine.data.source import RecordSource, read_data, read_lookup
from app.features.form_builder.engine.diagnostics import CODES, DiagnosticLocation, FormDiagnostic
from app.features.form_builder.engine.ui4.values import StringValue

import app.features.form_builder.engine.diagnostic_codes.fb3xx_data  # noqa: F401


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if not callable(add):
        return
    add(DataCheck("lookup-columns", _missing, 260))
    add(DataCheck("lookup-rows", _rows, 270))


def _missing(doc: object, connections: object, schema: object) -> Iterable[FormDiagnostic]:
    del connections
    source = _record(doc)
    if source is None:
        return ()
    cached = _schema(doc, schema, source.connection)
    if cached is None:
        return ()
    tables = {table.name: table for table in cached.tables}
    found: List[FormDiagnostic] = []
    for node in _nodes(doc):
        lookup = _lookup(node)
        if lookup is None:
            continue
        table = tables.get(lookup.table)
        if table is None:
            found.append(_problem(node, lookup.table))
            continue
        names = {column.name for column in table.columns}
        wanted = []
        for name in (lookup.key, lookup.show, lookup.order, *lookup.also):
            if name and name not in wanted:
                wanted.append(name)
        for name in wanted:
            if name not in names:
                found.append(_problem(node, name))
    return tuple(found)


def _rows(doc: object, connections: object, schema: object) -> Iterable[FormDiagnostic]:
    del connections
    source = _record(doc)
    if source is None:
        return ()
    cached = _schema(doc, schema, source.connection)
    if cached is None:
        return ()
    tables = {table.name: table for table in cached.tables}
    found = []
    seen = set()
    for node in _nodes(doc):
        lookup = _lookup(node)
        if lookup is None or lookup.table in seen:
            continue
        table = tables.get(lookup.table)
        rows = getattr(table, "rows", None) if table is not None else None
        if not isinstance(rows, int) or rows <= 2000:
            continue
        seen.add(lookup.table)
        count = "more than 100,000" if rows >= ROW_PROBE_LIMIT else "{:,}".format(rows)
        info = CODES["FB312"]
        message = info.title.format(table=lookup.table, n=count)
        found.append(
            FormDiagnostic(
                info.code,
                info.severity,
                message,
                _location(node),
                "data.check",
            )
        )
    return tuple(found)


def _problem(node: object, name: str) -> FormDiagnostic:
    info = CODES["FB311"]
    return FormDiagnostic(
        info.code,
        info.severity,
        info.title.format(name=name),
        _location(node),
        "data.check",
    )


def _schema(doc: object, schema: object, connection: str) -> Optional[Schema]:
    if isinstance(schema, Schema):
        return schema
    return schema_for(doc, connection)


def _record(doc: object):
    root = getattr(doc, "root", None)
    text = _text(root, "cbcsData")
    if not text:
        return None
    found = read_data(text).value
    if isinstance(found, RecordSource):
        return found
    return None


def _lookup(node: object):
    if (getattr(node, "class_name", "") or "").rsplit(".", 1)[-1] != "QComboBox":
        return None
    text = _text(node, "cbcsLookup")
    if not text:
        return None
    found, _error = read_lookup(text)
    return found


def _text(node: object, name: str) -> str:
    prop = getattr(node, "prop", None)
    if not callable(prop):
        return ""
    entry = prop(name)
    value = getattr(entry, "value", None)
    if isinstance(value, StringValue):
        return value.text
    return ""


def _nodes(doc: object):
    walk = getattr(doc, "iter_widgets", None)
    if not callable(walk):
        return ()
    try:
        return tuple(walk())
    except Exception:
        return ()


def _location(node: object) -> DiagnosticLocation:
    node_id = getattr(node, "id", None)
    name = getattr(node, "object_name", None)
    return DiagnosticLocation(
        node_id if isinstance(node_id, int) else None,
        name if isinstance(name, str) and name else None,
        "cbcsLookup",
        ("cbcsLookup",),
    )
