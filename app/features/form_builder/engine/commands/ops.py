"""Primitive ops: the only six ways a document changes (CONTRACTS.md section 3.3).

Every command, however complex (wrap, morph, paste, rename...), compiles to a
sequence of these. Correctness of undo, redo, replay and change events reduces
to correctness of these six and their inverses.

Ops are frozen, hashable and JSON-able (``op_to_json``). They never hold live
nodes, only ids, frozen values and ``NodeSpec`` snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Union

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.spec import NodeSpec, PropertyEntry


@dataclass(frozen=True)
class InsertNodeOp:
    """Insert ``spec`` (all ids set, none present in the document) at
    ``index`` (0..len) of ``parent``'s ``slot``. Inverse: RemoveNodeOp(spec.id)."""

    parent: NodeId
    slot: str
    index: int
    spec: NodeSpec


@dataclass(frozen=True)
class RemoveNodeOp:
    """Remove ``node`` and its subtree. Inverse: InsertNodeOp at the old parent,
    slot and index with the removed subtree's snapshot."""

    node: NodeId


@dataclass(frozen=True)
class MoveNodeOp:
    """Move ``node`` (keeping its id and subtree) to ``index`` of ``parent``'s
    ``slot``. ``index`` is counted AFTER the node has been taken out of its old
    list, so it is in 0..len(target list without the node). Moving a node into
    its own subtree is an OpError. Inverse: MoveNodeOp to the old position."""

    node: NodeId
    parent: NodeId
    slot: str
    index: int


@dataclass(frozen=True)
class SetPropertyOp:
    """Set, replace or remove one property/attribute entry on ``owner``.

    ``entry`` None removes the entry identified by (``kind``, ``name``).
    When the entry exists, it is replaced in place and ``index`` must be None.
    When it does not exist, it is inserted at ``index`` (0..len of that kind's
    list); the planner computes ``index`` by rank insertion
    (``QtClassTable.property_rank``) so redo and replay are exact.
    Inverse: SetPropertyOp restoring the old entry at its old index (or removing).
    """

    owner: NodeId
    kind: str  # "property" | "attribute"
    name: str
    entry: Optional[PropertyEntry]
    index: Optional[int] = None


@dataclass(frozen=True)
class SetFieldOp:
    """Set scalar field ``field`` of ``node`` (see ``schema.SCHEMA``) to ``value``
    (None clears an optional field; OpError for a required field).
    Inverse: SetFieldOp with the old value."""

    node: NodeId
    field: str
    value: object


@dataclass(frozen=True)
class ReplaceRootOp:
    """Replace the whole ``ui`` node with ``spec`` (kind ``ui``, id DOCUMENT_ID,
    every other id fresh). Inverse: ReplaceRootOp with the old snapshot.
    Used only by ReplaceDocument (View XML commit, draft/history restore,
    external reload)."""

    spec: NodeSpec


Op = Union[InsertNodeOp, RemoveNodeOp, MoveNodeOp, SetPropertyOp, SetFieldOp, ReplaceRootOp]


def op_to_json(op: Op) -> object:
    """Deterministic JSON for traces and replay fixtures."""
    return {"op": type(op).__name__, "payload": _encode(op)}


def op_from_json(data: object) -> Op:
    if not isinstance(data, dict):
        raise ValueError("op json must be an object")
    name = data.get("op")
    payload = data.get("payload")
    if not isinstance(name, str) or not isinstance(payload, dict):
        raise ValueError("op json is missing op or payload")
    cls = _OPS.get(name)
    if cls is None:
        raise ValueError("unknown op %s" % (name,))
    decoded = {key: _decode_field(key, value) for key, value in payload.items()}
    return cls(**decoded)  # type: ignore[operator]


