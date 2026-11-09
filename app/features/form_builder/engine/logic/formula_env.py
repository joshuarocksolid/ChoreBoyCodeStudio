"""Build the formula snapshot from a form and a window reading (CONTRACTS §17.5).

The formula package does not open a document. This module does, once per
structure revision, caption revision and window reading. A single label text
edit patches the one widget and the field it captions. Layout spacing moves
neither revision that this cache reads, so the snapshot is reused.
"""

from __future__ import annotations

import hashlib
import weakref
from dataclasses import replace
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
# key, env, field name -> the label object name that supplied its caption.
_ENV: "weakref.WeakKeyDictionary[UiDocument, Tuple[object, FormulaEnv, Dict[str, str]]]" = (
    weakref.WeakKeyDictionary()
)
_LOCAL_FACE = frozenset({"cbcsKind", "decimals", "prefix", "tristate", "specialValueText"})


def env_for(doc: UiDocument, window_facts: Optional[WindowFacts], catalog: QtClassTable) -> FormulaEnv:
    """Widgets, methods, and the class chain.

    Cached on the tree (``structure_revision``) and on captions (``face_revision``).
    One caption edit updates the widgets that show that caption.
    """
    token = _window_token(window_facts)
    table = catalog if catalog is not None else QtClassTable.shared()
    # Data texts bump ``face_revision``, so the digest does not need its own walk.
    key = (doc.structure_revision, doc.face_revision, token, _ejected(doc), id(table))
    held = _ENV.get(doc)
    if held is not None and held[0] == key:
        return held[1]
    patched = None if held is None else _patch_env(doc, held, key)
    if patched is None and held is not None:
        patched = _patch_added(doc, held, key)
    if patched is not None:
        _ENV[doc] = (key, patched[0], patched[1])
        return patched[0]
    env, sources = _build(doc, window_facts, table)
    _ENV[doc] = (key, env, sources)
    return env


def _patch_env(
    doc: UiDocument,
    held: Tuple[object, FormulaEnv, Dict[str, str]],
    key: Tuple[object, ...],
) -> Optional[Tuple[FormulaEnv, Dict[str, str]]]:
    """One caption or one local face property. None when the snapshot must be rebuilt."""
    old_key = held[0]
    if not isinstance(old_key, tuple) or len(old_key) < 5 or len(key) < 5:
        return None
    if old_key[0] != key[0] or old_key[2:] != key[2:]:
        return None
    edits = [
        edit
        for edit in doc._face_edits
        if isinstance(old_key[1], int) and edit[0] > old_key[1]
    ]
    if len(edits) != 1:
        return None
    _revision, node_id, prop = edits[0]
    node = doc.get(node_id)
    if not isinstance(node, WidgetNode) or not node.object_name:
        return None
    env, sources = held[1], dict(held[2])
    if prop == "text":
        patched = _patch_text(doc, env, sources, node)
        if patched is None:
            return None
        return patched
    if prop in _LOCAL_FACE:
        return _patch_widget(doc, env, sources, node), sources
    return None


def _patch_added(
    doc: UiDocument,
    held: Tuple[object, FormulaEnv, Dict[str, str]],
    key: Tuple[object, ...],
) -> Optional[Tuple[FormulaEnv, Dict[str, str]]]:
    """Widgets inserted since the cached snapshot. None when the tree was rebuilt."""
    old_key = held[0]
    if not isinstance(old_key, tuple) or len(old_key) < 5 or not isinstance(old_key[0], int):
        return None
    if old_key[0] == key[0] or old_key[1] != key[1] or old_key[2:] != key[2:]:
        return None
    added = doc.added_widgets_since(old_key[0])
    if not added:
        return None
    env, sources = held[1], dict(held[2])
    widgets = dict(env.widgets)
    for node_id in added:
        node = doc.get(node_id)
        if not isinstance(node, WidgetNode) or not node.object_name:
            continue
        name = node.object_name
        widgets[name] = _facts(doc, node, _caption_of(doc, sources, name, None))
        _claim_caption(doc, widgets, sources, node, name)
    return replace(env, widgets=MappingProxyType(widgets)), sources


