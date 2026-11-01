"""The document: node index and read-only queries (CONTRACTS.md section 2).

Complexities are part of the contract (section 12).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from contextlib import contextmanager
from typing import Any, Callable, Dict, FrozenSet, Iterable, Iterator, List, Literal, Optional, Tuple, TypeVar

from app.features.form_builder.engine.ids import DOCUMENT_ID, NodeId
from app.features.form_builder.engine.logic.codec import read_marker
from app.features.form_builder.engine.logic.storage import is_user_logic_key
from app.features.form_builder.engine.ui4.nodes import (
    CustomWidgetNode,
    LayoutNode,
    Node,
    WidgetNode,
    build_node,
)
from app.features.form_builder.engine.ui4.numfmt import format_real
from app.features.form_builder.engine.ui4.schema import SCHEMA, field_accepts
from app.features.form_builder.engine.ui4.spec import NodeSpec
from app.features.form_builder.engine.ui4.values import EnumValue, SetValue, StringValue

EnumStyle = Literal["short", "qualified"]

_T = TypeVar("_T")


def next_object_name(base: str, taken: Iterable[str]) -> str:
    """``base`` if it is free, else the next free ``stem_N``.

    ``email`` becomes ``email_2``. ``email_2`` becomes ``email_3``.
    Membership uses ``in`` only, so a name set is not walked.
    """
    if base not in taken:
        return base
    head, sep, tail = base.rpartition("_")
    if sep and head and tail.isdigit():
        stem = head
        suffix = int(tail) + 1
    else:
        stem = base
        suffix = 2
    while True:
        candidate = "%s_%d" % (stem, suffix)
        if candidate not in taken:
            return candidate
        suffix += 1

_NAME_FIELDS = {
    "widget": "object_name",
    "layout": "object_name",
    "spacer": "name",
    "action": "name",
    "actiongroup": "name",
    "buttongroup": "name",
}
_SLOT_SPEC = {kind: {slot.name: slot for slot in spec.slots} for kind, spec in SCHEMA.items()}
_SLOT_ORDER = {
    kind: {slot.name: index for index, slot in enumerate(spec.slots)}
    for kind, spec in SCHEMA.items()
}
_FIELD_NAMES = {kind: frozenset(item.name for item in spec.fields) for kind, spec in SCHEMA.items()}
_REQUIRED_FIELDS = {
    kind: tuple(item.name for item in spec.fields if item.required)
    for kind, spec in SCHEMA.items()
}


class InvariantError(AssertionError):
    """A model-integrity invariant failed. Always a bug; never a user error."""


class UiDocument:
    """One form. Created by the reader (``engine.ui4.reader.read_ui``) or by
    ``UiDocument.from_spec``; mutated only by ``engine.ui4.mutate`` primitives,
    which the command log calls.

    ``revision`` increases by one for every primitive op applied (do, undo and
    redo all increase it). It is the cache key for lazy serialization, the hit
    index and diagnostics. It is not the undo position.
    """

    def __init__(self, ui: Node, revision: int = 0) -> None:
        if ui.kind != "ui" or ui.id != DOCUMENT_ID:
            raise InvariantError("the document root must be the ui node")
        self._revision = revision
        self._peak = revision
        # ``revision`` without the bumps of event-only edits. See ``structure_memo``.
        self._structure_revision = revision
        self._event_only_depth = 0
        self._structure_memos: Dict[str, Tuple[int, Any]] = {}
        self._nodes: Dict[NodeId, Node] = {}
        self._by_name: Dict[str, List[NodeId]] = {}
        self._name_set: set[str] = set()
        #: Names whose bucket holds two or more ids. A move re-seats only these.
        self._shared_names: set[str] = set()
        self._names_view: Optional[FrozenSet[str]] = None
        self._custom: Dict[str, NodeId] = {}
        self._enum_cache: Optional[Tuple[int, EnumStyle]] = None
        self._logic_count = 0
        # events.py installs this so one step commit can reuse untouched events.
        self._revision_listener: Optional[Any] = None
        # Expat folds every line ending to LF. Designer writes a CRLF source
        # back with CRLF on every line, so the choice has to live beside the tree.
        self.newline = "\n"
        self._index_tree(ui)

    @classmethod
    def from_spec(cls, spec: NodeSpec) -> "UiDocument":
        """Build a document from a ``ui`` spec whose ids are all set and unique."""
        if spec.kind != "ui" or spec.id != DOCUMENT_ID:
            raise InvariantError("from_spec requires a ui spec with DOCUMENT_ID")
        doc = cls(_node_from_spec(spec, None, None, 0))
        doc._check_validate()
        return doc

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def structure_revision(self) -> int:
        """``revision``, except that edits which rewrite only events do not move it.

        A step commit changes a ``cbcs*`` property and the connection list. It adds,
        removes, moves and renames no node, and it touches no picture, action or
        layout. A walk of the form whose answer reads only those can be kept until
        this number moves.
        """
        return self._structure_revision

    @contextmanager
    def event_only_edits(self) -> Iterator[None]:
        """Bumps inside this block move ``revision`` and leave ``structure_revision`` alone."""
        self._event_only_depth += 1
        try:
            yield
        finally:
            self._event_only_depth -= 1

    def structure_memo(self, key: str, build: Callable[[], _T]) -> _T:
        """``build()``, kept until the structure moves.

        The value must be built from ids and plain values, never from node objects,
        which an event edit can replace without moving the structure.
        """
        held = self._structure_memos.get(key)
        if held is not None and held[0] == self._structure_revision:
            return held[1]
        value = build()
        self._structure_memos[key] = (self._structure_revision, value)
        return value

    def logic_property_count(self) -> int:
        """How many ``cbcs*`` logic properties are set, not counting ``cbcsLogic`` itself.

        Maintained as ops apply. ``SetLogic`` uses it to add or drop the version marker
        without scanning the form.
        """
        return self._logic_count

    @property
    def ui(self) -> Node:
        """The ``ui`` node (id DOCUMENT_ID)."""
        return self._nodes[DOCUMENT_ID]

    @property
    def root(self) -> WidgetNode:
        """The form's root widget. A document always has one (reader enforces)."""
        kids = self.ui.children("root")
        if len(kids) != 1 or not isinstance(kids[0], WidgetNode):
            raise InvariantError("the document has no root widget")
        return kids[0]

    def node(self, node_id: NodeId) -> Node:
        """O(1). KeyError when absent."""
        return self._nodes[node_id]

    def get(self, node_id: NodeId) -> Optional[Node]:
        """O(1). None when absent."""
        return self._nodes.get(node_id)

    def contains(self, node_id: NodeId) -> bool:
        """O(1)."""
        return node_id in self._nodes

    def parent(self, node_id: NodeId) -> Optional[Node]:
        """O(1)."""
        parent_id = self._nodes[node_id].parent_id
        if parent_id is None:
            return None
        return self._nodes[parent_id]

    def ancestors(self, node_id: NodeId) -> Tuple[NodeId, ...]:
        """Parent first, ``ui`` last. O(depth)."""
        found: List[NodeId] = []
        current = self._nodes[node_id].parent_id
        while current is not None:
            found.append(current)
            current = self._nodes[current].parent_id
        return tuple(found)

    def is_ancestor(self, ancestor: NodeId, node_id: NodeId) -> bool:
        """True when ``ancestor`` is a strict ancestor. O(depth)."""
        return ancestor in self.ancestors(node_id)

    def depth(self, node_id: NodeId) -> int:
        """``ui`` is 0, root widget 1. O(depth)."""
        return len(self.ancestors(node_id))

    def by_name(self, name: str) -> Tuple[NodeId, ...]:
        """Widgets, layouts, spacers, actions, action groups and button groups whose
        name is ``name``, in document order. More than one means a duplicate
        (FB010). O(k)."""
        return tuple(self._by_name.get(name, ()))

    def names(self) -> FrozenSet[str]:
        """Every name in the shared object-name namespace. O(1) (maintained)."""
        if self._names_view is None:
            self._names_view = frozenset(self._name_set)
        return self._names_view

    def unique_name(self, base: str) -> str:
        """``base`` if free, else the next free ``stem_N`` (Designer's rule).

        A base that already ends in ``_N`` increments that suffix, so a copy of
        ``emailEdit_2`` is ``emailEdit_3``, not ``emailEdit_2_2``.
        """
        return next_object_name(base, self._name_set)

    def form_class_name(self) -> str:
        """``<class>`` text, else the root widget's object name, else ``Form``."""
        class_name = self.ui.field("class_name")
        if isinstance(class_name, str) and class_name:
            return class_name
        root_name = self.root.object_name
        if root_name:
            return root_name
        return "Form"

    def iter_preorder(self, start: NodeId = DOCUMENT_ID) -> Iterator[Node]:
        """Pre-order, schema slot order, explicit stack (no recursion). O(subtree)."""
        stack = [self._nodes[start]]
        while stack:
            node = stack.pop()
            yield node
            ordered: List[Node] = []
            populated = object.__getattribute__(node, "_slots_by_name")
            if populated:
                for slot in SCHEMA[node.kind].slots:
                    kids = populated.get(slot.name)
                    if kids:
                        ordered.extend(kids)
            stack.extend(reversed(ordered))

    def iter_widgets(self) -> Iterator[WidgetNode]:
        """Every widget, document order. O(form)."""
        for node in self.iter_preorder():
            if isinstance(node, WidgetNode):
                yield node

    def layout_of(self, widget_id: NodeId) -> Optional[LayoutNode]:
        """O(1)."""
        node = self._nodes[widget_id]
        if isinstance(node, WidgetNode):
            return node.layout
        return None

    def owning_widget(self, node_id: NodeId) -> Optional[WidgetNode]:
        """Nearest widget ancestor-or-self that owns ``node_id`` visually: for a
        widget, itself; for a layout/item/spacer, the widget whose layout tree
        contains it. O(depth)."""
        node = self._nodes[node_id]
        if isinstance(node, WidgetNode):
            return node
        for ancestor_id in self.ancestors(node_id):
            ancestor = self._nodes[ancestor_id]
            if isinstance(ancestor, WidgetNode):
                return ancestor
        return None

    def containing_layout_item(self, node_id: NodeId) -> Optional[NodeId]:
        """The layout item whose ``content`` is ``node_id``, or None. O(1)."""
        node = self._nodes[node_id]
        if node.parent_slot != "content":
            return None
        parent_id = node.parent_id
        if parent_id is None:
            return None
        if self._nodes[parent_id].kind != "layoutitem":
            return None
        return parent_id

    def tabstops(self) -> Optional[Tuple[str, ...]]:
        """``<tabstops>`` names, or None when the element is absent."""
        value = self.ui.field("tabstops")
        if value is None:
            return None
        if isinstance(value, tuple):
            return tuple(item for item in value if isinstance(item, str))
        return None

    def connections(self) -> Tuple[Node, ...]:
        """ConnectionNodes in document order."""
        return self.ui.children("connections")

    def custom_widget(self, class_name: str) -> Optional[Node]:
        """The ``<customwidget>`` declaring ``class_name``. O(1)."""
        node_id = self._custom.get(class_name)
        if node_id is None:
            return None
        return self._nodes.get(node_id)

    def enum_style(self) -> EnumStyle:
        """Spelling used for new enum/set values: "qualified" when most enum texts in
        the document name the enum type (``Qt::Orientation::Horizontal``), else
        "short". Ties and documents without enums use ``DEFAULT_ENUM_STYLE``.
        Recomputed lazily per revision."""
        cached = self._enum_cache
        if cached is not None and cached[0] == self._revision:
            return cached[1]
        qualified = 0
        short = 0
        for node in self.iter_preorder():
            for entry in node.properties() + node.attributes():
                qualified, short = _count_style(entry.value, qualified, short)
        if qualified > short:
            style: EnumStyle = "qualified"
        elif short > qualified:
            style = "short"
        else:
            style = DEFAULT_ENUM_STYLE
        self._enum_cache = (self._revision, style)
        return style

    def logic_version(self) -> Optional[int]:
        """The version ``cbcsLogic`` on the root says, or None when there is no marker or it
        can't be read (CONTRACTS 15.2; ``marker_read_only`` tells those two apart)."""
        return read_marker(self.root.prop("cbcsLogic")).version

    def fingerprint(self) -> str:
        """sha256 hex of a canonical encoding of the whole tree INCLUDING ids.
        Used by replay and undo tests. O(form)."""
        return _digest(self.ui, include_ids=True)

    def structure_fingerprint(self) -> str:
        """Same, with ids excluded. Equal for two documents read from the same text."""
        return _digest(self.ui, include_ids=False)

    def validate(self) -> None:
        """Check every integrity invariant (CONTRACTS.md section 2.7); raise
        InvariantError naming the first violation. O(form). Called after every
        log entry when ``CBCS_FB_VALIDATE=1`` (always on in tests).
        """
        if self._revision < self._peak:
            raise InvariantError("revision went backwards")
        reachable: Dict[NodeId, Node] = {}
        self._walk_invariants(self.ui, None, None, 0, reachable)
        if set(reachable) != set(self._nodes):
            raise InvariantError("the id index does not match the reachable tree")
        roots = self.ui.children("root")
        if len(roots) != 1 or roots[0].kind != "widget":
            raise InvariantError("a document needs exactly one root widget")
        expected_names: Dict[str, List[NodeId]] = {}
        expected_custom: Dict[str, NodeId] = {}
        for node in self.iter_preorder():
            _check_fields(node)
            _check_property_identity(node)
            name = _node_name(node)
            if name is not None:
                expected_names.setdefault(name, []).append(node.id)
            if isinstance(node, CustomWidgetNode) and node.class_name:
                expected_custom.setdefault(node.class_name, node.id)
        if expected_names != self._by_name:
            raise InvariantError("the name index does not match the tree")
        if {name for name, ids in expected_names.items() if len(ids) > 1} != self._shared_names:
            raise InvariantError("the shared-name set does not match the name index")
        if expected_custom != self._custom:
            raise InvariantError("the custom-widget index does not match the tree")

    def to_spec(self) -> NodeSpec:
        """Frozen snapshot of the whole document (the ``ui`` spec)."""
        return self.ui.to_spec()

    def _bump(self) -> None:
        """One primitive op landed. Revision only moves forward."""
        self._revision += 1
        if self._revision < self._peak:
            raise InvariantError("revision went backwards")
        self._peak = self._revision
        if not self._event_only_depth:
            self._structure_revision += 1
        # A formula write sets this before it bumps, then notes the edit.
        # Every other bump drops the note so the rule graph walks again.
        if not getattr(self, "_formula_pending", False):
            self._formula_edits = None
        self._enum_cache = None
        listener = self._revision_listener
        if listener is not None:
            listener(self)

    def _bind_name(self, node: Node) -> None:
        name = _node_name(node)
        if name is None:
            return
        self._insert_name(name, node.id)

    def _unbind_name(self, node: Node) -> None:
        name = _node_name(node)
        if name is None:
            return
        self._remove_name(name, node.id)

    def _rebind_name(self, node_id: NodeId, old: Optional[str], new: Optional[str]) -> None:
        if old == new:
            return
        if old is not None:
            self._remove_name(old, node_id)
        if new is not None:
            self._insert_name(new, node_id)

    def _insert_name(self, name: str, node_id: NodeId) -> None:
        bucket = self._by_name.setdefault(name, [])
        if node_id in bucket:
            return
        index = 0
        for existing in bucket:
            if self._comes_before(node_id, existing):
                break
            index += 1
        bucket.insert(index, node_id)
        if len(bucket) > 1:
            self._shared_names.add(name)
        self._name_set.add(name)
        self._names_view = None

    def _remove_name(self, name: str, node_id: NodeId) -> None:
        bucket = self._by_name.get(name)
        if not bucket:
            return
        if node_id in bucket:
            bucket.remove(node_id)
        if len(bucket) < 2:
            self._shared_names.discard(name)
        if bucket:
            return
        self._by_name.pop(name, None)
        self._name_set.discard(name)
        self._names_view = None

    def _comes_before(self, left: NodeId, right: NodeId) -> bool:
        """Document order. Both ids are already linked into the tree."""
        if left == right:
            return False
        left_chain = self._chain(left)
        right_chain = self._chain(right)
        limit = min(len(left_chain), len(right_chain))
        for index in range(limit):
            if left_chain[index] != right_chain[index]:
                parent = self._nodes[left_chain[index - 1]]
                return self._child_before(parent, left_chain[index], right_chain[index])
        return len(left_chain) < len(right_chain)

    def _chain(self, node_id: NodeId) -> List[NodeId]:
        chain = [node_id]
        current = self._nodes[node_id].parent_id
        while current is not None:
            chain.append(current)
            current = self._nodes[current].parent_id
        chain.reverse()
        return chain

    def _child_before(self, parent: Node, left: NodeId, right: NodeId) -> bool:
        for slot in SCHEMA[parent.kind].slots:
            ids = [child.id for child in parent.children(slot.name)]
            if left in ids and right in ids:
                return ids.index(left) < ids.index(right)
            if left in ids:
                return True
            if right in ids:
                return False
        return False

    def _add_logic(self, node: Node) -> None:
        for entry in node.properties():
            if is_user_logic_key(entry.name):
                self._logic_count += 1

    def _sub_logic(self, node: Node) -> None:
        for entry in node.properties():
            if is_user_logic_key(entry.name):
                self._logic_count -= 1

    def _note_logic(self, name: str, delta: int) -> None:
        if is_user_logic_key(name):
            self._logic_count += delta

    def _rebuild_custom_index(self) -> None:
        found: Dict[str, NodeId] = {}
        for child in self.ui.children("customwidgets"):
            if isinstance(child, CustomWidgetNode) and child.class_name and child.class_name not in found:
                found[child.class_name] = child.id
        self._custom = found

    def _index_tree(self, node: Node) -> None:
        if node.id in self._nodes:
            raise InvariantError("duplicate id %s" % (int(node.id),))
        self._nodes[node.id] = node
        if isinstance(node, CustomWidgetNode) and node.class_name:
            self._custom.setdefault(node.class_name, node.id)
        name = _node_name(node)
        if name is not None:
            bucket = self._by_name.setdefault(name, [])
            bucket.append(node.id)
            if len(bucket) > 1:
                self._shared_names.add(name)
            self._name_set.add(name)
        self._add_logic(node)
        for _slot_name, kids in node.slots:
            for child in kids:
                self._index_tree(child)

    def _replace_tree(self, ui: Node) -> None:
        """Swap the whole tree. ``ReplaceRootOp`` is the only caller."""
        self._nodes = {}
        self._by_name = {}
        self._name_set = set()
        self._shared_names = set()
        self._names_view = None
        self._custom = {}
        self._enum_cache = None
        self._logic_count = 0
        self._index_tree(ui)
        self._bump()

    def _check_validate(self) -> None:
        if os.environ.get("CBCS_FB_VALIDATE") == "1":
            self.validate()

    def _walk_invariants(
        self,
        node: Node,
        parent_id: Optional[NodeId],
        parent_slot: Optional[str],
        index: int,
        reachable: Dict[NodeId, Node],
    ) -> None:
        if node.id in reachable:
            raise InvariantError("id %s is reachable twice" % (int(node.id),))
        reachable[node.id] = node
        if node.parent_id != parent_id or node.parent_slot != parent_slot or node.slot_index != index:
            raise InvariantError("parent link of id %s does not match the slot that holds it" % (int(node.id),))
        if node.kind not in SCHEMA:
            raise InvariantError("unknown kind %s" % (node.kind,))
        slot_specs = _SLOT_SPEC[node.kind]
        populated = object.__getattribute__(node, "_slots_by_name")
        for slot in SCHEMA[node.kind].slots:
            kids = populated.get(slot.name)
            if not kids:
                continue
            if slot.max_len and len(kids) > slot.max_len:
                raise InvariantError("slot %s of id %s holds more than one child" % (slot.name, int(node.id)))
            for child_index, child in enumerate(kids):
                if child.kind not in slot.accepts:
                    raise InvariantError(
                        "kind %s is not accepted by slot %s" % (child.kind, slot.name)
                    )
                self._walk_invariants(child, node.id, slot.name, child_index, reachable)
        for name in populated:
            if name not in slot_specs:
                raise InvariantError("id %s has unknown slot %s" % (int(node.id), name))