def _encode(value: object) -> object:
    if isinstance(value, (InsertNodeOp, RemoveNodeOp, MoveNodeOp, SetPropertyOp, SetFieldOp, ReplaceRootOp)):
        return {field: _encode(getattr(value, field)) for field in value.__dataclass_fields__}
    if isinstance(value, NodeSpec):
        return {
            "kind": value.kind,
            "id": None if value.id is None else int(value.id),
            "fields": [[key, _encode(item)] for key, item in value.fields],
            "properties": [_encode(entry) for entry in value.properties],
            "attributes": [_encode(entry) for entry in value.attributes],
            "slots": [[name, [_encode(child) for child in kids]] for name, kids in value.slots],
            "extra_attrs": [[key, item] for key, item in value.extra_attrs],
        }
    if isinstance(value, PropertyEntry):
        from app.features.form_builder.engine.ui4.values import value_to_json

        return {
            "kind": value.kind,
            "name": value.name,
            "value": value_to_json(value.value),
            "stdset": value.stdset,
            "extra_attrs": [[key, item] for key, item in value.extra_attrs],
        }
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    if value is None or isinstance(value, (str, int, bool, float)):
        return value
    if hasattr(value, "__dataclass_fields__"):
        return {
            "$": type(value).__name__,
            **{key: _encode(getattr(value, key)) for key in value.__dataclass_fields__},  # type: ignore[attr-defined]
        }
    raise TypeError("cannot encode %s" % (type(value).__name__,))


def _decode_field(key: str, value: object) -> object:
    if key in ("parent", "node", "owner"):
        if not isinstance(value, int):
            raise ValueError("expected an id")
        return NodeId(value)
    if key == "spec":
        if not isinstance(value, dict):
            raise ValueError("expected a spec")
        return _decode_spec(value)
    if key == "entry":
        if value is None:
            return None
        return _decode_entry(value)
    if key == "index":
        if value is None or isinstance(value, int):
            return value
        raise ValueError("expected an index")
    if key in ("slot", "kind", "name", "field"):
        if not isinstance(value, str):
            raise ValueError("expected a string")
        return value
    if key == "value":
        return value
    raise ValueError("unexpected op field %s" % (key,))


def _decode_spec(data: Dict[str, object]) -> NodeSpec:
    raw_id = data.get("id")
    raw_fields = data.get("fields", [])
    raw_properties = data.get("properties", [])
    raw_attributes = data.get("attributes", [])
    raw_slots = data.get("slots", [])
    raw_extra = data.get("extra_attrs", [])
    if not isinstance(raw_fields, list) or not isinstance(raw_properties, list):
        raise ValueError("malformed spec")
    if not isinstance(raw_attributes, list) or not isinstance(raw_slots, list) or not isinstance(raw_extra, list):
        raise ValueError("malformed spec")
    return NodeSpec(
        kind=str(data.get("kind")),
        id=None if raw_id is None else NodeId(int(raw_id)),  # type: ignore[arg-type]
        fields=tuple((str(pair[0]), pair[1]) for pair in raw_fields),
        properties=tuple(_decode_entry(item) for item in raw_properties),
        attributes=tuple(_decode_entry(item) for item in raw_attributes),
        slots=tuple(
            (str(slot[0]), tuple(_decode_spec(child) for child in slot[1]))
            for slot in raw_slots
        ),
        extra_attrs=tuple((str(pair[0]), str(pair[1])) for pair in raw_extra),
    )


def _decode_entry(data: object) -> PropertyEntry:
    from app.features.form_builder.engine.ui4.values import value_from_json

    if not isinstance(data, dict):
        raise ValueError("property entry must be an object")
    extra = data.get("extra_attrs", [])
    if not isinstance(extra, list):
        raise ValueError("malformed property entry")
    stdset = data.get("stdset")
    return PropertyEntry(
        kind=str(data.get("kind")),
        name=str(data.get("name")),
        value=value_from_json(data.get("value")),
        stdset=None if stdset is None else str(stdset),
        extra_attrs=tuple((str(pair[0]), str(pair[1])) for pair in extra),
    )


_OPS = {
    "InsertNodeOp": InsertNodeOp,
    "RemoveNodeOp": RemoveNodeOp,
    "MoveNodeOp": MoveNodeOp,
    "SetPropertyOp": SetPropertyOp,
    "SetFieldOp": SetFieldOp,
    "ReplaceRootOp": ReplaceRootOp,
}