def _claim_caption(
    doc: UiDocument,
    widgets: Dict[str, WidgetFacts],
    sources: Dict[str, str],
    label: WidgetNode,
    name: str,
) -> None:
    buddy = _text(label, "buddy")
    raw = _text(label, "text")
    if not buddy or not raw or sources.get(buddy, "") == name:
        return
    if _earlier_name(doc, name, sources.get(buddy, "")) != name:
        return
    sources[buddy] = name
    previous = widgets.get(buddy)
    if previous is not None and previous.display == raw:
        return
    found = doc.by_name(buddy)
    field = doc.get(found[0]) if found else None
    if isinstance(field, WidgetNode):
        widgets[buddy] = _facts(doc, field, raw)


def _earlier_name(doc: UiDocument, first: str, second: str) -> str:
    if not second or second == first:
        return first
    try:
        widgets = doc.iter_widgets()
    except Exception:
        return first
    for node in widgets:
        if node.object_name == first:
            return first
        if node.object_name == second:
            return second
    return first


def _patch_text(
    doc: UiDocument,
    env: FormulaEnv,
    sources: Dict[str, str],
    label: WidgetNode,
) -> Optional[Tuple[FormulaEnv, Dict[str, str]]]:
    label_name = label.object_name or ""
    if _caption_source_moved(doc, label, sources):
        return None
    widgets = dict(env.widgets)
    if label_name in widgets:
        widgets[label_name] = _facts(doc, label, _caption_of(doc, sources, label_name, None))
    for field, source_name in sources.items():
        if source_name != label_name:
            continue
        fresh = _fresh_caption(doc, label, field)
        if fresh is None:
            return None
        found = doc.by_name(field)
        node = doc.get(found[0]) if found else None
        if not isinstance(node, WidgetNode):
            return None
        widgets[field] = _facts(doc, node, fresh)
    return replace(env, widgets=MappingProxyType(widgets)), sources


def _caption_source_moved(doc: UiDocument, label: WidgetNode, sources: Dict[str, str]) -> bool:
    """True when this label starts captioning a field the snapshot does not record."""
    own = label.object_name or ""
    buddy = _text(label, "buddy")
    raw = _text(label, "text")
    if buddy and raw and sources.get(buddy) != own:
        return True
    for label_id, field in form_row_pairs(doc):
        if label_id != label.id or sources.get(field) == own:
            continue
        shown = caption(doc, label.id).strip()
        if shown and shown != own:
            return True
    return False


def _fresh_caption(doc: UiDocument, label: WidgetNode, field: str) -> Optional[str]:
    """The caption ``_buddy_labels`` would store for this field, or None when the source moves."""
    own = label.object_name or ""
    raw = _text(label, "text")
    if _text(label, "buddy") == field and raw:
        return raw
    shown = caption(doc, label.id).strip()
    if shown and shown != own:
        return shown
    return None


def _patch_widget(
    doc: UiDocument,
    env: FormulaEnv,
    sources: Dict[str, str],
    node: WidgetNode,
) -> FormulaEnv:
    name = node.object_name or ""
    widgets = dict(env.widgets)
    if name:
        widgets[name] = _facts(doc, node, _caption_of(doc, sources, name, None))
    return replace(env, widgets=MappingProxyType(widgets))


def _caption_of(
    doc: UiDocument,
    sources: Dict[str, str],
    widget_name: str,
    edited: Optional[WidgetNode],
) -> str:
    source_name = sources.get(widget_name, "")
    if not source_name:
        return ""
    if edited is not None and source_name == (edited.object_name or ""):
        return _text(edited, "text")
    found = doc.by_name(source_name)
    node = doc.get(found[0]) if found else None
    if not isinstance(node, WidgetNode):
        return ""
    return _text(node, "text")


