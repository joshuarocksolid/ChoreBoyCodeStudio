"""Read model of native name edges, plus promoted pages.

``rebuild`` reports every role ``references_to`` reports, and a promoted page
whose class is a ``<customwidget>``. Tab stops are stored and not asked about.
Rename and delete keep ``native_rename_ops`` / ``native_delete_ops``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from app.features.form_builder.engine.commands.refs import identity_name
from app.features.form_builder.engine.events import ChangeSet
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import Node, WidgetNode
from app.features.form_builder.engine.ui4.values import CStringValue, StringValue

_PAGE_HOSTS = frozenset({"QTabWidget", "QStackedWidget", "QToolBox"})


@dataclass(frozen=True)
class NameUse:
    """One edge. ``target`` is the object name being pointed at."""

    owner: NodeId
    role: str
    target: str
    signal: str = ""
    slot: str = ""
    direction: str = ""
    promoted_class: str = ""
    page_number: int = 0
    page_title: str = ""


@dataclass(frozen=True)
class Role:
    """One record. Adding a role is adding one ``Role``."""

    name: str
    asks: bool
    edges_on: Callable[[UiDocument, Node], Tuple[NameUse, ...]]


class _Hit:
    def __init__(self, use: NameUse, producer: NodeId) -> None:
        self.use = use
        self.producer = producer


def _field_str(node: Node, name: str) -> str:
    value = node.field(name)
    if isinstance(value, str):
        return value
    return ""


def _value_text(value: object) -> str:
    if isinstance(value, (StringValue, CStringValue)):
        return value.text
    return ""


def _entry_text(node: Node, kind: str, name: str) -> str:
    entry = node.prop(name) if kind == "property" else node.attr(name)
    if entry is None:
        return ""
    return _value_text(entry.value)


def _is_page_host(doc: UiDocument, node: Node) -> bool:
    if not isinstance(node, WidgetNode):
        return False
    if node.class_name in _PAGE_HOSTS:
        return True
    custom = doc.custom_widget(node.class_name)
    if custom is None:
        return False
    return _field_str(custom, "extends") in _PAGE_HOSTS


def _page_title(node: WidgetNode) -> str:
    title = _entry_text(node, "attribute", "title")
    if title:
        return title
    return _entry_text(node, "attribute", "label")


def _names_in(value: object) -> Tuple[str, ...]:
    if not isinstance(value, tuple):
        return ()
    found: List[str] = []
    for item in value:
        if isinstance(item, str) and item and item not in found:
            found.append(item)
    return tuple(found)


def _buddy_edges(doc: UiDocument, node: Node) -> Tuple[NameUse, ...]:
    del doc
    if node.kind != "widget":
        return ()
    target = _entry_text(node, "property", "buddy")
    if not target:
        return ()
    return (NameUse(node.id, "buddy", target),)


def _connection_edges(direction: str) -> Callable[[UiDocument, Node], Tuple[NameUse, ...]]:
    field_name = "sender" if direction == "sender" else "receiver"
    role = "connection." + direction

    def edges(doc: UiDocument, node: Node) -> Tuple[NameUse, ...]:
        del doc
        if node.kind != "connection":
            return ()
        target = _field_str(node, field_name)
        if not target:
            return ()
        return (
            NameUse(
                node.id,
                role,
                target,
                signal=_field_str(node, "signal"),
                slot=_field_str(node, "slot"),
                direction=direction,
            ),
        )

    return edges


def _promoted_edges(doc: UiDocument, node: Node) -> Tuple[NameUse, ...]:
    if not _is_page_host(doc, node) or not isinstance(node, WidgetNode):
        return ()
    found: List[NameUse] = []
    for index, child in enumerate(node.child_widgets):
        custom = None if not child.object_name else doc.custom_widget(child.class_name)
        if custom is None:
            continue
        found.append(
            NameUse(
                custom.id,
                "promoted_page",
                child.object_name,
                promoted_class=child.class_name,
                page_number=index + 1,
                page_title=_page_title(child),
            )
        )
    return tuple(found)


def _tabstop_edges(doc: UiDocument, node: Node) -> Tuple[NameUse, ...]:
    del doc
    if node.kind != "ui":
        return ()
    return tuple(NameUse(node.id, "tabstop", name) for name in _names_in(node.field("tabstops")))


def _zorder_edges(doc: UiDocument, node: Node) -> Tuple[NameUse, ...]:
    del doc
    if node.kind != "widget":
        return ()
    return tuple(NameUse(node.id, "zorder", name) for name in _names_in(node.field("zorder")))


def _menu_edges(doc: UiDocument, node: Node) -> Tuple[NameUse, ...]:
    del doc
    if node.kind != "action":
        return ()
    target = _field_str(node, "menu")
    if not target:
        return ()
    return (NameUse(node.id, "action.menu", target),)


def _addaction_edges(doc: UiDocument, node: Node) -> Tuple[NameUse, ...]:
    del doc
    if node.kind != "actionref":
        return ()
    target = _field_str(node, "name")
    if not target:
        return ()
    return (NameUse(node.id, "addaction", target),)


def _group_edges(doc: UiDocument, node: Node) -> Tuple[NameUse, ...]:
    del doc
    if node.kind != "widget":
        return ()
    target = _entry_text(node, "attribute", "buttonGroup")
    if not target:
        return ()
    return (NameUse(node.id, "buttonGroup", target),)


ROLES: Tuple[Role, ...] = (
    Role("buddy", True, _buddy_edges),
    Role("connection.sender", True, _connection_edges("sender")),
    Role("connection.receiver", True, _connection_edges("receiver")),
    Role("promoted_page", True, _promoted_edges),
    Role("tabstop", False, _tabstop_edges),
    Role("zorder", False, _zorder_edges),
    Role("action.menu", False, _menu_edges),
    Role("addaction", False, _addaction_edges),
    Role("buttonGroup", False, _group_edges),
)

_ASKING = frozenset(role.name for role in ROLES if role.asks)


def _edges(doc: UiDocument, node: Node) -> Tuple[NameUse, ...]:
    found: List[NameUse] = []
    for role in ROLES:
        found.extend(role.edges_on(doc, node))
    return tuple(found)


class RefIndex:
    """Derived edges. The session listener is the only writer during editing."""

    def __init__(self) -> None:
        self._by_name: Dict[str, List[_Hit]] = {}
        self._by_owner: Dict[NodeId, List[_Hit]] = {}
        self._by_producer: Dict[NodeId, List[_Hit]] = {}

    def rebuild(self, doc: UiDocument) -> None:
        """Full scan. Open and ``DocumentReplaced`` only."""
        self._by_name.clear()
        self._by_owner.clear()
        self._by_producer.clear()
        for node in doc.iter_preorder():
            produced = _edges(doc, node)
            if produced:
                self._store(node.id, produced)

    def apply(self, doc: UiDocument, change_set: ChangeSet) -> None:
        """Patch from one committed changeset.

        Reads the edges back off the document. A shared name is not rewritten,
        so stamping the rename onto every edge would disagree with the file.
        """
        if change_set.replaced:
            self.rebuild(doc)
            return
        producers = _touched(change_set)
        _expand_hosts(doc, producers, change_set.removed)
        for old, _new in change_set.renamed:
            producers.update(self._producers_targeting(old))
        for producer in producers:
            self._drop_producer(producer)
        for node_id in change_set.removed:
            self._drop_owner(node_id)
        removed = change_set.removed
        for producer in producers:
            if producer in removed or not doc.contains(producer):
                continue
            node = doc.get(producer)
            if node is None:
                continue
            produced = _edges(doc, node)
            if produced:
                self._store(producer, produced)

    def uses(self, name: str) -> Tuple[NameUse, ...]:
        """Edges whose target is ``name``. Empty when the name is unknown."""
        hits = self._by_name.get(name)
        if not hits:
            return ()
        return tuple(hit.use for hit in hits)

    def confirmable(self, name: str) -> Tuple[NameUse, ...]:
        """Buddy, connection, and promoted-page edges. Tab stops are absent."""
        return tuple(use for use in self.uses(name) if use.role in _ASKING)

    def targeted_names(self) -> Tuple[str, ...]:
        return tuple(self._by_name)

    def ask_sentence(self, doc: UiDocument, name: str, participants: Sequence[object]) -> str:
        """Empty when delete should run at once, including a tab-stop-only name."""
        lines = tuple(
            speak_participant(doc, owner, prop) for owner, prop in participant_pairs(doc, name, participants)
        )
        return confirm_prose(doc, name, self.confirmable(name), lines)

    def _store(self, producer: NodeId, uses: Tuple[NameUse, ...]) -> None:
        hits: List[_Hit] = []
        for use in uses:
            hit = _Hit(use, producer)
            hits.append(hit)
            self._by_name.setdefault(use.target, []).append(hit)
            self._by_owner.setdefault(use.owner, []).append(hit)
        self._by_producer[producer] = hits

    def _drop_producer(self, producer: NodeId) -> None:
        for hit in list(self._by_producer.get(producer, ())):
            self._unlink(hit)

    def _drop_owner(self, owner: NodeId) -> None:
        for hit in list(self._by_owner.get(owner, ())):
            self._unlink(hit)

    def _unlink(self, hit: _Hit) -> None:
        _remove(self._by_name, hit.use.target, hit)
        _remove(self._by_owner, hit.use.owner, hit)
        _remove(self._by_producer, hit.producer, hit)

    def _producers_targeting(self, name: str) -> Set[NodeId]:
        return {hit.producer for hit in self._by_name.get(name, ())}


def _remove(table: Dict[object, List[_Hit]], key: object, hit: _Hit) -> None:
    bucket = table.get(key)
    if not bucket:
        return
    kept = [item for item in bucket if item is not hit]
    if kept:
        table[key] = kept
    else:
        del table[key]


def _touched(change_set: ChangeSet) -> Set[NodeId]:
    found: Set[NodeId] = set(change_set.removed)
    found.update(change_set.added)
    found.update(change_set.structure_dirty)
    for owner, _kind, _name in change_set.property_dirty:
        found.add(owner)
    for change in change_set.changes:
        for attr in ("node", "owner", "old_parent", "new_parent", "parent"):
            value = getattr(change, attr, None)
            if value is not None:
                found.add(value)
    return found


def _expand_hosts(doc: UiDocument, producers: Set[NodeId], removed: Iterable[NodeId]) -> None:
    extra = []
    for node_id in producers:
        if node_id in removed or not doc.contains(node_id):
            continue
        parent = doc.parent(node_id)
        if isinstance(parent, WidgetNode) and _is_page_host(doc, parent):
            extra.append(parent.id)
    producers.update(extra)


def participant_pairs(
    doc: UiDocument,
    name: str,
    participants: Sequence[object],
) -> Tuple[Tuple[NodeId, str], ...]:
    """``RenameParticipant.references`` pairs. Delete participants are skipped."""
    found: List[Tuple[NodeId, str]] = []
    for participant in participants:
        references = getattr(participant, "references", None)
        if not callable(references):
            continue
        reported = references(doc, name)
        if not isinstance(reported, tuple):
            continue
        for pair in reported:
            if isinstance(pair, tuple) and len(pair) == 2:
                found.append((pair[0], pair[1]))
    return tuple(found)


def confirm_prose(
    doc: UiDocument,
    name: str,
    uses: Sequence[NameUse],
    participant_lines: Sequence[str],
) -> str:
    """``email is used by: the buddy of “Email:”, 1 connection (...)``."""
    parts: List[str] = []
    buddies = tuple(use for use in uses if use.role == "buddy")
    if buddies:
        parts.append(_speak_buddies(doc, buddies))
    connections = tuple(use for use in uses if use.role.startswith("connection."))
    if connections:
        spoken = _speak_connections(doc, connections)
        if spoken:
            parts.append(spoken)
    promoted = tuple(use for use in uses if use.role == "promoted_page")
    if promoted:
        parts.append(_speak_promoted(promoted))
    for line in participant_lines:
        if line:
            parts.append(line)
    if not parts:
        return ""
    return "%s is used by: %s" % (name, ", ".join(parts))


def speak_participant(doc: UiDocument, owner: NodeId, prop: str) -> str:
    """``a rule on “Email:” (cbcsValidate)``. M6 replaces this by registering."""
    return "a rule on %s (%s)" % (_quoted(_visible_text(doc.get(owner))), prop)


def _speak_buddies(doc: UiDocument, uses: Sequence[NameUse]) -> str:
    return ", ".join("the buddy of %s" % _quoted(_visible_text(doc.get(use.owner))) for use in uses)


def _speak_connections(doc: UiDocument, uses: Sequence[NameUse]) -> str:
    phrases: List[str] = []
    seen = set()
    for use in uses:
        if use.owner in seen:
            continue
        seen.add(use.owner)
        phrase = _connection_phrase(doc, use.owner)
        if phrase:
            phrases.append(phrase)
    if not phrases:
        return ""
    noun = "connection" if len(phrases) == 1 else "connections"
    return "%d %s (%s)" % (len(phrases), noun, "; ".join(phrases))


def _speak_promoted(uses: Sequence[NameUse]) -> str:
    parts = []
    for use in uses:
        if use.page_title:
            parts.append(
                "promoted class %s (page %d \u00b7 %s)" % (use.promoted_class, use.page_number, use.page_title)
            )
        else:
            parts.append("promoted class %s (page %d)" % (use.promoted_class, use.page_number))
    return ", ".join(parts)


def _connection_phrase(doc: UiDocument, owner: NodeId) -> str:
    node = doc.get(owner)
    if node is None or node.kind != "connection":
        return ""
    return "%s \u00b7 %s \u2192 %s \u00b7 %s" % (
        _field_str(node, "sender"),
        _signature_name(_field_str(node, "signal")),
        _field_str(node, "receiver"),
        _signature_name(_field_str(node, "slot")),
    )


def _signature_name(signature: str) -> str:
    return signature.split("(", 1)[0]


def _quoted(text: str) -> str:
    return "\u201c%s\u201d" % text


def _visible_text(node: Optional[Node]) -> str:
    if node is None:
        return ""
    for key in ("text", "title", "windowTitle", "plainText"):
        text = _entry_text(node, "property", key)
        if text:
            return text
    titled = _entry_text(node, "attribute", "title")
    if titled:
        return titled
    named = identity_name(node)
    return named or ""
