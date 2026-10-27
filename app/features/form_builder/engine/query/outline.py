"""Outline forest and the one gesture policy.

Rows are a pre-order spine. ``plan`` turns a key, drop, rename, filter, or
delete into an effect. The binder performs the effect. The engine stays free
of Qt.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Dict, FrozenSet, List, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.commands.catalog import DeleteNodes, MoveNodes, MovePage, SetProperty
from app.features.form_builder.engine.commands.catalog_ext.drop import AdoptIntoBox
from app.features.form_builder.engine.commands.drop_plan import auto_target, commands_for, nudge_commands
from app.features.form_builder.engine.commands.placement import InBoxLayout, InContainer
from app.features.form_builder.engine.events import ChangeSet, FieldChanged
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.drop_target import (
    AcceptedDrop,
    DropPayload,
    NoDrop,
    OutlineRow as PixelRow,
    RefusedDrop,
    resolve_outline,
)
from app.features.form_builder.engine.query.name_policy import explain_name
from app.features.form_builder.engine.query.ref_index import RefIndex
from app.features.form_builder.engine.query.tree import is_container
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import (
    LayoutItemNode,
    LayoutNode,
    Node,
    SpacerNode,
    WidgetNode,
)
from app.features.form_builder.engine.ui4.values import BoolValue, CStringValue, NumberValue, StringValue

PAGE_HOSTS = frozenset({"QTabWidget", "QStackedWidget", "QToolBox"})

_NOWHERE = "Nothing above to nest into"
_KEEP_PAGE = "A page stays inside its container."
_KEEP_FORM = "The form itself cannot be deleted."
_CAPTION_PROPS = frozenset({"text", "title", "windowTitle", "plainText", "visible"})
_CAPTION_ATTRS = frozenset({"title", "label"})
_CLIPBOARD = frozenset(
    {
        "form.action.cut",
        "form.action.copy",
        "form.action.paste",
        "form.action.duplicate",
    }
)
_ARROWS = {
    "form.action.outlineMoveUp": "up",
    "form.action.outlineMoveDown": "down",
    "form.action.outlineMoveLeft": "left",
    "form.action.outlineMoveRight": "right",
}
_REORDER = {
    "form.action.moveOrNudgeUp": "up",
    "form.action.moveOrNudgeDown": "down",
}
_HANDLED = frozenset(
    {
        "form.action.rename",
        "form.action.find",
        "form.action.insert",
        "form.action.delete",
        "form.action.backspace",
        "form.action.outlineNest",
        "form.action.outlineUnnest",
        "form.action.escape",
        *_CLIPBOARD,
        *_ARROWS,
        *_REORDER,
    }
)
_ROW_H = 24
_GLYPH = 16
_GAP = 4
_NAME_FLOOR = 24


@dataclass(frozen=True)
class InLayoutSlot:
    layout: NodeId
    layout_class: str
    index: int


@dataclass(frozen=True)
class InPageSlot:
    container: NodeId
    index: int


@dataclass(frozen=True)
class InBareSlot:
    container: NodeId
    index: int


Slot = Union[InLayoutSlot, InPageSlot, InBareSlot]


@dataclass(frozen=True)
class Row:
    """One outline row. Identity is ``node``. Caption fields change without a new item."""

    node: NodeId
    parent: Optional[NodeId]
    depth: int
    sibling_index: int
    kind: str
    tone: str
    name: str
    primary: str
    friendly: str
    qt_class: str
    visible_text: str
    hidden: bool
    problem: bool
    container: bool
    slot: Slot


class OutlineForest:
    """Pre-order rows. ``index`` is the row position of a node."""

    def __init__(self, rows: Tuple[Row, ...]) -> None:
        self.rows = rows
        self.index: Dict[NodeId, int] = {row.node: position for position, row in enumerate(rows)}

    def row(self, node: NodeId) -> Optional[Row]:
        position = self.index.get(node)
        if position is None:
            return None
        return self.rows[position]

    def children(self, node: Optional[NodeId]) -> Tuple[Row, ...]:
        """Direct child rows, sibling order. ``None`` is the root list."""
        return tuple(row for row in self.rows if row.parent == node)

    def next_visible(
        self,
        node: NodeId,
        mask: "FilterMask",
        expanded: FrozenSet[NodeId],
    ) -> Optional[NodeId]:
        order = _visible_order(self, mask, expanded)
        if node not in order:
            return order[0] if order else None
        position = order.index(node)
        if position + 1 >= len(order):
            return None
        return order[position + 1]

    def prev_visible(
        self,
        node: NodeId,
        mask: "FilterMask",
        expanded: FrozenSet[NodeId],
    ) -> Optional[NodeId]:
        order = _visible_order(self, mask, expanded)
        if node not in order:
            return order[-1] if order else None
        position = order.index(node)
        if position == 0:
            return None
        return order[position - 1]


@dataclass(frozen=True)
class OutlineCursor:
    """View state for one plan call.

    ``expanded`` holds collapsed rows. A missing id stays open, so a row that
    appears later starts open. ``selected`` is a copy of the selection model's
    ids. The model stays the owner.
    """

    anchor: Optional[NodeId] = None
    focus: Optional[NodeId] = None
    expanded: FrozenSet[NodeId] = frozenset()
    filter_text: str = ""
    renaming: Optional[NodeId] = None
    selected: Tuple[NodeId, ...] = ()


@dataclass(frozen=True)
class OutlineWorld:
    index: RefIndex
    base_methods: FrozenSet[str] = frozenset()
    problems: FrozenSet[NodeId] = frozenset()
    participants: Tuple[object, ...] = ()
    friendly_of: Callable[[str], str] = lambda name: name


@dataclass(frozen=True)
class KeyGesture:
    command_id: str = ""
    key: str = ""
    shift: bool = False
    alt: bool = False
    text: str = ""


@dataclass(frozen=True)
class DropGesture:
    x: int
    y: int
    release: bool
    payload: DropPayload
    rows: Tuple[PixelRow, ...]
    indent: int = 20
    blocked: FrozenSet[NodeId] = frozenset()


@dataclass(frozen=True)
class RenameGesture:
    node: NodeId
    text: str
    how: str


@dataclass(frozen=True)
class FilterGesture:
    text: str
    how: str


@dataclass(frozen=True)
class InsertGesture:
    after: Optional[NodeId]


@dataclass(frozen=True)
class ConfirmGesture:
    """Delete button of the reference popover. Cancel is accept False."""

    ids: Tuple[NodeId, ...]
    accept: bool


Gesture = Union[KeyGesture, DropGesture, RenameGesture, FilterGesture, InsertGesture, ConfirmGesture]


@dataclass(frozen=True)
class Commit:
    commands: Tuple[object, ...]
    label: str
    toast: str = ""


@dataclass(frozen=True)
class BareNest:
    """``ApplyLayout`` allocates the layout id, so the commands are not known yet.

    ``plan`` chooses ``layout_class``. The binder runs one transaction.
    """

    container: NodeId
    ids: Tuple[NodeId, ...]
    layout_class: str


@dataclass(frozen=True)
class Navigate:
    ids: Tuple[NodeId, ...]
    current: NodeId
    anchor: NodeId


@dataclass(frozen=True)
class Expand:
    node: NodeId
    expanded: bool
    select_child: bool


@dataclass(frozen=True)
class AskDelete:
    prose: str
    ids: Tuple[NodeId, ...]


@dataclass(frozen=True)
class Route:
    action_id: str


@dataclass(frozen=True)
class OpenInsert:
    after: Optional[NodeId]


@dataclass(frozen=True)
class EditName:
    node: NodeId


@dataclass(frozen=True)
class CloseName:
    """Cancel, or commit then maybe open the next row. ``then_node`` None keeps the row."""

    node: NodeId
    new_name: Optional[str]
    then_node: Optional[NodeId]


@dataclass(frozen=True)
class NameInvalid:
    prose: str


@dataclass(frozen=True)
class FilterSet:
    text: str
    focus_tree: bool
    select: Optional[NodeId]


@dataclass(frozen=True)
class DropCue:
    x: int
    y: int
    width: int
    height: int
    into: bool
    prose: str


@dataclass(frozen=True)
class Flash:
    node: NodeId
    prose: str


@dataclass(frozen=True)
class Idle:
    pass


Effect = Union[
    Commit,
    BareNest,
    Navigate,
    Expand,
    AskDelete,
    Route,
    OpenInsert,
    EditName,
    CloseName,
    NameInvalid,
    FilterSet,
    DropCue,
    Flash,
    Idle,
]


def project(
    doc: UiDocument,
    problems: FrozenSet[NodeId],
    friendly_of: Callable[[str], str],
) -> OutlineForest:
    """Pre-order rows. Layout items are not rows. O(form)."""
    found: List[Row] = []

    def walk(node: Node, depth: int, parent: Optional[NodeId]) -> None:
        if not _is_row(node):
            for child in _slot_children(node):
                walk(child, depth, parent)
            return
        sibling_index = sum(1 for row in found if row.parent == parent)
        found.append(_make_row(doc, node, parent, depth, sibling_index, problems, friendly_of))
        for child in _slot_children(node):
            walk(child, depth + 1, node.id)

    walk(doc.ui, 0, None)
    return OutlineForest(tuple(found))


def patch_captions(
    forest: OutlineForest,
    doc: UiDocument,
    nodes: Tuple[NodeId, ...],
    problems: FrozenSet[NodeId],
    friendly_of: Callable[[str], str],
) -> OutlineForest:
    """Replace caption fields of ``nodes`` that are rows. Same row objects elsewhere."""
    wanted = set(nodes)
    rows: List[Row] = []
    changed = False
    for row in forest.rows:
        if row.node not in wanted or not doc.contains(row.node):
            rows.append(row)
            continue
        updated = _retitle(row, doc, doc.node(row.node), problems, friendly_of)
        if updated != row:
            changed = True
            rows.append(updated)
        else:
            rows.append(row)
    if not changed:
        return forest
    return OutlineForest(tuple(rows))


def captions_touched(change_set: ChangeSet) -> Tuple[NodeId, ...]:
    """Ids whose outline caption may have changed. Renames included."""
    found: List[NodeId] = []
    for owner, kind, name in change_set.property_dirty:
        if kind == "property" and name in _CAPTION_PROPS:
            found.append(owner)
        elif kind == "attribute" and name in _CAPTION_ATTRS:
            found.append(owner)
    for change in change_set.changes:
        if isinstance(change, FieldChanged) and change.field in ("object_name", "name"):
            found.append(change.node)
    return tuple(dict.fromkeys(found))


def structure_touched(change_set: ChangeSet) -> bool:
    """Replaced, added, removed, or a parent whose children changed."""
    return bool(change_set.replaced or change_set.added or change_set.removed or change_set.structure_dirty)


@dataclass(frozen=True)
class FilterMask:
    query: str
    state: Tuple[Tuple[NodeId, str], ...]
    first_match: Optional[NodeId]
    empty: bool


def filter_mask(forest: OutlineForest, query: str) -> FilterMask:
    """Case-insensitive substring of name, friendly class, Qt class, and visible text.

    An empty query matches every row. Ancestors of a match stay, marked
    ``ancestor`` when they do not match themselves.
    """
    if not query:
        state = tuple((row.node, "match") for row in forest.rows)
        first = forest.rows[0].node if forest.rows else None
        return FilterMask(query, state, first, False)
    needle = query.casefold()
    matched = set()
    for row in forest.rows:
        haystack = "\n".join((row.name, row.friendly, row.qt_class, row.visible_text)).casefold()
        if needle in haystack:
            matched.add(row.node)
    ancestors = set()
    for node in matched:
        current = forest.row(node)
        parent = None if current is None else current.parent
        while parent is not None:
            if parent not in matched:
                ancestors.add(parent)
            parent_row = forest.row(parent)
            parent = None if parent_row is None else parent_row.parent
    state_list: List[Tuple[NodeId, str]] = []
    for row in forest.rows:
        if row.node in matched:
            state_list.append((row.node, "match"))
        elif row.node in ancestors:
            state_list.append((row.node, "ancestor"))
        else:
            state_list.append((row.node, "hidden"))
    first = next((node for node, kind in state_list if kind == "match"), None)
    return FilterMask(query, tuple(state_list), first, first is None)


@dataclass(frozen=True)
class RowBoxes:
    """Pixel boxes inside the item rect. Pairwise disjoint, each inside the width."""

    glyph: Tuple[int, int, int, int]
    name: Tuple[int, int, int, int]
    caption: Optional[Tuple[int, int, int, int]]
    problem: Optional[Tuple[int, int, int, int]]
    name_elides: bool


def layout_row(item_width: int, has_caption: bool, has_problem: bool) -> RowBoxes:
    """24 px row. Glyph 16. Gaps 4. Problem glyph 16 at the right.

    The caption is omitted when the name would have under 24 px. The name
    takes what remains. The delegate elides that box in the middle.
    """
    width = max(int(item_width), 0)
    glyph_w = min(_GLYPH, width)
    glyph = (0, 4, glyph_w, _GLYPH)
    right = width
    problem: Optional[Tuple[int, int, int, int]] = None
    if has_problem and width - glyph_w >= _GLYPH:
        problem = (width - _GLYPH, 4, _GLYPH, _GLYPH)
        right = width - _GLYPH - _GAP
    left = glyph_w + (_GAP if glyph_w and right > glyph_w else 0)
    if left > right:
        left = right
    room = max(right - left, 0)
    caption: Optional[Tuple[int, int, int, int]] = None
    name_w = room
    if has_caption and room >= _NAME_FLOOR + _GAP + 8:
        caption_w = min(room // 3, room - _NAME_FLOOR - _GAP)
        if caption_w >= 8 and room - _GAP - caption_w >= _NAME_FLOOR:
            name_w = room - _GAP - caption_w
            caption = (left + name_w + _GAP, 4, caption_w, _GLYPH)
    name = (left, 4, name_w, _GLYPH)
    return RowBoxes(glyph, name, caption, problem, name_w < 80)


def plan(
    doc: UiDocument,
    forest: OutlineForest,
    cursor: OutlineCursor,
    gesture: Gesture,
    world: OutlineWorld,
) -> Effect:
    """One policy for keys, drops, rename, filter, and delete."""
    if isinstance(gesture, KeyGesture):
        return _plan_key(doc, forest, cursor, gesture, world)
    if isinstance(gesture, RenameGesture):
        return _plan_rename(doc, forest, cursor, gesture, world)
    if isinstance(gesture, FilterGesture):
        return _plan_filter(forest, gesture)
    if isinstance(gesture, InsertGesture):
        return OpenInsert(gesture.after)
    if isinstance(gesture, ConfirmGesture):
        return _plan_confirm(forest, gesture)
    if isinstance(gesture, DropGesture):
        return _plan_drop(doc, forest, gesture)
    return Idle()


def _plan_key(
    doc: UiDocument,
    forest: OutlineForest,
    cursor: OutlineCursor,
    gesture: KeyGesture,
    world: OutlineWorld,
) -> Effect:
    command = gesture.command_id
    if command and command not in _HANDLED:
        return Idle()
    focus = cursor.focus
    row = None if focus is None else forest.row(focus)
    if command == "form.action.rename" or gesture.key == "f2":
        if row is None or not row.name:
            return Idle()
        return EditName(row.node)
    if command == "form.action.find":
        return FilterSet(cursor.filter_text, False, None)
    if command in _CLIPBOARD:
        return Route(command)
    if command in ("form.action.delete", "form.action.backspace") or gesture.key in ("delete", "backspace"):
        return _plan_delete(doc, forest, cursor, world)
    if command == "form.action.outlineUnnest" or gesture.key == "backtab" or (
        gesture.key == "tab" and gesture.shift and command != "form.action.outlineNest"
    ):
        return _unnest(doc, forest, cursor)
    if command == "form.action.outlineNest" or gesture.key == "tab":
        return _nest(doc, forest, cursor)
    if command == "form.action.insert" or gesture.key == "slash":
        return OpenInsert(focus)
    direction = _REORDER.get(command, _ARROWS.get(command, gesture.key))
    if (gesture.alt or command in _REORDER) and direction in ("up", "down"):
        return _reorder(doc, forest, cursor, direction)
    if gesture.shift and direction in ("up", "down"):
        return _shift(forest, cursor, -1 if direction == "up" else 1)
    if direction == "up":
        return _move_visible(forest, cursor, False)
    if direction == "down":
        return _move_visible(forest, cursor, True)
    if direction == "left":
        return _collapse_or_parent(forest, cursor)
    if direction == "right":
        return _expand_or_child(forest, cursor, False)
    if gesture.key == "home":
        return _ends(forest, cursor, False)
    if gesture.key == "end":
        return _ends(forest, cursor, True)
    if gesture.key == "enter":
        return _expand_or_child(forest, cursor, True)
    if command == "form.action.escape" or gesture.key == "esc":
        return _parent(forest, cursor)
    return Idle()


def _plan_rename(
    doc: UiDocument,
    forest: OutlineForest,
    cursor: OutlineCursor,
    gesture: RenameGesture,
    world: OutlineWorld,
) -> Effect:
    row = forest.row(gesture.node)
    if row is None:
        return Idle()
    if gesture.how == "cancel":
        return CloseName(gesture.node, None, None)
    current = row.name
    taken = frozenset(name for name in doc.names() if name != current)
    refusal = explain_name(gesture.text, taken, world.base_methods, current)
    if refusal is not None:
        return NameInvalid(refusal.prose)
    then: Optional[NodeId] = None
    if gesture.how in ("next", "prev"):
        mask = filter_mask(forest, cursor.filter_text)
        step = forest.next_visible if gesture.how == "next" else forest.prev_visible
        then = step(gesture.node, mask, cursor.expanded)
    new_name = None if gesture.text == current else gesture.text
    return CloseName(gesture.node, new_name, then)


def _plan_filter(forest: OutlineForest, gesture: FilterGesture) -> Effect:
    if gesture.how == "clear":
        return FilterSet("", True, None)
    mask = filter_mask(forest, gesture.text)
    if gesture.how == "enter":
        return FilterSet(gesture.text, False, mask.first_match)
    return FilterSet(gesture.text, False, None)


def _plan_confirm(forest: OutlineForest, gesture: ConfirmGesture) -> Effect:
    if not gesture.accept:
        return Idle()
    return Commit((DeleteNodes(gesture.ids),), "Delete", _toast(forest, gesture.ids))


def _plan_delete(
    doc: UiDocument,
    forest: OutlineForest,
    cursor: OutlineCursor,
    world: OutlineWorld,
) -> Effect:
    focus = cursor.focus
    if focus is None:
        return Idle()
    ids = _delete_ids(forest, cursor)
    ids = tuple(node for node in ids if node != doc.root.id)
    if not ids:
        return Flash(focus, _KEEP_FORM)
    names = []
    for node in ids:
        row = forest.row(node)
        names.append(row.name if row is not None else "")
    if any(name and len(doc.by_name(name)) > 1 for name in names):
        return Commit((DeleteNodes(ids),), "Delete", _toast(forest, ids))
    prose = []
    for name in names:
        if not name:
            continue
        sentence = world.index.ask_sentence(doc, name, world.participants)
        if sentence:
            prose.append(sentence)
    if prose:
        return AskDelete(" ".join(prose), ids)
    return Commit((DeleteNodes(ids),), "Delete", _toast(forest, ids))


def _nest(doc: UiDocument, forest: OutlineForest, cursor: OutlineCursor) -> Effect:
    focus = cursor.focus
    if focus is None or forest.row(focus) is None:
        return Idle()
    block = _sibling_block(forest, cursor, focus)
    if block is None:
        return Flash(focus, _NOWHERE)
    previous = _previous_sibling(forest, block[0])
    if previous is None or not (previous.container or previous.kind == "layout"):
        return Flash(focus, _NOWHERE)
    ids = tuple(row.node for row in block)
    node = doc.get(previous.node)
    has_layout = isinstance(node, LayoutNode) or (isinstance(node, WidgetNode) and node.layout is not None)
    if previous.kind == "layout" or has_layout or (isinstance(node, WidgetNode) and _page_host(doc, node)):
        payload = DropPayload("widget", ids)
        target = auto_target(doc, previous.node, payload)
        commands = commands_for(doc, target, payload, None) if target is not None else ()
        if not commands:
            return Flash(focus, _NOWHERE)
        return Commit(tuple(commands), "Nest")
    if isinstance(node, WidgetNode) and is_container(doc, node.id) and not node.child_widgets:
        return Commit((AdoptIntoBox(previous.node, existing=ids),), "Nest")
    if isinstance(node, WidgetNode) and is_container(doc, node.id):
        return BareNest(previous.node, ids, "QVBoxLayout")
    return Flash(focus, _NOWHERE)


def _unnest(doc: UiDocument, forest: OutlineForest, cursor: OutlineCursor) -> Effect:
    focus = cursor.focus
    if focus is None or forest.row(focus) is None:
        return Idle()
    block = _sibling_block(forest, cursor, focus)
    if block is None:
        return Flash(focus, _NOWHERE)
    parent_id = block[0].parent
    if parent_id is None:
        return Flash(focus, _NOWHERE)
    parent = doc.get(parent_id)
    ids = tuple(row.node for row in block)
    if isinstance(parent, LayoutNode):
        return _unnest_layout(doc, focus, parent, ids)
    if (
        isinstance(parent, WidgetNode)
        and _page_host(doc, parent)
        and all(isinstance(row.slot, InPageSlot) for row in block)
    ):
        return _unnest_pages(doc, focus, parent, block)
    if isinstance(parent, WidgetNode):
        return _after_widget(doc, focus, parent, ids, "Un-nest")
    return Flash(focus, _NOWHERE)


def _unnest_layout(doc: UiDocument, focus: NodeId, layout: LayoutNode, ids: Tuple[NodeId, ...]) -> Effect:
    owner = layout.owner_widget_id()
    if owner is None:
        item = doc.parent(layout.id)
        if not isinstance(item, LayoutItemNode):
            return Flash(focus, _NOWHERE)
        grand = doc.parent(item.id)
        if not isinstance(grand, LayoutNode):
            return Flash(focus, _NOWHERE)
        return Commit((MoveNodes(ids, InBoxLayout(grand.id, item.slot_index + 1)),), "Un-nest")
    widget = doc.get(owner)
    if not isinstance(widget, WidgetNode):
        return Flash(focus, _NOWHERE)
    return _after_widget(doc, focus, widget, ids, "Un-nest")


def _unnest_pages(doc: UiDocument, focus: NodeId, host: WidgetNode, block: Tuple[Row, ...]) -> Effect:
    moved = _after_widget(doc, focus, host, tuple(row.node for row in block), "Un-nest")
    if not isinstance(moved, Commit):
        return moved
    current = _current_index(host)
    removed = sorted(row.slot.index for row in block if isinstance(row.slot, InPageSlot))
    remaining = len(host.child_widgets) - len(removed)
    shift = sum(1 for index in removed if index <= current)
    new_index = current - shift
    if remaining <= 0:
        new_index = 0
    else:
        new_index = max(0, min(new_index, remaining - 1))
    commands = list(moved.commands)
    if new_index != current:
        commands.append(SetProperty(host.id, "currentIndex", NumberValue(new_index)))
    return Commit(tuple(commands), "Un-nest")


def _after_widget(
    doc: UiDocument,
    focus: NodeId,
    widget: WidgetNode,
    ids: Tuple[NodeId, ...],
    label: str,
) -> Effect:
    if widget.id == doc.root.id:
        return Flash(focus, _NOWHERE)
    parent = doc.parent(widget.id)
    if isinstance(parent, LayoutItemNode):
        layout = doc.parent(parent.id)
        if isinstance(layout, LayoutNode):
            return Commit((MoveNodes(ids, InBoxLayout(layout.id, parent.slot_index + 1)),), label)
    if isinstance(parent, WidgetNode):
        return Commit((MoveNodes(ids, InContainer(parent.id, _widget_index(parent, widget.id) + 1)),), label)
    return Flash(focus, _NOWHERE)


def _reorder(doc: UiDocument, forest: OutlineForest, cursor: OutlineCursor, direction: str) -> Effect:
    focus = cursor.focus
    row = None if focus is None else forest.row(focus)
    if row is None:
        return Idle()
    slot = row.slot
    if isinstance(slot, InPageSlot):
        delta = -1 if direction == "up" else 1
        destination = slot.index + delta
        host = doc.get(slot.container)
        count = len(host.child_widgets) if isinstance(host, WidgetNode) else 0
        if destination < 0 or destination >= count:
            return Idle()
        return Commit((MovePage(slot.container, slot.index, destination),), "Move page")
    if isinstance(slot, InLayoutSlot):
        sharing = _layout_selection(forest, cursor, slot.layout)
        commands = nudge_commands(doc, sharing, direction)
        if not commands:
            return Idle()
        return Commit(tuple(commands), "Move")
    return Idle()


def _plan_drop(doc: UiDocument, forest: OutlineForest, gesture: DropGesture) -> Effect:
    target = resolve_outline(
        doc,
        gesture.rows,
        gesture.y,
        gesture.payload,
        gesture.blocked,
        x=gesture.x,
        indent=gesture.indent,
    )
    page = _dragged_page(forest, gesture.payload.source_ids)
    if not gesture.release:
        if isinstance(target, AcceptedDrop):
            rect = target.indicator.rect
            return DropCue(rect.x, rect.y, rect.width, rect.height, target.indicator.dashed, target.sentence)
        return Idle()
    if page is not None:
        return _drop_page(doc, page, target)
    if isinstance(target, AcceptedDrop):
        commands = commands_for(doc, target, gesture.payload, None)
        if commands:
            return Commit(tuple(commands), "Move")
        return _drop_flash(forest, gesture, target.sentence)
    if isinstance(target, RefusedDrop):
        return _drop_flash(forest, gesture, target.sentence)
    return Idle()


def _drop_page(doc: UiDocument, row: Row, target: object) -> Effect:
    slot = row.slot
    if not isinstance(slot, InPageSlot):
        return Flash(row.node, _KEEP_PAGE)
    host = doc.get(slot.container)
    count = len(host.child_widgets) if isinstance(host, WidgetNode) else 0
    if isinstance(target, AcceptedDrop) and target.host == slot.container and target.action in ("splitter", "pages"):
        insert = target.index
        if insert > slot.index:
            insert -= 1
        if insert < 0 or insert >= count or insert == slot.index:
            return Idle()
        return Commit((MovePage(slot.container, slot.index, insert),), "Move page")
    if isinstance(target, NoDrop):
        return Idle()
    return Flash(row.node, _KEEP_PAGE)


def _shift(forest: OutlineForest, cursor: OutlineCursor, delta: int) -> Effect:
    anchor = cursor.anchor or cursor.focus
    focus = cursor.focus or anchor
    if anchor is None or focus is None:
        return Idle()
    anchor_row = forest.row(anchor)
    if anchor_row is None:
        return Idle()
    siblings = forest.children(anchor_row.parent)
    ids = [row.node for row in siblings]
    if anchor not in ids:
        return Idle()
    moving = ids.index(focus) if focus in ids else ids.index(anchor)
    nxt = moving + delta
    if nxt < 0 or nxt >= len(ids):
        return Idle()
    start, end = sorted((ids.index(anchor), nxt))
    return Navigate(tuple(ids[start : end + 1]), ids[nxt], anchor)


def _move_visible(forest: OutlineForest, cursor: OutlineCursor, forward: bool) -> Effect:
    focus = cursor.focus
    if focus is None:
        return Idle()
    mask = filter_mask(forest, cursor.filter_text)
    nxt = forest.next_visible(focus, mask, cursor.expanded) if forward else forest.prev_visible(focus, mask, cursor.expanded)
    if nxt is None:
        return Idle()
    return Navigate((nxt,), nxt, nxt)


def _collapse_or_parent(forest: OutlineForest, cursor: OutlineCursor) -> Effect:
    focus = cursor.focus
    row = None if focus is None else forest.row(focus)
    if row is None:
        return Idle()
    if focus not in cursor.expanded and forest.children(focus):
        return Expand(focus, False, False)
    if row.parent is None:
        return Idle()
    return Navigate((row.parent,), row.parent, row.parent)


def _expand_or_child(forest: OutlineForest, cursor: OutlineCursor, select_child: bool) -> Effect:
    focus = cursor.focus
    if focus is None:
        return Idle()
    kids = forest.children(focus)
    if not kids:
        return Idle()
    if focus in cursor.expanded:
        return Expand(focus, True, select_child)
    return Navigate((kids[0].node,), kids[0].node, kids[0].node)


def _parent(forest: OutlineForest, cursor: OutlineCursor) -> Effect:
    focus = cursor.focus
    row = None if focus is None else forest.row(focus)
    if row is None or row.parent is None:
        return Idle()
    return Navigate((row.parent,), row.parent, row.parent)


def _ends(forest: OutlineForest, cursor: OutlineCursor, last: bool) -> Effect:
    mask = filter_mask(forest, cursor.filter_text)
    order = _visible_order(forest, mask, cursor.expanded)
    if not order:
        return Idle()
    node = order[-1] if last else order[0]
    return Navigate((node,), node, node)


def _visible_order(forest: OutlineForest, mask: FilterMask, collapsed: FrozenSet[NodeId]) -> List[NodeId]:
    hidden = {node for node, state in mask.state if state == "hidden"}
    order: List[NodeId] = []
    closed: Optional[int] = None
    for row in forest.rows:
        if closed is not None:
            if row.depth > closed:
                continue
            closed = None
        if row.node in hidden:
            continue
        order.append(row.node)
        if row.node in collapsed:
            closed = row.depth
    return order


def _sibling_block(forest: OutlineForest, cursor: OutlineCursor, focus: NodeId) -> Optional[Tuple[Row, ...]]:
    focus_row = forest.row(focus)
    if focus_row is None:
        return None
    chosen = cursor.selected or (focus,)
    rows = []
    for node in chosen:
        row = forest.row(node)
        if row is None or row.parent != focus_row.parent:
            return None
        rows.append(row)
    rows.sort(key=lambda row: row.sibling_index)
    indexes = [row.sibling_index for row in rows]
    if indexes != list(range(indexes[0], indexes[0] + len(indexes))):
        return None
    return tuple(rows)


def _previous_sibling(forest: OutlineForest, row: Row) -> Optional[Row]:
    siblings = forest.children(row.parent)
    for index, sibling in enumerate(siblings):
        if sibling.node == row.node:
            if index == 0:
                return None
            return siblings[index - 1]
    return None


def _delete_ids(forest: OutlineForest, cursor: OutlineCursor) -> Tuple[NodeId, ...]:
    focus = cursor.focus
    if focus is None:
        return ()
    chosen = cursor.selected or (focus,)
    rows = []
    for node in chosen:
        row = forest.row(node)
        if row is None:
            continue
        rows.append(row)
    if not rows:
        return (focus,)
    parents = {row.parent for row in rows}
    if len(parents) == 1:
        return tuple(row.node for row in rows)
    return (focus,)


def _layout_selection(forest: OutlineForest, cursor: OutlineCursor, layout: NodeId) -> Tuple[NodeId, ...]:
    focus = cursor.focus
    chosen = cursor.selected or ((focus,) if focus is not None else ())
    found = []
    for node in chosen:
        row = forest.row(node)
        if row is None or not isinstance(row.slot, InLayoutSlot) or row.slot.layout != layout:
            continue
        found.append(node)
    if found:
        return tuple(found)
    if focus is None:
        return ()
    return (focus,)


def _dragged_page(forest: OutlineForest, source_ids: Tuple[NodeId, ...]) -> Optional[Row]:
    if not source_ids:
        return None
    row = forest.row(source_ids[0])
    if row is None or not isinstance(row.slot, InPageSlot):
        return None
    return row


def _drop_flash(forest: OutlineForest, gesture: DropGesture, prose: str) -> Effect:
    node = gesture.payload.source_ids[0] if gesture.payload.source_ids else None
    if node is None or forest.row(node) is None:
        return Idle()
    return Flash(node, prose or "That drop does not land.")


def _toast(forest: OutlineForest, ids: Sequence[NodeId]) -> str:
    if len(ids) != 1:
        return "Deleted %d widgets \u00b7 Undo" % len(ids)
    row = forest.row(ids[0])
    name = row.name if row is not None and row.name else "widget"
    return "Deleted %s \u00b7 Undo" % name


def _make_row(
    doc: UiDocument,
    node: Node,
    parent: Optional[NodeId],
    depth: int,
    sibling_index: int,
    problems: FrozenSet[NodeId],
    friendly_of: Callable[[str], str],
) -> Row:
    kind, tone, name, qt_class, slot = _identity(doc, node, parent, sibling_index)
    visible = _visible_text(node)
    if kind == "page" and not visible:
        visible = _attr(node, "label")
    primary = _page_primary(node, slot.index) if kind == "page" and isinstance(slot, InPageSlot) else name
    return Row(
        node.id,
        parent,
        depth,
        sibling_index,
        kind,
        tone,
        name,
        primary,
        friendly_of(qt_class),
        qt_class,
        visible,
        _hidden(node),
        node.id in problems,
        kind == "layout" or (isinstance(node, WidgetNode) and is_container(doc, node.id)),
        slot,
    )


def _retitle(
    row: Row,
    doc: UiDocument,
    node: Node,
    problems: FrozenSet[NodeId],
    friendly_of: Callable[[str], str],
) -> Row:
    name = _object_name(node)
    visible = _visible_text(node)
    if row.kind == "page" and not visible:
        visible = _attr(node, "label")
    primary = row.primary
    if row.kind == "page" and isinstance(row.slot, InPageSlot):
        primary = _page_primary(node, row.slot.index)
    elif row.kind != "page":
        primary = name
    return replace(
        row,
        name=name,
        primary=primary,
        friendly=friendly_of(row.qt_class),
        visible_text=visible,
        hidden=_hidden(node),
        problem=node.id in problems,
    )


def _identity(
    doc: UiDocument,
    node: Node,
    parent: Optional[NodeId],
    sibling_index: int,
) -> Tuple[str, str, str, str, Slot]:
    parent_node = None if parent is None else doc.get(parent)
    if isinstance(node, SpacerNode):
        return ("spacer", "spacer", node.name, "Spacer", _bare_or_layout(doc, node, parent_node, sibling_index))
    if isinstance(node, LayoutNode):
        return (
            "layout",
            "layout",
            node.object_name,
            node.class_name,
            _bare_or_layout(doc, node, parent_node, sibling_index),
        )
    assert isinstance(node, WidgetNode)
    page = isinstance(parent_node, WidgetNode) and _page_host(doc, parent_node)
    kind = "page" if page else "widget"
    slot: Slot
    if page:
        slot = InPageSlot(parent_node.id, _widget_index(parent_node, node.id))
    else:
        slot = _bare_or_layout(doc, node, parent_node, sibling_index)
    return (kind, "widget", node.object_name, node.class_name, slot)


def _bare_or_layout(
    doc: UiDocument,
    node: Node,
    parent_node: Optional[Node],
    sibling_index: int,
) -> Slot:
    item = doc.parent(node.id)
    if isinstance(item, LayoutItemNode):
        layout = doc.parent(item.id)
        if isinstance(layout, LayoutNode):
            return InLayoutSlot(layout.id, layout.class_name, _layout_index(layout, item))
    container = parent_node.id if parent_node is not None else node.id
    return InBareSlot(container, sibling_index)


def _layout_index(layout: LayoutNode, item: LayoutItemNode) -> int:
    if layout.class_name not in ("QGridLayout", "QFormLayout"):
        return item.slot_index
    ranked = sorted(layout.items, key=lambda entry: (entry.row or 0, entry.column or 0, entry.slot_index))
    for index, entry in enumerate(ranked):
        if entry.id == item.id:
            return index
    return item.slot_index


def _page_host(doc: UiDocument, node: Node) -> bool:
    if not isinstance(node, WidgetNode):
        return False
    if node.class_name in PAGE_HOSTS:
        return True
    custom = doc.custom_widget(node.class_name)
    if custom is None:
        return False
    extends = custom.field("extends")
    return isinstance(extends, str) and extends in PAGE_HOSTS


def _page_primary(node: Node, index: int) -> str:
    title = _attr(node, "title") or _attr(node, "label")
    if title:
        return "Page %d \u00b7 %s" % (index + 1, title)
    return "Page %d" % (index + 1)


def _visible_text(node: Node) -> str:
    for key in ("text", "title", "windowTitle", "plainText"):
        text = _prop(node, key)
        if text:
            return text
    return _attr(node, "title")


def _hidden(node: Node) -> bool:
    entry = node.prop("visible")
    return entry is not None and isinstance(entry.value, BoolValue) and not entry.value.value


def _prop(node: Node, name: str) -> str:
    entry = node.prop(name)
    if entry is None:
        return ""
    value = entry.value
    if isinstance(value, (StringValue, CStringValue)) and value.text:
        return value.text
    return ""


def _attr(node: Node, name: str) -> str:
    entry = node.attr(name)
    if entry is None:
        return ""
    value = entry.value
    if isinstance(value, (StringValue, CStringValue)) and value.text:
        return value.text
    return ""


def _object_name(node: Node) -> str:
    if isinstance(node, SpacerNode):
        return node.name
    if isinstance(node, (WidgetNode, LayoutNode)):
        return node.object_name
    return ""


def _widget_index(parent: WidgetNode, node_id: NodeId) -> int:
    for index, child in enumerate(parent.child_widgets):
        if child.id == node_id:
            return index
    return 0


def _current_index(widget: WidgetNode) -> int:
    entry = widget.prop("currentIndex")
    if entry is not None and isinstance(entry.value, NumberValue):
        return int(entry.value.value)
    return 0


def _is_row(node: Node) -> bool:
    return isinstance(node, (WidgetNode, LayoutNode, SpacerNode))


def _slot_children(node: Node) -> Tuple[Node, ...]:
    found: List[Node] = []
    for _name, kids in node.slots:
        found.extend(kids)
    if isinstance(node, LayoutNode) and node.class_name in ("QGridLayout", "QFormLayout"):
        found.sort(key=_reading_key)
    return tuple(found)


def _reading_key(node: Node) -> Tuple[int, int, int]:
    if isinstance(node, LayoutItemNode):
        return (node.row or 0, node.column or 0, node.slot_index)
    return (0, 0, 0)