def _ejected(doc: UiDocument) -> bool:
    return bool(_text(doc.root, "cbcsEjected"))  # type: ignore[arg-type]


def _build(
    doc: UiDocument,
    window_facts: Optional[WindowFacts],
    catalog: QtClassTable,
) -> Tuple[FormulaEnv, Dict[str, str]]:
    doc._reset_added_widgets()
    widgets: Dict[str, WidgetFacts] = {}
    buddies, sources = _buddy_labels(doc)
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
    env = FormulaEnv(
        widgets=MappingProxyType(widgets),
        methods=MappingProxyType(methods),
        reserved=reserved_names(),
        data=_data_facts(doc, widgets),
        class_chain=_chain_of(catalog),
        returns={},
        class_name=class_name,
        window_file="window.py",
        ejected=_ejected(doc),
    )
    return env, sources


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


def _buddy_labels(doc: UiDocument) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Field name to caption text, and field name to the label's object name."""
    labels: Dict[str, str] = {}
    sources: Dict[str, str] = {}
    try:
        widgets = tuple(doc.iter_widgets())
    except Exception:
        return labels, sources
    for node in widgets:
        if (node.class_name or "").rsplit(".", 1)[-1] != "QLabel":
            continue
        buddy = _text(node, "buddy")
        label = _text(node, "text")
        own = node.object_name or ""
        if buddy and label and buddy not in labels:
            labels[buddy] = label
            if own:
                sources[buddy] = own
    for label_id, field in form_row_pairs(doc):
        if field in labels:
            continue
        node = doc.get(label_id)
        own = node.object_name if isinstance(node, WidgetNode) else ""
        text = caption(doc, label_id).strip()
        if text and text != own:
            labels[field] = text
            if own:
                sources[field] = own
    return labels, sources


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
        also_types=_also_types(doc, node),
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
        # Eject removed the source. form.isNew and the other form facts still apply.
        return DataFacts() if _ejected(doc) else None
    record: Dict[str, FType] = {}
    table_name = getattr(source, "table", "") or ""
    connection = getattr(source, "connection", "") or ""
    schema = schema_for(doc, connection) if connection else None
    record_known = False
    if schema is not None and table_name:
        engine = schema.engine or "sqlite"
        for table in schema.tables:
            if table.name != table_name:
                continue
            record_known = True
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
    return DataFacts(
        record=MappingProxyType(record),
        grids=MappingProxyType(grids),
        record_known=record_known,
    )


def _also(node: WidgetNode) -> Tuple[str, ...]:
    from app.features.form_builder.engine.data.source import read_lookup

    text = _text(node, "cbcsLookup")
    if not text:
        return ()
    lookup, _error = read_lookup(text)
    if lookup is None:
        return ()
    return lookup.also


def _also_types(doc: UiDocument, node: WidgetNode) -> Tuple[Tuple[str, FType], ...]:
    """Schema types for a lookup's also columns. Missing columns stay text."""

    from app.features.form_builder.engine.data.schema import schema_for
    from app.features.form_builder.engine.data.source import read_data, read_lookup
    from app.features.form_builder.engine.data.types import describe

    text = _text(node, "cbcsLookup")
    if not text:
        return ()
    lookup, _error = read_lookup(text)
    if lookup is None or not lookup.also:
        return ()
    source_text = _text(doc.root, "cbcsData")
    source = read_data(source_text).value if source_text else None
    connection = getattr(source, "connection", "") if source is not None else ""
    schema = schema_for(doc, connection) if connection else None
    columns = {}
    if schema is not None:
        for table in schema.tables:
            if table.name != lookup.table:
                continue
            engine = schema.engine if schema.engine in ("sqlite", "postgres") else "sqlite"
            for column in table.columns:
                kind = describe(
                    column.type,
                    engine=engine,
                    column_name=column.name,
                    nullable=column.nullable,
                )
                columns[column.name] = _FORMULA_TYPES.get(kind.kind, TEXT)
            break
    return tuple((name, columns.get(name, TEXT)) for name in lookup.also)
