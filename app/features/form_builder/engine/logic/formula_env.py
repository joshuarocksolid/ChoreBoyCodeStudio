"""Build the formula snapshot from a form and a window reading (CONTRACTS §17.5).

The formula package does not open a document. This module does, once per
structure revision and window reading, and caches the result on the document.
A form with data properties also keys the cache on those texts, so a logic
edit that does not move ``structure_revision`` still rebuilds the snapshot.
"""

from __future__ import annotations

import hashlib
from types import MappingProxyType
from typing import Dict, Optional, Tuple

from app.features.form_builder.engine.logic.events_catalog import class_chain
from app.features.form_builder.engine.logic.formula.env import DataFacts, FormulaEnv, WidgetFacts, reserved_names
from app.features.form_builder.engine.logic.formula.types import DATE, DATETIME, MONEY, NUMBER, TEXT, TIME, WHOLE, YESNO, FType
from app.features.form_builder.engine.project.window_facts import MethodFacts, WindowFacts
from app.features.form_builder.engine.query.tab_stops import caption, form_row_pairs
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import (
    BoolValue,
    CStringValue,
    DoubleValue,
    FloatValue,
    LongLongValue,
    NumberValue,
    StringValue,
    UIntValue,
    ULongLongValue,
)

_NUMBER = (NumberValue, UIntValue, LongLongValue, ULongLongValue, DoubleValue, FloatValue)
_TEXT = (StringValue, CStringValue)


def env_for(doc: UiDocument, window_facts: Optional[WindowFacts], catalog: QtClassTable) -> FormulaEnv:
    """Widgets, methods, and the class chain. Cached on ``doc.structure_revision``."""
    token = _window_token(window_facts)
    table = catalog if catalog is not None else QtClassTable.shared()
    key = "m7.2a.formula_env\0%s" % token
    if _text(doc.root, "cbcsData"):  # type: ignore[arg-type]
        digest = _data_digest(doc)
        if digest:
            key = "%s\0%s" % (key, digest)
    return doc.structure_memo(key, lambda: _build(doc, window_facts, table))


def _build(doc: UiDocument, window_facts: Optional[WindowFacts], catalog: QtClassTable) -> FormulaEnv:
    widgets: Dict[str, WidgetFacts] = {}
    buddies = _buddy_labels(doc)
    try:
        found = tuple(doc.iter_widgets())
    except Exception:
        found = ()
    for node in found:
        name = node.object_name or ""
        if not name:
            continue
        widgets[name] = _facts(doc, node, buddies.get(name, ""))
    methods: Dict[str, MethodFacts] = {}
    class_name = "Window"
    if window_facts is not None and window_facts.class_name:
        class_name = window_facts.class_name
        for method in window_facts.base_methods:
            methods[method.name] = method
        for method in window_facts.methods:
            methods[method.name] = method
    return FormulaEnv(
        widgets=MappingProxyType(widgets),
        methods=MappingProxyType(methods),
        reserved=reserved_names(),
        data=_data_facts(doc, widgets),
        class_chain=_chain_of(catalog),
        returns={},
        class_name=class_name,
        window_file="window.py",
    )


def _window_token(window_facts: Optional[WindowFacts]) -> str:
    if window_facts is None or not window_facts.class_name:
        return ""
    parts = [window_facts.class_name]
    for method in window_facts.methods:
        parts.append("%s:%s:%s" % (method.name, method.required, method.source_hash))
    return "\n".join(parts)


def _chain_of(catalog: QtClassTable):
    def chain(class_name: str) -> Tuple[str, ...]:
        leaf = class_name.rsplit(".", 1)[-1]
        found = class_chain(catalog, leaf)
        if found:
            return found
        return (leaf,)

    return chain


def _buddy_labels(doc: UiDocument) -> Dict[str, str]:
    labels: Dict[str, str] = {}
    try:
        widgets = tuple(doc.iter_widgets())
    except Exception:
        return labels
    for node in widgets:
        if (node.class_name or "").rsplit(".", 1)[-1] != "QLabel":
            continue
        buddy = _text(node, "buddy")
        label = _text(node, "text")
        if buddy and label and buddy not in labels:
            labels[buddy] = label
    for label_id, field in form_row_pairs(doc):
        if field in labels:
            continue
        node = doc.get(label_id)
        own = node.object_name if isinstance(node, WidgetNode) else ""
        text = caption(doc, label_id).strip()
        if text and text != own:
            labels[field] = text
    return labels


