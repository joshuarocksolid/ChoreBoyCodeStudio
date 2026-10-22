"""Mutation primitives. PRIVATE (CONTRACTS.md sections 2.6 and 3.3).

Only ``engine/commands/log.py``, ``engine/commands/context.py`` and
``engine/ui4/reader.py`` may import this module (dune file role
``form_builder.mutate_guard``). Every other module changes a document through
the command log.

Each primitive applies one op and returns its inverse. Property and field ops
rewrite the node and the ancestor path only. Insert, remove and move splice one
child list and reindex the siblings whose positions moved. ``ReplaceRootOp`` is
the one O(form) primitive. ``apply(doc, op)`` then ``apply(doc, inverse)``
restores ``fingerprint()``. A failed precondition raises ``OpError`` before any
change.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import List, Optional, Tuple

from app.features.form_builder.engine.commands.ops import (
    InsertNodeOp,
    MoveNodeOp,
    Op,
    RemoveNodeOp,
    ReplaceRootOp,
    SetFieldOp,
    SetPropertyOp,
)
from app.features.form_builder.engine.ids import DOCUMENT_ID, NodeId
from app.features.form_builder.engine.ui4.document import UiDocument, _node_from_spec
from app.features.form_builder.engine.ui4.nodes import Node, placed, with_attributes, with_fields, with_properties, with_slots
from app.features.form_builder.engine.ui4.schema import SCHEMA, field_spec, slot_spec
from app.features.form_builder.engine.ui4.spec import NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.writer import require_xml_text

_NAME_FIELD = {
    "widget": "object_name",
    "layout": "object_name",
    "spacer": "name",
    "action": "name",
    "actiongroup": "name",
    "buttongroup": "name",
}

#: Nodes whose objects were replaced by the last ``apply`` call.
#: A property edit on a deep leaf stays on the ancestor path, whatever else the
#: form contains. Tests read this to show insert and move do not walk the form.
last_touched = 0
_touched = 0


class OpError(ValueError):
    """An op's precondition failed (unknown id, wrong slot, index out of range,
    kind not accepted by slot, duplicate id, single-child slot occupied,
    moving a node into its own subtree). Raised before any change."""


def load_spec(spec: NodeSpec) -> UiDocument:
    """Build a document from a fully-id'd ``ui`` spec. The reader is the caller."""
    return UiDocument.from_spec(spec)


def apply(doc: UiDocument, op: Op) -> Op:
    """Apply ``op`` and return its inverse."""
    global last_touched, _touched
    _touched = 0
    try:
        if isinstance(op, InsertNodeOp):
            inverse = _insert(doc, op)
        elif isinstance(op, RemoveNodeOp):
            inverse = _remove(doc, op)
        elif isinstance(op, MoveNodeOp):
            inverse = _move(doc, op)
        elif isinstance(op, SetPropertyOp):
            inverse = _set_property(doc, op)
        elif isinstance(op, SetFieldOp):
            inverse = _set_field(doc, op)
        elif isinstance(op, ReplaceRootOp):
            inverse = _replace_root(doc, op)
        else:
            raise OpError("unknown op")
        return inverse
    finally:
        last_touched = _touched


def _insert(doc: UiDocument, op: InsertNodeOp) -> Op:
    parent = _require(doc, op.parent)
    _require_slot(parent.kind, op.slot, op.spec.kind)
    kids = list(parent.children(op.slot))
    if op.index < 0 or op.index > len(kids):
        raise OpError("index out of range")
    slot = slot_spec(parent.kind, op.slot)
    if slot.max_len and len(kids) >= slot.max_len:
        raise OpError("slot %s already holds its only child" % (op.slot,))
    _require_fresh_ids(doc, op.spec)
    if op.spec.id is None:
        raise OpError("inserted spec has no id")
    child = _node_from_spec(op.spec, op.parent, op.slot, op.index)
    kids.insert(op.index, child)
    _retarget_slot(doc, parent, op.slot, kids)
    _register_subtree(doc, doc._nodes[op.spec.id])
    doc._rebuild_custom_index()
    doc._bump()
    return RemoveNodeOp(op.spec.id)


