"""Change events (CONTRACTS.md section 4).

One ``ChangeSet`` per committed log entry (a single command, a merged command,
or a whole transaction), and one per undo and per redo. Changes are derived
mechanically from the applied ops, one change per op, in application order
(undo: the inverse ops, in the order they were applied).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Literal, Optional, Tuple, Union

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.spec import PropertyEntry

Origin = Literal["do", "undo", "redo"]

Category = Literal[
    "node",        # widget/spacer/layout inserted, removed or moved (not items/pages/actions)
    "property",    # a non-logic property or attribute changed
    "layout",      # layout cell/span/alignment/stretch fields, or layout class
    "item",        # list/combo/tree/table items or header sections
    "page",        # a page of a tab/stacked/toolbox/wizard/splitter container
    "action",      # action, action group, addaction, menu/toolbar membership
    "connection",  # <connections>
    "logic",       # any cbcs* dynamic property (LOGIC_DESIGN 6.1)
    "form",        # ui-level fields: class, tab stops, includes, resources, custom widgets...
    "name",        # object_name / name field (rename)
    "document",    # ReplaceRootOp
]


@dataclass(frozen=True)
class NodeInserted:
    node: NodeId
    kind: str
    parent: NodeId
    slot: str
    index: int
    #: Every id in the inserted subtree (node first, pre-order).
    subtree: Tuple[NodeId, ...]
    category: Category


@dataclass(frozen=True)
class NodeRemoved:
    node: NodeId
    kind: str
    parent: NodeId
    slot: str
    index: int
    subtree: Tuple[NodeId, ...]
    category: Category


@dataclass(frozen=True)
class NodeMoved:
    node: NodeId
    kind: str
    old_parent: NodeId
    old_slot: str
    old_index: int
    new_parent: NodeId
    new_slot: str
    new_index: int
    category: Category


@dataclass(frozen=True)
class PropertyChanged:
    owner: NodeId
    kind: str  # "property" | "attribute"
    name: str
    old: Optional[PropertyEntry]
    new: Optional[PropertyEntry]
    category: Category


@dataclass(frozen=True)
class FieldChanged:
    node: NodeId
    field: str
    old: object
    new: object
    category: Category


@dataclass(frozen=True)
class DocumentReplaced:
    """Every previous id except DOCUMENT_ID is gone; every listener rebuilds."""

    removed: FrozenSet[NodeId]
    category: Category = "document"


Change = Union[NodeInserted, NodeRemoved, NodeMoved, PropertyChanged, FieldChanged, DocumentReplaced]


@dataclass(frozen=True)
class ChangeSet:
    """Delivered after the entry is fully applied; the document is consistent.

    ``revision``: ``UiDocument.revision`` after the entry.
    ``label``: the entry's undo label.
    ``changes``: one per op, application order.
    The remaining fields are derived from ``changes`` once (O(changes)) so every
    listener does not recompute them:

    ``removed``: ids no longer in the document (union of removed subtrees that were
    not re-inserted in the same set).
    ``added``: ids newly in the document.
    ``structure_dirty``: ids whose child lists changed (parents of inserts,
    removes and both ends of moves), excluding removed ids.
    ``property_dirty``: ``(owner, kind, name)`` triples whose final value differs
    from the value before the set (a set-then-reset in one transaction is absent).
    ``renamed``: ``(old_name, new_name)`` pairs, in order.
    ``categories``: every category present.
    ``replaced``: True when the set contains DocumentReplaced.
    """

    revision: int
    origin: Origin
    label: str
    changes: Tuple[Change, ...]
    removed: FrozenSet[NodeId]
    added: FrozenSet[NodeId]
    structure_dirty: FrozenSet[NodeId]
    property_dirty: FrozenSet[Tuple[NodeId, str, str]]
    renamed: Tuple[Tuple[str, str], ...]
    categories: FrozenSet[str]
    replaced: bool


#: Listener priorities: lower runs first. Within a priority, subscription order.
PRIORITY_MODEL_CACHES = 0     # engine-side derived indexes (logic dependency graph...)
PRIORITY_SELECTION = 5        # selection pruning / restore
PRIORITY_DIAGNOSTICS = 8      # cheap synchronous diagnostic producers
PRIORITY_REALIZE = 10         # qtside realizer patches widgets
PRIORITY_HIT_INDEX = 20       # hit index invalidation
PRIORITY_VIEWS = 30           # outline, inspector, overlay repaint requests
PRIORITY_SHELL = 40           # dirty indicator, Problems bridge, preview update scheduling