def _node_from_spec(
    spec: NodeSpec,
    parent_id: Optional[NodeId],
    parent_slot: Optional[str],
    index: int,
) -> Node:
    if spec.id is None:
        raise InvariantError("a document spec is missing an id")
    order = _SLOT_ORDER[spec.kind]
    slots = spec.slots
    previous = -1
    ordered = True
    for slot_name, _kids in slots:
        rank = order.get(slot_name, 1000)
        if rank < previous:
            ordered = False
            break
        previous = rank
    if not ordered:
        slots = tuple(sorted(slots, key=lambda item, order=order: order.get(item[0], 1000)))
    child_slots = []
    for slot_name, kids in slots:
        child_slots.append(
            (
                slot_name,
                tuple(
                    _node_from_spec(child, spec.id, slot_name, child_index)
                    for child_index, child in enumerate(kids)
                ),
            )
        )
    return build_node(
        kind=spec.kind,
        node_id=spec.id,
        parent_id=parent_id,
        parent_slot=parent_slot,
        slot_index=index,
        fields=spec.fields,
        properties=spec.properties,
        attributes=spec.attributes,
        slots=tuple(child_slots),
        extra_attrs=spec.extra_attrs,
    )


def _node_name(node: Node) -> Optional[str]:
    field_name = _NAME_FIELDS.get(node.kind)
    if field_name is None:
        return None
    value = node.field(field_name)
    if isinstance(value, str):
        return value
    return None


