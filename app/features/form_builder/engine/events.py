"""Change events (CONTRACTS.md section 4).

One ``ChangeSet`` per committed log entry (a single command, a merged command,
or a whole transaction), and one per undo and per redo. Changes are derived
mechanically from the applied ops, one change per op, in application order
(undo: the inverse ops, in the order they were applied).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, List, Literal, Optional, Sequence, Tuple, Union

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
from app.features.form_builder.engine.logic.storage import is_logic_key
from app.features.form_builder.engine.query.tree import is_page_container
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.spec import NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import semantic_equal

Origin = Literal["do", "undo", "redo"]

Category = Literal[
    "node",        # widget/spacer/layout inserted, removed or moved (not items/pages/actions)
    "property",    # a non-logic property or attribute changed
    "layout",      # layout cell/span/alignment/stretch fields, or layout class
    "item",        # list/combo/tree/table items or header sections
    "page",        # a page of a tab/stacked/toolbox/wizard/splitter container
    "action",      # action, action group, addaction, menu/toolbar membership
    "connection",  # <connections>
    "logic",       # any cbcs* dynamic property (LOGIC_DESIGN 6.1) except CBCS_LAYOUT_KEYS
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
    #: The inserted subtree: from the op (do/redo) or its inverse (undo),
    #: shared by reference. Lets a listener rebuild from ChangeSets alone.
    spec: NodeSpec


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
    """Every previous id except DOCUMENT_ID is gone; every listener rebuilds.
    ``spec`` is the new whole-document spec (shared by reference)."""

    removed: FrozenSet[NodeId]
    spec: NodeSpec
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
PRIORITY_SELECTION_NOTIFY = 100  # SelectionModel notifies subscribers (after every log listener)


def change_from_op(doc: UiDocument, op: Op) -> Change:
    """One change for ``op``, read from ``doc`` before the op is applied."""
    if isinstance(op, InsertNodeOp):
        subtree = op.spec.ids()
        return NodeInserted(
            node=op.spec.id if op.spec.id is not None else DOCUMENT_ID,
            kind=op.spec.kind,
            parent=op.parent,
            slot=op.slot,
            index=op.index,
            subtree=subtree,
            category=_structure_category(doc, op.spec.kind, op.parent, op.slot),
            spec=op.spec,
        )
    if isinstance(op, RemoveNodeOp):
        node = doc.node(op.node)
        parent = node.parent_id if node.parent_id is not None else DOCUMENT_ID
        slot = node.parent_slot or ""
        subtree = tuple(item.id for item in doc.iter_preorder(op.node))
        return NodeRemoved(
            node=op.node,
            kind=node.kind,
            parent=parent,
            slot=slot,
            index=node.slot_index,
            subtree=subtree,
            category=_structure_category(doc, node.kind, parent, slot),
        )
    if isinstance(op, MoveNodeOp):
        node = doc.node(op.node)
        old_parent = node.parent_id if node.parent_id is not None else DOCUMENT_ID
        old_slot = node.parent_slot or ""
        origin = _structure_category(doc, node.kind, old_parent, old_slot)
        destination = _structure_category(doc, node.kind, op.parent, op.slot)
        category: Category = "page" if "page" in (origin, destination) else destination
        return NodeMoved(
            node=op.node,
            kind=node.kind,
            old_parent=old_parent,
            old_slot=old_slot,
            old_index=node.slot_index,
            new_parent=op.parent,
            new_slot=op.slot,
            new_index=op.index,
            category=category,
        )
    if isinstance(op, SetPropertyOp):
        owner = doc.node(op.owner)
        current = owner.prop(op.name) if op.kind == "property" else owner.attr(op.name)
        return PropertyChanged(
            owner=op.owner,
            kind=op.kind,
            name=op.name,
            old=current,
            new=op.entry,
            category=_property_category(owner.kind, op.name),
        )
    if isinstance(op, SetFieldOp):
        node = doc.node(op.node)
        return FieldChanged(
            node=op.node,
            field=op.field,
            old=node.field(op.field),
            new=op.value,
            category=_field_category(node.kind, op.field),
        )
    if isinstance(op, ReplaceRootOp):
        removed = frozenset(item.id for item in doc.iter_preorder() if item.id != DOCUMENT_ID)
        return DocumentReplaced(removed=removed, spec=op.spec)
    raise TypeError("unknown op %s" % (type(op).__name__,))


def assemble(
    changes: Sequence[Change],
    revision: int,
    origin: Origin,
    label: str,
) -> ChangeSet:
    """Derived sets for one entry. O(changes)."""
    removed = set()
    added = set()
    structure = set()
    first_old = {}
    last_new = {}
    renamed: List[Tuple[str, str]] = []
    categories = set()
    replaced = False
    for change in changes:
        categories.add(change.category)
        if isinstance(change, NodeInserted):
            for node_id in change.subtree:
                added.add(node_id)
                removed.discard(node_id)
            structure.add(change.parent)
        elif isinstance(change, NodeRemoved):
            for node_id in change.subtree:
                removed.add(node_id)
                added.discard(node_id)
            structure.add(change.parent)
        elif isinstance(change, NodeMoved):
            structure.add(change.old_parent)
            structure.add(change.new_parent)
        elif isinstance(change, PropertyChanged):
            key = (change.owner, change.kind, change.name)
            if key not in first_old:
                first_old[key] = change.old
            last_new[key] = change.new
        elif isinstance(change, FieldChanged):
            if change.field in ("object_name", "name") and isinstance(change.old, str) and isinstance(change.new, str):
                if change.old != change.new:
                    renamed.append((change.old, change.new))
        elif isinstance(change, DocumentReplaced):
            replaced = True
            removed.update(change.removed)
            for node_id in change.spec.ids():
                if node_id != DOCUMENT_ID:
                    added.add(node_id)
                    removed.discard(node_id)
    dirty = set()
    for key, old in first_old.items():
        if not _same_entry(old, last_new[key]):
            dirty.add(key)
    structure -= removed
    return ChangeSet(
        revision=revision,
        origin=origin,
        label=label,
        changes=tuple(changes),
        removed=frozenset(removed),
        added=frozenset(added),
        structure_dirty=frozenset(structure),
        property_dirty=frozenset(dirty),
        renamed=tuple(renamed),
        categories=frozenset(categories),
        replaced=replaced,
    )


def _structure_category(doc: UiDocument, kind: str, parent: NodeId, slot: str) -> Category:
    if kind in ("item", "header"):
        return "item"
    if kind == "widget" and slot == "children" and doc.contains(parent) and is_page_container(doc, parent):
        return "page"
    if kind in ("action", "actiongroup", "actionref"):
        return "action"
    if kind == "connection":
        return "connection"
    if kind in ("customwidget", "include", "resource", "buttongroup"):
        return "form"
    return "node"


def _property_category(kind: str, name: str) -> Category:
    if is_logic_key(name):
        return "logic"
    if kind in ("item", "header"):
        return "item"
    return "property"


def _field_category(kind: str, field: str) -> Category:
    if field in ("object_name", "name"):
        return "name"
    if field == "zorder":
        return "node"
    if kind == "layoutitem" and field in ("row", "column", "rowspan", "colspan", "alignment"):
        return "layout"
    if kind == "layout" and field in (
        "class_name",
        "stretch",
        "rowstretch",
        "columnstretch",
        "rowminimumheight",
        "columnminimumwidth",
    ):
        return "layout"
    if kind == "ui" or kind in ("customwidget", "include", "resource", "buttongroup"):
        return "form"
    if kind == "connection":
        return "connection"
    if kind == "widget" and field == "class_name":
        return "node"
    return "node"


def _same_entry(old: Optional[PropertyEntry], new: Optional[PropertyEntry]) -> bool:
    if old is None or new is None:
        return old is new
    return old.stdset == new.stdset and old.extra_attrs == new.extra_attrs and semantic_equal(old.value, new.value)

