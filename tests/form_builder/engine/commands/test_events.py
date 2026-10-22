"""Change sets rebuild the tree, and categories follow the op (CONTRACTS.md section 4)."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.features.form_builder.engine.commands.catalog import (
    AddConnection,
    MoveNodes,
    Rename,
    SetLogic,
    SetProperty,
)
from app.features.form_builder.engine.commands.log import CommandLog
from app.features.form_builder.engine.commands.placement import InBoxLayout
from app.features.form_builder.engine.events import (
    ChangeSet,
    DocumentReplaced,
    FieldChanged,
    NodeInserted,
    NodeMoved,
    NodeRemoved,
    PropertyChanged,
)
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.spec import NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import StringValue
from tests.form_builder.engine.commands._support import BOX, nid, open_log


class _Rec:
    def __init__(self, parent: Optional[NodeId], slot: Optional[str], index: int) -> None:
        self.parent = parent
        self.slot = slot
        self.index = index


class ShadowTree:
    """Parent, slot, child order and property map, updated only from ChangeSets."""

    def __init__(self, doc: UiDocument) -> None:
        self.nodes: Dict[NodeId, _Rec] = {}
        self.props: Dict[NodeId, Dict[Tuple[str, str], PropertyEntry]] = {}
        for node in doc.iter_preorder():
            self.nodes[node.id] = _Rec(node.parent_id, node.parent_slot, node.slot_index)
            self.props[node.id] = {
                (entry.kind, entry.name): entry
                for entry in node.properties() + node.attributes()
            }

    def apply(self, change_set: ChangeSet) -> None:
        for change in change_set.changes:
            if isinstance(change, NodeInserted):
                self._shift(change.parent, change.slot, change.index, 1)
                self._add(change.parent, change.slot, change.index, change.spec)
            elif isinstance(change, NodeRemoved):
                rec = self.nodes[change.node]
                for node_id in self._subtree(change.node):
                    self.nodes.pop(node_id, None)
                    self.props.pop(node_id, None)
                self._shift(rec.parent, rec.slot, rec.index + 1, -1)
            elif isinstance(change, NodeMoved):
                rec = self.nodes[change.node]
                self._shift(rec.parent, rec.slot, rec.index + 1, -1)
                self._shift(change.new_parent, change.new_slot, change.new_index, 1)
                rec.parent = change.new_parent
                rec.slot = change.new_slot
                rec.index = change.new_index
            elif isinstance(change, PropertyChanged):
                bucket = self.props.setdefault(change.owner, {})
                key = (change.kind, change.name)
                if change.new is None:
                    bucket.pop(key, None)
                else:
                    bucket[key] = change.new
            elif isinstance(change, FieldChanged):
                continue
            elif isinstance(change, DocumentReplaced):
                self.nodes.clear()
                self.props.clear()
                self._add(None, None, 0, change.spec)

    def matches(self, doc: UiDocument) -> bool:
        return self._structure() == _live_structure(doc) and self._properties() == _live_properties(doc)

    def _add(self, parent: Optional[NodeId], slot: Optional[str], index: int, spec: NodeSpec) -> None:
        assert spec.id is not None
        self.nodes[spec.id] = _Rec(parent, slot, index)
        self.props[spec.id] = {
            (entry.kind, entry.name): entry
            for entry in spec.properties + spec.attributes
        }
        for slot_name, kids in spec.slots:
            for child_index, child in enumerate(kids):
                self._add(spec.id, slot_name, child_index, child)

    def _shift(self, parent: Optional[NodeId], slot: Optional[str], index: int, delta: int) -> None:
        if parent is None or slot is None:
            return
        for rec in self.nodes.values():
            if rec.parent == parent and rec.slot == slot and rec.index >= index:
                rec.index += delta

    def _subtree(self, node_id: NodeId) -> Tuple[NodeId, ...]:
        children: Dict[Optional[NodeId], List[NodeId]] = {}
        for current, rec in self.nodes.items():
            children.setdefault(rec.parent, []).append(current)
        found: List[NodeId] = []
        stack = [node_id]
        while stack:
            current = stack.pop()
            found.append(current)
            stack.extend(children.get(current, ()))
        return tuple(found)

    def _structure(self) -> Dict[NodeId, Tuple[Optional[NodeId], Optional[str], int]]:
        return {
            node_id: (rec.parent, rec.slot, rec.index)
            for node_id, rec in self.nodes.items()
        }

    def _properties(self) -> Dict[NodeId, Dict[Tuple[str, str], PropertyEntry]]:
        return {node_id: dict(entries) for node_id, entries in self.props.items()}


def _live_structure(doc: UiDocument) -> Dict[NodeId, Tuple[Optional[NodeId], Optional[str], int]]:
    return {
        node.id: (node.parent_id, node.parent_slot, node.slot_index)
        for node in doc.iter_preorder()
    }


def _live_properties(doc: UiDocument) -> Dict[NodeId, Dict[Tuple[str, str], PropertyEntry]]:
    found = {}
    for node in doc.iter_preorder():
        found[node.id] = {
            (entry.kind, entry.name): entry
            for entry in node.properties() + node.attributes()
        }
    return found


def test_shadow_tree_matches_after_edits_undo_and_redo() -> None:
    from tests.support.form_builder.gen import run_sequence

    for seed in range(4):
        run_sequence(seed, 20)


def test_categories_follow_the_op() -> None:
    log = open_log(BOX)
    doc = log.document
    found: List[ChangeSet] = []
    log.subscribe(lambda change_set: found.append(change_set), priority=0)
    button = nid(doc, "okButton")
    log.execute(SetProperty(button, "text", StringValue("Go")))
    log.execute(SetLogic(button, "cbcsEnabledWhen", "1"))
    log.execute(AddConnection("okButton", "clicked", "label", "clear"))
    log.execute(Rename(nid(doc, "label"), "caption"))
    assert found[0].categories == frozenset({"property"})
    assert "logic" in found[1].categories
    assert "connection" in found[2].categories
    assert "name" in found[3].categories


def test_listeners_run_in_priority_order() -> None:
    log = open_log(BOX)
    order: List[int] = []
    log.subscribe(lambda _change_set: order.append(100), priority=100)
    log.subscribe(lambda _change_set: order.append(0), priority=0)
    log.execute(SetProperty(nid(log.document, "okButton"), "text", StringValue("Go")))
    assert order == [0, 100]


def test_one_change_per_op() -> None:
    log: CommandLog = open_log(BOX)
    found: List[ChangeSet] = []
    log.subscribe(lambda change_set: found.append(change_set), priority=0)
    log.execute(SetProperty(nid(log.document, "okButton"), "text", StringValue("Go")))
    assert len(found) == 1
    assert len(found[0].changes) == len(log.entries()[-1].ops)