def _check_fields(node: Node) -> None:
    known = _FIELD_NAMES[node.kind]
    values = object.__getattribute__(node, "_fields_by_name")
    for name, value in node.fields:
        if name not in known:
            raise InvariantError("id %s has unknown field %s" % (int(node.id), name))
        if value is not None and not field_accepts(node.kind, name, value):
            raise InvariantError("id %s field %s has type %s" % (int(node.id), name, type(value).__name__))
    for name in _REQUIRED_FIELDS[node.kind]:
        if values.get(name) is None:
            raise InvariantError("id %s is missing required field %s" % (int(node.id), name))


def _check_property_identity(node: Node) -> None:
    seen = set()
    for entry in node.properties():
        identity = (entry.kind, entry.name)
        if identity in seen:
            raise InvariantError("id %s repeats property %s" % (int(node.id), entry.name))
        seen.add(identity)
        if entry.kind != "property":
            raise InvariantError("a property entry has kind %s" % (entry.kind,))
    seen = set()
    for entry in node.attributes():
        identity = (entry.kind, entry.name)
        if identity in seen:
            raise InvariantError("id %s repeats attribute %s" % (int(node.id), entry.name))
        seen.add(identity)
        if entry.kind != "attribute":
            raise InvariantError("an attribute entry has kind %s" % (entry.kind,))


