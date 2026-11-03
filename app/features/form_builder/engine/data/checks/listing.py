"""FB314, FB315, and FB322 for list screens."""

from __future__ import annotations

import os
import weakref
from typing import Dict, Iterable, Optional, Sequence, cast

from app.features.form_builder.engine.data.check import DataCheck
from app.features.form_builder.engine.data.listing import VALUE_READ
from app.features.form_builder.engine.data.source import ListSource, RecordSource, read_data
from app.features.form_builder.engine.data.sql import (
    PG8000_SCAN_SENTENCE,
    is_identifier,
    pg8000_scan_closed,
    select_source_error,
)
from app.features.form_builder.engine.diagnostics import CODES, DiagnosticLocation, FormDiagnostic
from app.features.form_builder.engine.ui4.values import StringValue

import app.features.form_builder.engine.diagnostic_codes.fb3xx_data  # noqa: F401

_SENTENCE = "Only a single SELECT can be a list's source."
_PROBES: "weakref.WeakKeyDictionary[object, Dict[str, object]]" = weakref.WeakKeyDictionary()


def remember_list_probe(document: object, sql: str, outcome: object) -> None:
    """Keep a probe on the document. Publish reads this and does not connect."""

    try:
        bucket = _PROBES.get(document)
    except TypeError:
        return
    if bucket is None:
        bucket = {}
        try:
            _PROBES[document] = bucket
        except TypeError:
            return
    bucket[sql] = outcome


def cached_list_probe(document: object, sql: str) -> object:
    try:
        bucket = _PROBES.get(document)
    except TypeError:
        return None
    if not isinstance(bucket, dict):
        return None
    return bucket.get(sql)


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if not callable(add):
        return
    add(DataCheck("list-sql", _sql, 260))
    add(DataCheck("list-widgets", _widgets, 270))
    add(DataCheck("list-names", _names, 280))
    add(DataCheck("list-open-key", _open_key, 290))


def _sql(doc: object, connections: object, schema: object) -> Iterable[FormDiagnostic]:
    del schema
    source = _list(doc)
    if source is None or not source.sql.strip():
        return ()
    grammar = select_source_error(source.sql)
    if grammar:
        return (_at(doc, "FB314", grammar, _root(doc)),)
    if _postgres(connections, source.connection) and not pg8000_scan_closed(source.sql):
        return (_at(doc, "FB314", PG8000_SCAN_SENTENCE, _root(doc)),)
    outcome = cached_list_probe(doc, source.sql)
    kind = getattr(outcome, "kind", "")
    if outcome is None or getattr(outcome, "ok", False) or kind in ("no_driver", "cancelled"):
        return ()
    reason = str(getattr(outcome, "reason", "") or "").strip() or _SENTENCE
    return (_at(doc, "FB314", reason, _root(doc)),)


def _widgets(doc: object, connections: object, schema: object) -> Iterable[FormDiagnostic]:
    del connections, schema
    source = _list(doc)
    if source is None:
        return ()
    nodes = { _name(node): node for node in _nodes(doc) }
    found = []
    if source.search_field:
        node = nodes.get(source.search_field)
        if node is None or _class(node) != "QLineEdit":
            found.append(_at(doc, "FB315", _widget_sentence(source.search_field), node or _root(doc)))
    for item in source.filters:
        node = nodes.get(item.field)
        if node is None or _class(node) not in VALUE_READ:
            found.append(_at(doc, "FB315", _widget_sentence(item.field), node or _root(doc)))
    return found


def _names(doc: object, connections: object, schema: object) -> Iterable[FormDiagnostic]:
    del connections, schema
    source = _list(doc)
    if source is None:
        return ()
    bad = []
    if source.table and not is_identifier(source.table):
        bad.append(source.table)
    for name in tuple(source.columns) + tuple(source.search):
        if name and not is_identifier(name):
            bad.append(name)
    for item in source.filters:
        if item.column and not is_identifier(item.column):
            bad.append(item.column)
    if source.open is not None and source.open.key and not is_identifier(source.open.key):
        bad.append(source.open.key)
    return tuple(_at(doc, "FB307", CODES["FB307"].title.format(name=name), _root(doc)) for name in bad)


def _open_key(doc: object, connections: object, schema: object) -> Iterable[FormDiagnostic]:
    del connections, schema
    source = _list(doc)
    if source is None or source.open is None or not source.open.form or not source.open.key:
        return ()
    target = _record_key(source.open.form)
    if not target or target == source.open.key:
        return ()
    message = CODES["FB322"].title.format(
        form="%s.ui" % source.open.form,
        target=target,
        key=source.open.key,
    )
    return (_at(doc, "FB322", message, _root(doc)),)


def _record_key(stem: str) -> str:
    from app.features.form_builder.engine.data.schema_cache import installed_root
    from app.features.form_builder.engine.ids import IdAllocator
    from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui

    root = installed_root()
    if not root:
        return ""
    path = os.path.join(root, "forms", "%s.ui" % stem)
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        document = read_ui(text, allocator=IdAllocator()).document
    except (OSError, UnicodeError, UiReadError):
        return ""
    prop = getattr(document.root, "prop", None)
    if not callable(prop):
        return ""
    entry = prop("cbcsData")
    value = getattr(entry, "value", None)
    raw = getattr(value, "text", "")
    if not isinstance(raw, str) or not raw.strip():
        return ""
    found = read_data(raw).value
    if isinstance(found, RecordSource):
        return found.key
    return ""


def _postgres(connections: object, name: str) -> bool:
    items = getattr(connections, "connections", None)
    if not isinstance(items, (tuple, list)):
        return False
    for item in items:
        if getattr(item, "name", None) == name and getattr(item, "engine", None) == "postgres":
            return True
    return False


def _list(doc: object) -> Optional[ListSource]:
    root = _root(doc)
    prop = getattr(root, "prop", None)
    if not callable(prop):
        return None
    entry = prop("cbcsData")
    value = getattr(entry, "value", None)
    text = getattr(value, "text", "")
    if not isinstance(text, str) or not text.strip():
        return None
    found = read_data(text).value
    if isinstance(found, ListSource):
        return found
    return None


def _widget_sentence(widget: str) -> str:
    return CODES["FB315"].title.format(widget=widget or "This widget")


def _at(doc: object, code: str, message: str, node: object) -> FormDiagnostic:
    del doc
    info = CODES[code]
    return FormDiagnostic(info.code, info.severity, message, _location(node), "data.check")


def _location(node: object) -> DiagnosticLocation:
    node_id = getattr(node, "id", None)
    if not isinstance(node_id, int):
        node_id = getattr(node, "node_id", None)
    return DiagnosticLocation(
        node_id if isinstance(node_id, int) else None,
        _name(node) or None,
        "cbcsData",
        ("cbcsData",),
    )


def _root(doc: object) -> object:
    return getattr(doc, "root", None)


def _nodes(doc: object) -> Sequence[object]:
    walk = getattr(doc, "iter_widgets", None)
    if not callable(walk):
        walk = getattr(doc, "iter_preorder", None)
    if not callable(walk):
        return ()
    try:
        return tuple(cast(Iterable[object], walk()))
    except Exception:
        return ()


def _name(node: object) -> str:
    value = getattr(node, "object_name", "")
    if callable(value):
        try:
            value = value()
        except Exception:
            return ""
    return value if isinstance(value, str) else ""


def _class(node: object) -> str:
    value = getattr(node, "class_name", "")
    if callable(value):
        try:
            value = value()
        except Exception:
            return ""
    return value if isinstance(value, str) else ""