def _remove(doc: UiDocument, op: RemoveNodeOp) -> Op:
    node = _require(doc, op.node)
    if node.parent_id is None or node.parent_slot is None:
        raise OpError("the ui node cannot be removed")
    if node.id == doc.root.id:
        raise OpError("the root widget cannot be removed")
    parent_id = node.parent_id
    slot = node.parent_slot
    index = node.slot_index
    snapshot = node.to_spec()
    parent = doc._nodes[parent_id]
    kids = [child for child in parent.children(slot) if child.id != op.node]
    _forget_subtree(doc, node)
    _retarget_slot(doc, doc._nodes[parent_id], slot, kids)
    doc._rebuild_custom_index()
    doc._bump()
    return InsertNodeOp(parent=parent_id, slot=slot, index=index, spec=snapshot)


def _move(doc: UiDocument, op: MoveNodeOp) -> Op:
    node = _require(doc, op.node)
    if node.parent_id is None or node.parent_slot is None:
        raise OpError("the ui node cannot be moved")
    if node.id == doc.root.id:
        raise OpError("the root widget cannot be moved")
    if op.node == op.parent or doc.is_ancestor(op.node, op.parent):
        raise OpError("a node cannot move into its own subtree")
    parent = _require(doc, op.parent)
    _require_slot(parent.kind, op.slot, node.kind)
    old_parent = node.parent_id
    old_slot = node.parent_slot
    old_index = node.slot_index
    destination = list(parent.children(op.slot))
    if old_parent == op.parent and old_slot == op.slot:
        destination = [item for item in destination if item.id != op.node]
    if op.index < 0 or op.index > len(destination):
        raise OpError("index out of range")
    slot = slot_spec(parent.kind, op.slot)
    if slot.max_len and len(destination) >= slot.max_len:
        raise OpError("slot %s already holds its only child" % (op.slot,))
    source = doc._nodes[old_parent]
    remaining = [item for item in source.children(old_slot) if item.id != op.node]
    _retarget_slot(doc, source, old_slot, remaining)
    current = doc._nodes[op.node]
    parent = doc._nodes[op.parent]
    destination = [item for item in parent.children(op.slot) if item.id != op.node]
    destination.insert(op.index, current)
    _retarget_slot(doc, parent, op.slot, destination)
    doc._rebuild_custom_index()
    doc._bump()
    return MoveNodeOp(node=op.node, parent=old_parent, slot=old_slot, index=old_index)


def _set_property(doc: UiDocument, op: SetPropertyOp) -> Op:
    if op.entry is not None:
        _reject_illegal_text(op.entry)
    owner = _require(doc, op.owner)
    kind_spec = SCHEMA[owner.kind]
    if op.kind == "property" and not kind_spec.has_properties:
        raise OpError("kind %s has no properties" % (owner.kind,))
    if op.kind == "attribute" and not kind_spec.has_attributes:
        raise OpError("kind %s has no attributes" % (owner.kind,))
    if op.kind not in ("property", "attribute"):
        raise OpError("kind must be property or attribute")
    current = owner.properties() if op.kind == "property" else owner.attributes()
    existing = _find_entry(current, op.name)
    if op.entry is None:
        if existing is None:
            raise OpError("property %s is not set" % (op.name,))
        old_entry, old_index = existing
        updated = _entries_node(owner, op.kind, _without(current, op.name))
        _bubble(doc, updated)
        doc._note_logic(op.name, -1)
        doc._bump()
        return SetPropertyOp(owner=op.owner, kind=op.kind, name=op.name, entry=old_entry, index=old_index)
    if op.entry.kind != op.kind or op.entry.name != op.name:
        raise OpError("entry identity does not match the op")
    if existing is not None:
        if op.index is not None:
            raise OpError("replacing a property takes no index")
        old_entry, _old_index = existing
        updated = _entries_node(owner, op.kind, _replace_entry(current, op.entry))
        _bubble(doc, updated)
        doc._bump()
        return SetPropertyOp(owner=op.owner, kind=op.kind, name=op.name, entry=old_entry, index=None)
    if op.index is None or op.index < 0 or op.index > len(current):
        raise OpError("index out of range")
    inserted = list(current)
    inserted.insert(op.index, op.entry)
    updated = _entries_node(owner, op.kind, tuple(inserted))
    _bubble(doc, updated)
    doc._note_logic(op.name, 1)
    doc._bump()
    return SetPropertyOp(owner=op.owner, kind=op.kind, name=op.name, entry=None, index=None)


