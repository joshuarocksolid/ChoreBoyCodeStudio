"""Mutation primitives. PRIVATE (CONTRACTS.md sections 2.6 and 3.3).

Only ``engine/commands/log.py``, ``engine/commands/context.py`` and
``engine/ui4/reader.py`` may import this module (dune file role
``form_builder.mutate_guard``). Every other module changes a document through
the command log.

Each primitive applies one op, keeps the id index, parent map, name index and
per-node property maps consistent, bumps ``UiDocument.revision`` by one, and
returns the exact inverse op. ``apply(doc, op)`` followed by
``apply(doc, inverse)`` leaves ``doc.fingerprint()`` unchanged (section 13).
Each primitive validates its preconditions and raises ``OpError`` before
changing anything, so a failed primitive leaves the document untouched.
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
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.schema import SCHEMA, field_spec, slot_spec
from app.features.form_builder.engine.ui4.spec import NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.writer import require_xml_text


class OpError(ValueError):
    """An op's precondition failed (unknown id, wrong slot, index out of range,
    kind not accepted by slot, duplicate id, single-child slot occupied,
    moving a node into its own subtree). Raised before any change."""


def load_spec(spec: NodeSpec) -> UiDocument:
    """Build a document from a fully-id'd ``ui`` spec. The reader is the caller."""
    return UiDocument.from_spec(spec)


def apply(doc: UiDocument, op: Op) -> Op:
    """Apply ``op`` and return its inverse. O(changed): O(1) for property and
    field ops, O(subtree) for insert/remove (index maintenance), O(siblings) for
    list splicing, O(form) only for ReplaceRootOp."""
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


def _insert(doc: UiDocument, op: InsertNodeOp) -> Op:
    parent = _require(doc, op.parent)
    _require_slot(parent.kind, op.slot, op.spec.kind)
    kids = parent.children(op.slot)
    if op.index < 0 or op.index > len(kids):
        raise OpError("index out of range")
    slot = slot_spec(parent.kind, op.slot)
    if slot.max_len and len(kids) >= slot.max_len:
        raise OpError("slot %s already holds its only child" % (op.slot,))
    _require_fresh_ids(doc, op.spec)
    if op.spec.id is None:
        raise OpError("inserted spec has no id")
    updated = _edit(doc.to_spec(), op.parent, lambda spec: _splice(spec, op.slot, op.index, op.spec))
    doc._replace_tree(UiDocument.from_spec(updated).ui)
    return RemoveNodeOp(op.spec.id)


def _remove(doc: UiDocument, op: RemoveNodeOp) -> Op:
    node = _require(doc, op.node)
    if node.id == DOCUMENT_ID or node.parent_id is None or node.parent_slot is None:
        raise OpError("the ui node cannot be removed")
    parent_id = node.parent_id
    slot = node.parent_slot
    index = node.index_in_parent()
    snapshot = node.to_spec()
    updated = _edit(doc.to_spec(), parent_id, lambda spec: _unsplice(spec, slot, op.node))
    doc._replace_tree(UiDocument.from_spec(updated).ui)
    return InsertNodeOp(parent=parent_id, slot=slot, index=index, spec=snapshot)


def _move(doc: UiDocument, op: MoveNodeOp) -> Op:
    node = _require(doc, op.node)
    if node.parent_id is None or node.parent_slot is None:
        raise OpError("the ui node cannot be moved")
    if op.node == op.parent or doc.is_ancestor(op.node, op.parent):
        raise OpError("a node cannot move into its own subtree")
    parent = _require(doc, op.parent)
    _require_slot(parent.kind, op.slot, node.kind)
    old_parent = node.parent_id
    old_slot = node.parent_slot
    old_index = node.index_in_parent()
    destination = list(parent.children(op.slot))
    if old_parent == op.parent and old_slot == op.slot:
        destination = [item for item in destination if item.id != op.node]
    if op.index < 0 or op.index > len(destination):
        raise OpError("index out of range")
    slot = slot_spec(parent.kind, op.slot)
    if slot.max_len and len(destination) >= slot.max_len:
        raise OpError("slot %s already holds its only child" % (op.slot,))
    snapshot = node.to_spec()
    removed = _edit(doc.to_spec(), old_parent, lambda spec: _unsplice(spec, old_slot, op.node))
    updated = _edit(removed, op.parent, lambda spec: _splice(spec, op.slot, op.index, snapshot))
    doc._replace_tree(UiDocument.from_spec(updated).ui)
    return MoveNodeOp(node=op.node, parent=old_parent, slot=old_slot, index=old_index)


def _set_property(doc: UiDocument, op: SetPropertyOp) -> Op:
    if op.entry is not None:
        _reject_illegal_text(op.entry)
    owner = _require(doc, op.owner)
    if op.kind not in ("property", "attribute"):
        raise OpError("kind must be property or attribute")
    current = owner.properties() if op.kind == "property" else owner.attributes()
    existing = _find_entry(current, op.name)
    if op.entry is None:
        if existing is None:
            raise OpError("property %s is not set" % (op.name,))
        old_entry, old_index = existing
        updated = _edit(doc.to_spec(), op.owner, lambda spec: _write_entries(spec, op.kind, _without(current, op.name)))
        doc._replace_tree(UiDocument.from_spec(updated).ui)
        return SetPropertyOp(owner=op.owner, kind=op.kind, name=op.name, entry=old_entry, index=old_index)
    if op.entry.kind != op.kind or op.entry.name != op.name:
        raise OpError("entry identity does not match the op")
    if existing is not None:
        if op.index is not None:
            raise OpError("replacing a property takes no index")
        old_entry, old_index = existing
        replaced = _replace_entry(current, op.entry)
        updated = _edit(doc.to_spec(), op.owner, lambda spec: _write_entries(spec, op.kind, replaced))
        doc._replace_tree(UiDocument.from_spec(updated).ui)
        return SetPropertyOp(owner=op.owner, kind=op.kind, name=op.name, entry=old_entry, index=None)
    if op.index is None or op.index < 0 or op.index > len(current):
        raise OpError("index out of range")
    inserted = list(current)
    inserted.insert(op.index, op.entry)
    updated = _edit(doc.to_spec(), op.owner, lambda spec: _write_entries(spec, op.kind, tuple(inserted)))
    doc._replace_tree(UiDocument.from_spec(updated).ui)
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
    old = node.field(op.field)
    updated = _edit(doc.to_spec(), op.node, lambda item: _write_field(item, op.field, op.value))
    doc._replace_tree(UiDocument.from_spec(updated).ui)
    return SetFieldOp(node=op.node, field=op.field, value=old)