def _count_style(value: object, qualified: int, short: int) -> Tuple[int, int]:
    if isinstance(value, EnumValue):
        return _add_style(value.text, qualified, short)
    if isinstance(value, SetValue):
        for piece in value.text.split("|"):
            name = piece.strip()
            if not name or name == "0":
                continue
            qualified, short = _add_style(name, qualified, short)
    return qualified, short


def _add_style(text: str, qualified: int, short: int) -> Tuple[int, int]:
    if text.count("::") >= 2:
        return qualified + 1, short
    return qualified, short + 1


def _digest(node: Node, *, include_ids: bool) -> str:
    encoded = _canon(node, include_ids)
    limit = sys.getrecursionlimit()
    # json.dumps walks the tree recursively. A legal form is nested up to MAX_DEPTH.
    sys.setrecursionlimit(max(limit, 10000))
    try:
        payload = json.dumps(encoded, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    finally:
        sys.setrecursionlimit(limit)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canon(value: object, include_ids: bool) -> object:
    """Canonical form of ``value``. Iterative so a form at the nesting limit still fingerprints."""
    stack: List[dict] = [{"value": value, "phase": 0, "parts": []}]
    result: object = None
    while stack:
        frame = stack[-1]
        current = frame["value"]
        if frame["phase"] == 0:
            jobs = _canon_jobs(current)
            if jobs is None:
                result = _canon_leaf(current)
                stack.pop()
                if stack:
                    stack[-1]["parts"].append(result)
                continue
            frame["jobs"] = jobs
            frame["phase"] = 1
            frame["index"] = 0
        jobs = frame["jobs"]
        if frame["index"] < len(jobs):
            nxt = jobs[frame["index"]]
            frame["index"] += 1
            stack.append({"value": nxt, "phase": 0, "parts": []})
            continue
        result = _canon_assemble(current, frame["parts"], include_ids)
        stack.pop()
        if stack:
            stack[-1]["parts"].append(result)
    return result


def _canon_jobs(value: object) -> Optional[List[object]]:
    if isinstance(value, Node):
        jobs: List[object] = []
        jobs.extend(item for _key, item in value.fields)
        jobs.extend(value.properties())
        jobs.extend(value.attributes())
        for _name, kids in value.slots:
            jobs.extend(kids)
        return jobs
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    if value is None or isinstance(value, (str, int, bool, float)):
        return None
    if hasattr(value, "__dataclass_fields__"):
        return [getattr(value, key) for key in _content_keys(value)]
    return None


def _content_keys(value: object) -> List[str]:
    """Dataclass fields that are content. ``compare=False`` marks bookkeeping (a source line)."""
    found = getattr(value, "__dataclass_fields__")
    return [key for key, spec in found.items() if getattr(spec, "compare", True)]


def _canon_leaf(value: object) -> object:
    if isinstance(value, float):
        return format_real(value)
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError("cannot fingerprint %s" % (type(value).__name__,))


def _canon_assemble(value: object, parts: List[object], include_ids: bool) -> object:
    if isinstance(value, Node):
        index = 0
        fields = []
        for key, _item in value.fields:
            fields.append([key, parts[index]])
            index += 1
        properties = parts[index:index + len(value.properties())]
        index += len(value.properties())
        attributes = parts[index:index + len(value.attributes())]
        index += len(value.attributes())
        slots = []
        for name, kids in value.slots:
            slots.append([name, parts[index:index + len(kids)]])
            index += len(kids)
        body: Dict[str, object] = {
            "kind": value.kind,
            "fields": fields,
            "properties": properties,
            "attributes": attributes,
            "slots": slots,
            "extra": [[key, item] for key, item in value.extra_attrs()],
        }
        if include_ids:
            body["id"] = int(value.id)
            body["parent"] = None if value.parent_id is None else int(value.parent_id)
            body["parent_slot"] = value.parent_slot
            body["index"] = value.slot_index
        return body
    if isinstance(value, (set, frozenset)):
        return sorted(parts, key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, tuple):
        return list(parts)
    encoded: Dict[str, object] = {"$": type(value).__name__}
    keys = _content_keys(value)
    for key, part in zip(keys, parts):
        encoded[key] = part
    return encoded


#: Enum spelling for a document with no enum values. Set from the M0.4b
#: Designer-resave corpus (what Designer 6.8 writes for a fresh form).
DEFAULT_ENUM_STYLE: EnumStyle = "qualified"
