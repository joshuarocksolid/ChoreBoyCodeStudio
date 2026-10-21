"""Primitive ops: the only six ways a document changes (CONTRACTS.md section 3.3).

Every command, however complex (wrap, morph, paste, rename...), compiles to a
sequence of these. Correctness of undo, redo, replay and change events reduces
to correctness of these six and their inverses.

Ops are frozen, hashable and JSON-able (``op_to_json``). They never hold live
nodes, only ids, frozen values and ``NodeSpec`` snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.spec import NodeSpec, PropertyEntry


@dataclass(frozen=True)
class InsertNodeOp:
    """Insert ``spec`` at ``index`` (0..len) of ``parent``'s ``slot``.

    Precondition (checked by ``mutate``): every id in ``spec`` is set and not
    present in the document. Freshness (every id came from ``ctx.alloc()`` in
    this entry) is checked by ``ctx.do`` on forward application only, never by
    ``mutate``, undo or redo. Inverse: RemoveNodeOp(spec.id)."""

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
    """Replace the whole ``ui`` node with ``spec`` (kind ``ui``, id DOCUMENT_ID;
    every other id set and not present in the document, except 0). Freshness is
    checked by ``ctx.do`` on forward application only, as for InsertNodeOp.
    Inverse: ReplaceRootOp with the old snapshot.
    Used only by ReplaceDocument (View XML commit, draft/history restore,
    external reload)."""

    spec: NodeSpec


Op = Union[InsertNodeOp, RemoveNodeOp, MoveNodeOp, SetPropertyOp, SetFieldOp, ReplaceRootOp]


def op_to_json(op: Op) -> object:
    """Deterministic JSON for traces and replay fixtures."""
    ...


def op_from_json(data: object) -> Op:
    ...
