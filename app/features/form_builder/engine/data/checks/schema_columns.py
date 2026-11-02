"""FB309, FB310, and FB303. They read the schema cache and do not change the form."""

from __future__ import annotations

import datetime
from typing import Iterable, Optional, Sequence

from app.features.form_builder.engine.data.check import DataCheck
from app.features.form_builder.engine.data.schema import is_stale, schema_for
from app.features.form_builder.engine.data.schema_cache import format_read_at
from app.features.form_builder.engine.data.source import read_bind, read_data
from app.features.form_builder.engine.diagnostics import (
    CODES,
    DiagnosticLocation,
    FormDiagnostic,
)
from app.features.form_builder.engine.ui4.values import StringValue


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if not callable(add):
        return
    add(DataCheck("schema-missing", _missing, 100))
    add(DataCheck("schema-stale", _stale, 110))
    add(DataCheck("schema-column", _columns, 120))


def _missing(doc: object, connections: object, schema: object) -> Iterable[FormDiagnostic]:
    del connections, schema
    source = _source(doc)
    if source is None:
        return ()
    if schema_for(doc, source.connection) is not None:
        return ()
    info = CODES["FB309"]
    return (
        FormDiagnostic(
            info.code,
            info.severity,
            info.title,
            _location(_root(doc), "cbcsData"),
            "data.check",
        ),
    )


def _stale(doc: object, connections: object, schema: object) -> Iterable[FormDiagnostic]:
    del connections, schema
    source = _source(doc)
    if source is None:
        return ()
    cached = schema_for(doc, source.connection)
    if cached is None or not is_stale(cached, datetime.datetime.now()):
        return ()
    info = CODES["FB310"]
    return (
        FormDiagnostic(
            info.code,
            info.severity,
            info.title.format(date=format_read_at(cached.read_at)),
            _location(_root(doc), "cbcsData"),
            "data.check",
        ),
    )


def _columns(doc: object, connections: object, schema: object) -> Iterable[FormDiagnostic]:
    del connections, schema
    source = _source(doc)
    if source is None:
        return ()
    cached = schema_for(doc, source.connection)
    if cached is None:
        return ()
    known = _known(cached, getattr(source, "table", "") or "")
    info = CODES["FB303"]
    table = getattr(source, "table", "") or ""
    found = []
    for node in _nodes(doc):
        for entry in _properties(node):
            if getattr(entry, "name", "") != "cbcsBind" or not isinstance(getattr(entry, "value", None), StringValue):
                continue
            column = read_bind(entry.value.text).column
            if not column or column in known:
                continue
            found.append(
                FormDiagnostic(
                    info.code,
                    info.severity,
                    info.title.format(table=table, column=column),
                    _location(node, "cbcsBind"),
                    "data.check",
                )
            )
    return tuple(found)


def _source(doc: object) -> Optional[object]:
    root = _root(doc)
    prop = getattr(root, "prop", None)
    if not callable(prop):
        return None
    entry = prop("cbcsData")
    if entry is None:
        return None
    value = getattr(entry, "value", None)
    if not isinstance(value, StringValue) or not value.text.strip():
        return None
    return read_data(value.text).value


def _known(schema: object, table: str) -> set:
    names = set()
    for item in getattr(schema, "tables", ()) or ():
        if getattr(item, "name", None) != table:
            continue
        for column in getattr(item, "columns", ()) or ():
            name = getattr(column, "name", None)
            if isinstance(name, str):
                names.add(name)
    return names


def _root(doc: object) -> object:
    return getattr(doc, "root", None)


def _nodes(doc: object) -> Sequence[object]:
    walk = getattr(doc, "iter_preorder", None)
    if not callable(walk):
        return ()
    try:
        return tuple(walk())
    except Exception:
        return ()


def _properties(node: object) -> Sequence[object]:
    props = getattr(node, "properties", None)
    if not callable(props):
        return ()
    try:
        return tuple(props())
    except Exception:
        return ()


def _location(node: object, prop_name: str) -> DiagnosticLocation:
    name = ""
    getter = getattr(node, "object_name", None)
    if callable(getter):
        try:
            found = getter()
        except Exception:
            found = ""
        if isinstance(found, str):
            name = found
    elif isinstance(getter, str):
        name = getter
    node_id = getattr(node, "node_id", None)
    return DiagnosticLocation(
        node_id if isinstance(node_id, int) else None,
        name or None,
        prop_name,
        (prop_name,),
    )
