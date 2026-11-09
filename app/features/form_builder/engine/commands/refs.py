"""Native name references. One pass, no chaining (CONTRACTS.md section 3.6).

Identity fields (a widget's own object name, a layout's name, and the same for
spacers, actions, action groups and button groups) are not references. Rewriting
them here would chain ``x -> x_2`` with ``x_2 -> x_3``.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.commands.ops import Op, RemoveNodeOp, SetFieldOp, SetPropertyOp
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import Node
from app.features.form_builder.engine.ui4.spec import NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import CStringValue, StringValue

NAME_FIELD = {
    "widget": "object_name",
    "layout": "object_name",
    "spacer": "name",
    "action": "name",
    "actiongroup": "name",
    "buttongroup": "name",
}

RESERVED_NAMES = frozenset({"form", "record", "window", "True", "False", "None"})

FORMULA_NAMES = frozenset(
    {
        "is_blank",
        "if_blank",
        "round",
        "abs",
        "min",
        "max",
        "sum",
        "avg",
        "count",
        "number",
        "whole",
        "text",
        "len",
        "upper",
        "lower",
        "trim",
        "proper",
        "left",
        "right",
        "contains",
        "starts_with",
        "ends_with",
        "replace",
        "matches",
        "is_email",
        "is_phone",
        "is_zip",
        "today",
        "now",
        "date",
        "year",
        "month",
        "day",
        "weekday",
        "add_days",
        "add_months",
        "days_between",
    }
)


def identity_name(node: Node) -> Optional[str]:
    field_name = NAME_FIELD.get(node.kind)
    if field_name is None:
        return None
    value = node.field(field_name)
    if isinstance(value, str) and value:
        return value
    return None


def native_rename_ops(
    doc: UiDocument,
    renames: Tuple[Tuple[str, str], ...],
    scope: Optional[Sequence[NodeId]],
) -> Tuple[Op, ...]:
    """Rewrite native references. ``renames`` is applied simultaneously."""
    mapping = {old: new for old, new in renames if old != new}
    if not mapping:
        return ()
    allowed = None if scope is None else set(scope)
    found: List[Op] = []
    for node in doc.iter_preorder():
        if allowed is not None and node.id not in allowed:
            continue
        found.extend(_rename_node(node, mapping))
    return tuple(found)


def native_delete_ops(doc: UiDocument, removed_names: Tuple[str, ...]) -> Tuple[Op, ...]:
    """Drop native references to names that no longer exist."""
    gone = set(removed_names)
    if not gone:
        return ()
    found: List[Op] = []
    for node in doc.iter_preorder():
        found.extend(_delete_node(node, gone))
    return tuple(found)


def rewrite_spec_refs(spec: NodeSpec, mapping: Dict[str, str]) -> NodeSpec:
    """Rewrite references inside a fragment spec. Identity names stay as assigned."""
    name_field = NAME_FIELD.get(spec.kind)
    fields: List[Tuple[str, object]] = []
    for key, value in spec.fields:
        if key == name_field:
            fields.append((key, value))
        else:
            fields.append((key, _map_field_value(spec.kind, key, value, mapping)))
    return NodeSpec(
        kind=spec.kind,
        id=spec.id,
        fields=tuple(fields),
        properties=tuple(_map_entry(entry, mapping) for entry in spec.properties),
        attributes=tuple(_map_entry(entry, mapping) for entry in spec.attributes),
        slots=tuple(
            (slot, tuple(rewrite_spec_refs(child, mapping) for child in kids))
            for slot, kids in spec.slots
        ),
        extra_attrs=spec.extra_attrs,
    )


def _rename_node(node: Node, mapping: Dict[str, str]) -> List[Op]:
    found: List[Op] = []
    if node.kind == "connection":
        for field_name in ("sender", "receiver"):
            value = node.field(field_name)
            if isinstance(value, str) and value in mapping:
                found.append(SetFieldOp(node.id, field_name, mapping[value]))
    elif node.kind == "action":
        menu = node.field("menu")
        if isinstance(menu, str) and menu in mapping:
            found.append(SetFieldOp(node.id, "menu", mapping[menu]))
    elif node.kind == "actionref":
        name = node.field("name")
        if isinstance(name, str) and name in mapping:
            found.append(SetFieldOp(node.id, "name", mapping[name]))
    elif node.kind == "widget":
        zorder = node.field("zorder")
        if isinstance(zorder, tuple):
            mapped = _map_tuple(zorder, mapping)
            if mapped != zorder:
                found.append(SetFieldOp(node.id, "zorder", mapped))
        found.extend(_rename_buddy(node, mapping))
        found.extend(_rename_group(node, mapping))
    elif node.kind == "ui":
        stops = node.field("tabstops")
        if isinstance(stops, tuple):
            mapped = _map_tuple(stops, mapping)
            if mapped != stops:
                found.append(SetFieldOp(node.id, "tabstops", mapped))
    return found


def _delete_node(node: Node, gone: set) -> List[Op]:
    found: List[Op] = []
    if node.kind == "connection":
        sender = node.field("sender")
        receiver = node.field("receiver")
        if sender in gone or receiver in gone:
            found.append(RemoveNodeOp(node.id))
    elif node.kind == "action" and node.field("menu") in gone:
        found.append(SetFieldOp(node.id, "menu", None))
    elif node.kind == "actionref" and node.field("name") in gone:
        found.append(RemoveNodeOp(node.id))
    elif node.kind == "widget":
        zorder = node.field("zorder")
        if isinstance(zorder, tuple) and any(item in gone for item in zorder):
            kept = tuple(item for item in zorder if item not in gone)
            found.append(SetFieldOp(node.id, "zorder", kept if kept else None))
        buddy = node.prop("buddy")
        if buddy is not None and _text(buddy.value) in gone:
            found.append(SetPropertyOp(node.id, "property", "buddy", None, None))
        group = node.attr("buttonGroup")
        if group is not None and _text(group.value) in gone:
            found.append(SetPropertyOp(node.id, "attribute", "buttonGroup", None, None))
    elif node.kind == "ui":
        stops = node.field("tabstops")
        if isinstance(stops, tuple) and any(item in gone for item in stops):
            kept = tuple(item for item in stops if isinstance(item, str) and item not in gone)
            found.append(SetFieldOp(node.id, "tabstops", kept if kept else None))
    return found


def _rename_buddy(node: Node, mapping: Dict[str, str]) -> List[Op]:
    entry = node.prop("buddy")
    if entry is None or not isinstance(entry.value, CStringValue):
        return []
    if entry.value.text not in mapping:
        return []
    replacement = PropertyEntry(
        "property",
        "buddy",
        CStringValue(mapping[entry.value.text]),
        entry.stdset,
        entry.extra_attrs,
    )
    return [SetPropertyOp(node.id, "property", "buddy", replacement, None)]


def _rename_group(node: Node, mapping: Dict[str, str]) -> List[Op]:
    entry = node.attr("buttonGroup")
    if entry is None:
        return []
    text = _text(entry.value)
    if text is None or text not in mapping:
        return []
    replacement = PropertyEntry(
        "attribute",
        "buttonGroup",
        _with_text(entry.value, mapping[text]),
        entry.stdset,
        entry.extra_attrs,
    )
    return [SetPropertyOp(node.id, "attribute", "buttonGroup", replacement, None)]


def _map_entry(entry: PropertyEntry, mapping: Dict[str, str]) -> PropertyEntry:
    if not mapping:
        return entry
    if entry.name == "buddy" and isinstance(entry.value, CStringValue) and entry.value.text in mapping:
        return PropertyEntry(
            entry.kind,
            entry.name,
            CStringValue(mapping[entry.value.text]),
            entry.stdset,
            entry.extra_attrs,
        )
    if entry.name == "buttonGroup":
        text = _text(entry.value)
        if text is not None and text in mapping:
            return PropertyEntry(
                entry.kind,
                entry.name,
                _with_text(entry.value, mapping[text]),
                entry.stdset,
                entry.extra_attrs,
            )
    return entry


def _map_field_value(kind: str, key: str, value: object, mapping: Dict[str, str]) -> object:
    if not mapping:
        return value
    if key == "zorder" and isinstance(value, tuple):
        return _map_tuple(value, mapping)
    if key in ("sender", "receiver", "menu") or (kind == "actionref" and key == "name"):
        if isinstance(value, str) and value in mapping:
            return mapping[value]
    return value


def _map_tuple(values: Tuple[object, ...], mapping: Dict[str, str]) -> Tuple[object, ...]:
    return tuple(mapping.get(item, item) if isinstance(item, str) else item for item in values)


def _text(value: object) -> Optional[str]:
    if isinstance(value, (StringValue, CStringValue)):
        return value.text
    return None


def _with_text(value: object, text: str) -> object:
    if isinstance(value, StringValue):
        return StringValue(text, value.notr, value.comment, value.extracomment, value.id)
    if isinstance(value, CStringValue):
        return CStringValue(text)
    return text