def _set_field(doc: UiDocument, op: SetFieldOp) -> Op:
    _reject_illegal_text(op.value)
    node = _require(doc, op.node)
    try:
        spec = field_spec(node.kind, op.field)
    except KeyError:
        raise OpError("unknown field %s" % (op.field,))
    if op.value is None and spec.required:
        raise OpError("required field %s cannot be cleared" % (op.field,))
    if not _value_ok(op.value):
        raise OpError("field %s has an invalid value" % (op.field,))
    old = node.field(op.field)
    updated = _fields_with(node, op.field, op.value)
    _bubble(doc, updated)
    if _NAME_FIELD.get(node.kind) == op.field:
        old_name = old if isinstance(old, str) else None
        new_name = op.value if isinstance(op.value, str) else None
        doc._rebind_name(node.id, old_name, new_name)
    if node.kind == "customwidget" and op.field == "class_name":
        doc._rebuild_custom_index()
    doc._bump()
    return SetFieldOp(node=op.node, field=op.field, value=old)


def _replace_root(doc: UiDocument, op: ReplaceRootOp) -> Op:
    if op.spec.kind != "ui" or op.spec.id != DOCUMENT_ID:
        raise OpError("ReplaceRootOp requires a ui spec")
    for node_id in op.spec.ids():
        if node_id != DOCUMENT_ID and doc.contains(node_id):
            raise OpError("replacement id %s is already in use" % (int(node_id),))
    previous = doc.to_spec()
    doc._replace_tree(UiDocument.from_spec(op.spec).ui)
    global _touched
    _touched += len(op.spec.ids()) + len(previous.ids())
    return ReplaceRootOp(previous)


def _require(doc: UiDocument, node_id: NodeId) -> Node:
    node = doc.get(node_id)
    if node is None:
        raise OpError("unknown id %s" % (int(node_id),))
    return node


def _require_slot(kind: str, slot: str, child_kind: str) -> None:
    try:
        spec = slot_spec(kind, slot)
    except KeyError:
        raise OpError("kind %s has no slot %s" % (kind, slot))
    if child_kind not in spec.accepts:
        raise OpError("slot %s does not accept %s" % (slot, child_kind))


def _require_fresh_ids(doc: UiDocument, spec: NodeSpec) -> None:
    """Every id in ``spec`` is set and not present.

    Freshness (each id came from ``ctx.alloc()`` in this entry) is checked by
    ``ctx.do`` on forward application only, never by mutate, undo or redo.
    """
    for node_id in spec.ids():
        if doc.contains(node_id):
            raise OpError("id %s is already in use" % (int(node_id),))
    if any(item is None for item in _raw_ids(spec)):
        raise OpError("inserted spec has an unset id")


def _reject_illegal_text(value: object) -> None:
    """Text outside the XML 1.0 Char range cannot be stored on a node."""
    if value is None or isinstance(value, (int, float, bool)):
        return
    if isinstance(value, str):
        try:
            require_xml_text(value)
        except ValueError as exc:
            raise OpError(str(exc)) from exc
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _reject_illegal_text(item)
        return
    if is_dataclass(value) and not isinstance(value, type):
        for item in fields(value):
            _reject_illegal_text(getattr(value, item.name))


def _value_ok(value: object) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, tuple):
        return all(_value_ok(item) for item in value)
    if is_dataclass(value) and not isinstance(value, type):
        return all(_value_ok(getattr(value, item.name)) for item in fields(value))
    return False