def _facts(doc: UiDocument, node: WidgetNode, buddy_label: str) -> WidgetFacts:
    class_name = (node.class_name or "").rsplit(".", 1)[-1]
    own = _text(node, "text")
    kind = _text(node, "cbcsKind")
    decimals = _whole(node, "decimals")
    if decimals is None:
        decimals = 2 if class_name == "QDoubleSpinBox" else 0
    return WidgetFacts(
        class_name=class_name,
        display=buddy_label or own or (node.object_name or ""),
        kind=kind,
        decimals=decimals,
        prefix=_text(node, "prefix"),
        tristate=_bool(node, "tristate"),
        allow_blank=bool(_text(node, "specialValueText")),
        has_items_data=_items_have_data(node),
        pages=_pages(doc, node),
        also=_also(node),
    )


def _pages(doc: UiDocument, node: WidgetNode) -> Tuple[str, ...]:
    try:
        from app.features.form_builder.engine.query.pages import pages

        return tuple(child.object_name for child in pages(doc, node.id) if child.object_name)
    except Exception:
        return ()


def _items_have_data(node: WidgetNode) -> bool:
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
            if entry.name != "text":
                return True
    return False


def _text(node: WidgetNode, name: str) -> str:
    try:
        value = node.value(name)
    except Exception:
        return ""
    if isinstance(value, _TEXT):
        return value.text
    return ""


def _bool(node: WidgetNode, name: str) -> bool:
    try:
        value = node.value(name)
    except Exception:
        return False
    if isinstance(value, BoolValue):
        return bool(value.value)
    return False


def _whole(node: WidgetNode, name: str) -> Optional[int]:
    try:
        value = node.value(name)
    except Exception:
        return None
    if isinstance(value, _NUMBER) and not isinstance(value.value, bool):
        return int(value.value)
    return None


_FORMULA_TYPES = {
    "whole": WHOLE,
    "number": NUMBER,
    "money": MONEY,
    "text": TEXT,
    "date": DATE,
    "time": TIME,
    "datetime": DATETIME,
    "yesno": YESNO,
}


def _data_digest(doc: UiDocument) -> str:
    parts = [_text(doc.root, "cbcsData")]  # type: ignore[arg-type]
    try:
        widgets = tuple(doc.iter_widgets())
    except Exception:
        widgets = ()
    for node in widgets:
        for key in ("cbcsLookup", "cbcsRows"):
            text = _text(node, key)
            if text:
                parts.append("%s\0%s\0%s" % (node.object_name or "", key, text))
    blob = "\0".join(parts)
    if not blob.strip("\0"):
        return ""
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _data_facts(doc: UiDocument, widgets: Dict[str, WidgetFacts]) -> Optional[DataFacts]:
    from app.features.form_builder.engine.data.schema import schema_for
    from app.features.form_builder.engine.data.source import read_data, read_rows
    from app.features.form_builder.engine.data.types import describe

    read = read_data(_text(doc.root, "cbcsData"))  # type: ignore[arg-type]
    source = read.value
    if source is None:
        return None
    record: Dict[str, FType] = {}
    table_name = getattr(source, "table", "") or ""
    connection = getattr(source, "connection", "") or ""
    schema = schema_for(doc, connection) if connection else None
    if schema is not None and table_name:
        engine = schema.engine or "sqlite"
        for table in schema.tables:
            if table.name != table_name:
                continue
            for column in table.columns:
                ref = column.references.table if column.references is not None else ""
                kind = describe(
                    column.type,
                    engine=engine,
                    column_name=column.name,
                    references_table=ref,
                    nullable=column.nullable,
                )
                record[column.name] = _FORMULA_TYPES.get(kind.kind, TEXT)
    grids: Dict[str, Tuple[str, ...]] = {}
    try:
        nodes = tuple(doc.iter_widgets())
    except Exception:
        nodes = ()
    for node in nodes:
        text = _text(node, "cbcsRows")
        if not text:
            continue
        rows, _error = read_rows(text)
        if rows is None:
            continue
        names = []
        for column in rows.columns:
            name = getattr(column, "column", "") or getattr(column, "name", "")
            if name:
                names.append(name)
        if node.object_name:
            grids[node.object_name] = tuple(names)
    del widgets
    return DataFacts(record=MappingProxyType(record), grids=MappingProxyType(grids))


def _also(node: WidgetNode) -> Tuple[str, ...]:
    from app.features.form_builder.engine.data.source import read_lookup

    text = _text(node, "cbcsLookup")
    if not text:
        return ()
    lookup, _error = read_lookup(text)
    if lookup is None:
        return ()
    return lookup.also