def _replace_root(doc: UiDocument, op: ReplaceRootOp) -> Op:
    if op.spec.kind != "ui" or op.spec.id != DOCUMENT_ID:
        raise OpError("ReplaceRootOp requires a ui spec")
    for node_id in op.spec.ids():
        if node_id != DOCUMENT_ID and doc.contains(node_id):
            raise OpError("replacement id %s is already in use" % (int(node_id),))
    previous = doc.to_spec()
    doc._replace_tree(UiDocument.from_spec(op.spec).ui)
    return ReplaceRootOp(previous)


def _require(doc: UiDocument, node_id: NodeId):
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
    """``SetProperty`` / ``SetField`` reject text outside the XML 1.0 Char range.

    ``CommandRejected`` arrives with the command log (M1.2). Until then the
    ui4 boundary raises ``OpError``.
    """
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


def _raw_ids(spec: NodeSpec) -> Tuple[Optional[NodeId], ...]:
    found: List[Optional[NodeId]] = [spec.id]
    for _name, kids in spec.slots:
        for kid in kids:
            found.extend(_raw_ids(kid))
    return tuple(found)


def _edit(spec: NodeSpec, target: NodeId, fn) -> NodeSpec:  # type: ignore[no-untyped-def]
    if spec.id == target:
        return fn(spec)
    slots = []
    for name, kids in spec.slots:
        slots.append((name, tuple(_edit(child, target, fn) for child in kids)))
    return NodeSpec(
        kind=spec.kind,
        id=spec.id,
        fields=spec.fields,
        properties=spec.properties,
        attributes=spec.attributes,
        slots=tuple(slots),
        extra_attrs=spec.extra_attrs,
    )


def _splice(spec: NodeSpec, slot: str, index: int, child: NodeSpec) -> NodeSpec:
    mapping = {name: kids for name, kids in spec.slots}
    kids = list(mapping.get(slot, ()))
    kids.insert(index, child)
    mapping[slot] = tuple(kids)
    return _with_slots(spec, mapping)


def _unsplice(spec: NodeSpec, slot: str, node_id: NodeId) -> NodeSpec:
    mapping = {name: kids for name, kids in spec.slots}
    kids = [child for child in mapping.get(slot, ()) if child.id != node_id]
    if kids:
        mapping[slot] = tuple(kids)
    else:
        mapping.pop(slot, None)
    return _with_slots(spec, mapping)


def _with_slots(spec: NodeSpec, mapping: dict) -> NodeSpec:  # type: ignore[type-arg]
    ordered = []
    for slot in SCHEMA[spec.kind].slots:
        kids = mapping.get(slot.name)
        if kids:
            ordered.append((slot.name, kids))
    return NodeSpec(
        kind=spec.kind,
        id=spec.id,
        fields=spec.fields,
        properties=spec.properties,
        attributes=spec.attributes,
        slots=tuple(ordered),
        extra_attrs=spec.extra_attrs,
    )


def _find_entry(entries: Tuple[PropertyEntry, ...], name: str) -> Optional[Tuple[PropertyEntry, int]]:
    for index, entry in enumerate(entries):
        if entry.name == name:
            return entry, index
    return None


def _without(entries: Tuple[PropertyEntry, ...], name: str) -> Tuple[PropertyEntry, ...]:
    return tuple(entry for entry in entries if entry.name != name)


def _replace_entry(entries: Tuple[PropertyEntry, ...], replacement: PropertyEntry) -> Tuple[PropertyEntry, ...]:
    return tuple(replacement if entry.name == replacement.name else entry for entry in entries)


def _write_entries(spec: NodeSpec, kind: str, entries: Tuple[PropertyEntry, ...]) -> NodeSpec:
    if kind == "property":
        return NodeSpec(
            kind=spec.kind,
            id=spec.id,
            fields=spec.fields,
            properties=entries,
            attributes=spec.attributes,
            slots=spec.slots,
            extra_attrs=spec.extra_attrs,
        )
    return NodeSpec(
        kind=spec.kind,
        id=spec.id,
        fields=spec.fields,
        properties=spec.properties,
        attributes=entries,
        slots=spec.slots,
        extra_attrs=spec.extra_attrs,
    )


def _write_field(spec: NodeSpec, field: str, value: object) -> NodeSpec:
    order = [item.name for item in SCHEMA[spec.kind].fields]
    kept = [(key, item) for key, item in spec.fields if key != field]
    if value is not None:
        kept.append((field, value))
    kept.sort(key=lambda item: order.index(item[0]) if item[0] in order else 1000)
    return NodeSpec(
        kind=spec.kind,
        id=spec.id,
        fields=tuple(kept),
        properties=spec.properties,
        attributes=spec.attributes,
        slots=spec.slots,
        extra_attrs=spec.extra_attrs,
    )