def _raw_ids(spec: NodeSpec) -> Tuple[Optional[NodeId], ...]:
    found: List[Optional[NodeId]] = [spec.id]
    for _name, kids in spec.slots:
        for kid in kids:
            found.extend(_raw_ids(kid))
    return tuple(found)


def _point(doc: UiDocument, node: Node) -> None:
    global _touched
    doc._nodes[node.id] = node
    _touched += 1


def _bubble(doc: UiDocument, node: Node) -> None:
    """Install ``node`` and copy it up the ancestor path. Siblings are shared."""
    _point(doc, node)
    while node.parent_id is not None:
        parent = doc._nodes[node.parent_id]
        slot = node.parent_slot
        if slot is None:
            raise OpError("node has a parent and no slot")
        found = False
        kids: List[Node] = []
        for child in parent.children(slot):
            if child.id == node.id:
                kids.append(node)
                found = True
            else:
                kids.append(child)
        if not found:
            raise OpError("parent slot lost its child")
        parent = _replace_slot(parent, slot, tuple(kids))
        _point(doc, parent)
        node = parent


def _retarget_slot(doc: UiDocument, parent: Node, slot: str, kids: List[Node]) -> None:
    """Write ``kids`` into ``slot`` and give each child the index it now has."""
    placed_kids: List[Node] = []
    parent_now = doc._nodes[parent.id]
    for index, child in enumerate(kids):
        updated = placed(child, parent_now.id, slot, index)
        placed_kids.append(updated)
        _point(doc, updated)
    _bubble(doc, _replace_slot(parent_now, slot, tuple(placed_kids)))


def _register_subtree(doc: UiDocument, node: Node) -> None:
    for item in _walk(node):
        _point(doc, item)
        doc._bind_name(item)
        doc._add_logic(item)


def _forget_subtree(doc: UiDocument, node: Node) -> None:
    for item in _walk(node):
        doc._unbind_name(item)
        doc._sub_logic(item)
        doc._nodes.pop(item.id, None)


def _walk(node: Node) -> List[Node]:
    found: List[Node] = []
    stack = [node]
    while stack:
        current = stack.pop()
        found.append(current)
        ordered: List[Node] = []
        for slot in SCHEMA[current.kind].slots:
            ordered.extend(current.children(slot.name))
        stack.extend(reversed(ordered))
    return found


def _replace_slot(node: Node, slot: str, kids: Tuple[Node, ...]) -> Node:
    mapping = {name: children for name, children in node.slots}
    if kids:
        mapping[slot] = kids
    else:
        mapping.pop(slot, None)
    ordered = []
    for spec in SCHEMA[node.kind].slots:
        children = mapping.get(spec.name)
        if children:
            ordered.append((spec.name, children))
    return with_slots(node, tuple(ordered))


def _find_entry(entries: Tuple[PropertyEntry, ...], name: str) -> Optional[Tuple[PropertyEntry, int]]:
    for index, entry in enumerate(entries):
        if entry.name == name:
            return entry, index
    return None


def _without(entries: Tuple[PropertyEntry, ...], name: str) -> Tuple[PropertyEntry, ...]:
    return tuple(entry for entry in entries if entry.name != name)


def _replace_entry(entries: Tuple[PropertyEntry, ...], replacement: PropertyEntry) -> Tuple[PropertyEntry, ...]:
    return tuple(replacement if entry.name == replacement.name else entry for entry in entries)


def _entries_node(node: Node, kind: str, entries: Tuple[PropertyEntry, ...]) -> Node:
    if kind == "property":
        return with_properties(node, entries)
    return with_attributes(node, entries)


def _fields_with(node: Node, field: str, value: object) -> Node:
    order = [item.name for item in SCHEMA[node.kind].fields]
    kept = [(key, item) for key, item in node.fields if key != field]
    if value is not None:
        kept.append((field, value))
    kept.sort(key=lambda item: order.index(item[0]) if item[0] in order else 1000)
    return with_fields(node, tuple(kept))
