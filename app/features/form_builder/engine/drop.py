"""The drag machine and the one way a drop becomes commands.

Imports slots. Does not import Qt. Every edit is a transaction of commands
that already exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.commands.catalog import InsertFragment, MoveNodes, SetBuddy, Wrap
from app.features.form_builder.engine.commands.log import CommandLog, Transaction
from app.features.form_builder.engine.commands.placement import InBoxLayout, InFormRow, InGridCell
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.hit_index import GeoEntry
from app.features.form_builder.engine.query.slots import (
    LABEL_CLASS,
    SPACER_CLASS,
    Away,
    Beside,
    Buddy,
    CanvasGeom,
    Cargo,
    CellMark,
    DropPaint,
    DropTarget,
    FrameMark,
    GapMark,
    GhostMark,
    Mark,
    MoveCargo,
    NewCargo,
    NoMark,
    OutlineGeom,
    Place,
    Point,
    Refuse,
    Sight,
    Spring,
    acceptable,
    loud,
    resolve,
)
from app.features.form_builder.engine.query.tree import form_item_role
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import StringValue

DRAG_THRESHOLD = 4
SPRING_MS = 600

_OBJECT_NAMES = {
    "QPushButton": "pushButton",
    "QLineEdit": "lineEdit",
    LABEL_CLASS: "label",
    SPACER_CLASS: "spacer",
}


@dataclass(frozen=True)
class Tile:
    class_name: str
    caption: str
    #: Widget ``text`` property. None for a line edit and a spacer.
    text: Optional[str]


TILES: Tuple[Tile, ...] = (
    Tile("QPushButton", "Button", "Button"),
    Tile("QLineEdit", "Line edit", None),
    Tile(LABEL_CLASS, "Label", "Label"),
    Tile(SPACER_CLASS, "Spacer", None),
)


@dataclass(frozen=True)
class ArmCanvas:
    pressed: NodeId
    selected: Tuple[NodeId, ...]
    narrow_on_click: bool
    global_at: Point
    local_at: Point
    token: str


@dataclass(frozen=True)
class ArmRow:
    node: NodeId
    global_at: Point
    local_at: Point
    token: str


@dataclass(frozen=True)
class ArmTile:
    class_name: str
    size: Tuple[int, int]
    global_at: Point
    local_at: Point
    token: str


@dataclass(frozen=True)
class Pointer:
    where: Literal["canvas", "outline", "away"]
    global_at: Point
    local_at: Point
    snap: int
    now_ms: int


@dataclass(frozen=True)
class Release:
    pass


@dataclass(frozen=True)
class Cancel:
    pass


CarryEvent = Union[ArmCanvas, ArmRow, ArmTile, Pointer, Release, Cancel]


@dataclass(frozen=True)
class Say:
    sentence: str


@dataclass(frozen=True)
class Repaint:
    paint: Optional[DropPaint]


@dataclass(frozen=True)
class DragCursor:
    shape: Literal["move", "forbidden", "arrow"]


@dataclass(frozen=True)
class SpringOpen:
    action: Spring


@dataclass(frozen=True)
class NarrowSelection:
    node: NodeId


@dataclass(frozen=True)
class CommitDrop:
    target: DropTarget
    cargo: Cargo
    token: str


CarryEffect = Union[Say, Repaint, DragCursor, SpringOpen, NarrowSelection, CommitDrop]


@dataclass(frozen=True)
class Quiet:
    pass


@dataclass(frozen=True)
class Armed:
    token: str
    origin: Point
    cargo: Cargo
    narrow: Optional[NodeId]


@dataclass(frozen=True)
class Dwell:
    spring: Spring
    since_ms: int
    fired: bool


@dataclass(frozen=True)
class Dragging:
    token: str
    cargo: Cargo
    where: Literal["canvas", "outline", "away"]
    target: DropTarget
    dwell: Optional[Dwell]


Carry = Union[Quiet, Armed, Dragging]


@dataclass(frozen=True)
class CarryStep:
    state: Carry
    effects: Tuple[CarryEffect, ...]


@dataclass(frozen=True)
class DropDone:
    moved: bool
    edited: Optional[NodeId]


def step(state: Carry, event: CarryEvent, sight: Sight, document: UiDocument) -> CarryStep:
    """Pure. No log, no timer, no Qt.

    ``sight`` is read only while handling ``Pointer``. Arm, release, and
    cancel ignore it. Release commits the target already stored on ``Dragging``.
    """
    if isinstance(event, Cancel):
        return _cancel(state)
    if isinstance(state, Quiet):
        return _from_quiet(event, document)
    if isinstance(state, Armed):
        return _from_armed(state, event, sight, document)
    return _from_dragging(state, event, sight, document)


def commit(log: CommandLog, effect: CommitDrop) -> DropDone:
    """One transaction. ``acceptable`` is false → ``DropDone(False, None)`` and the log is not opened."""
    if not acceptable(effect.target):
        return DropDone(False, None)
    recipe = effect.target.recipe
    cargo = effect.cargo
    if isinstance(cargo, MoveCargo) and not cargo.ids:
        return DropDone(False, None)
    gesture = isinstance(recipe, Buddy)
    label = "Move" if isinstance(cargo, MoveCargo) else "Insert"
    with log.transaction(
        label,
        merge_token=effect.token if gesture else None,
        continue_gesture=gesture,
    ) as txn:
        ids, edited = _perform(log, txn, recipe, cargo)
        if ids:
            current = edited if edited is not None else ids[0]
            txn.select(tuple(ids), current)
    return DropDone(True, edited)


def nudge(
    log: CommandLog,
    document: UiDocument,
    ids: Tuple[NodeId, ...],
    current: Optional[NodeId],
    key: Literal["left", "right", "up", "down"],
) -> bool:
    """One slot. False, and no transaction, when the selection cannot move."""
    if not ids and current is None:
        return False
    pressed = current if current is not None else ids[0]
    moving = _movable(document, pressed, ids if ids else (pressed,))
    if not moving:
        return False
    home = _home(document, moving[0])
    if home is None or home[0] != "layout":
        return False
    layout = document.get(home[1])
    if not isinstance(layout, LayoutNode):
        return False
    if layout.class_name == "QFormLayout":
        return _nudge_form(log, document, layout, moving, pressed, key)
    if layout.class_name == "QGridLayout":
        placement = _grid_step(document, layout, moving[0], key)
        if placement is None:
            return False
        _move(log, moving, placement, pressed)
        return True
    delta = _box_delta(layout.class_name, key)
    if delta is None:
        return False
    start = _box_start(layout, moving, delta)
    if start is None:
        return False
    _move(log, moving, InBoxLayout(layout.id, start), pressed)
    return True


def _from_quiet(event: CarryEvent, document: UiDocument) -> CarryStep:
    if isinstance(event, ArmCanvas):
        cargo = MoveCargo(_movable(document, event.pressed, event.selected))
        narrow = event.pressed if event.narrow_on_click else None
        return CarryStep(Armed(event.token, event.global_at, cargo, narrow), ())
    if isinstance(event, ArmRow):
        return CarryStep(Armed(event.token, event.global_at, MoveCargo((event.node,)), None), ())
    if isinstance(event, ArmTile):
        if _tile(event.class_name) is None:
            return CarryStep(Quiet(), (Say(""),))
        return CarryStep(
            Armed(event.token, event.global_at, NewCargo(event.class_name, event.size), None),
            (),
        )
    return CarryStep(Quiet(), ())


def _from_armed(state: Armed, event: CarryEvent, sight: Sight, document: UiDocument) -> CarryStep:
    if isinstance(event, Release):
        effects: Tuple[CarryEffect, ...] = ()
        if state.narrow is not None:
            effects = (NarrowSelection(state.narrow),)
        return CarryStep(Quiet(), effects)
    if not isinstance(event, Pointer) or not _crossed(state.origin, event.global_at):
        return CarryStep(state, ())
    return _drag(state.token, state.cargo, event, sight, document, "", None)


def _from_dragging(state: Dragging, event: CarryEvent, sight: Sight, document: UiDocument) -> CarryStep:
    if isinstance(event, Release):
        return _release(state)
    if not isinstance(event, Pointer):
        return CarryStep(state, ())
    return _drag(state.token, state.cargo, event, sight, document, state.target.sentence, state.dwell)


def _drag(
    token: str,
    cargo: Cargo,
    event: Pointer,
    sight: Sight,
    document: UiDocument,
    previous: str,
    dwell: Optional[Dwell],
) -> CarryStep:
    target = _aim(document, sight, event, cargo)
    next_dwell, sprung = _dwell(dwell, target, event.now_ms)
    state = Dragging(token, cargo, event.where, target, next_dwell)
    return CarryStep(state, _pointer_effects(previous, target, event, cargo, sight) + sprung)


def _release(state: Dragging) -> CarryStep:
    effects: List[CarryEffect] = [Repaint(None), DragCursor("arrow")]
    if acceptable(state.target):
        effects.append(CommitDrop(state.target, state.cargo, state.token))
    elif loud(state.target):
        effects.append(Say(state.target.sentence))
    else:
        effects.append(Say(""))
    return CarryStep(Quiet(), tuple(effects))


def _cancel(state: Carry) -> CarryStep:
    if isinstance(state, Quiet):
        return CarryStep(Quiet(), ())
    return CarryStep(Quiet(), (Repaint(None), DragCursor("arrow"), Say("")))


def _aim(document: UiDocument, sight: Sight, event: Pointer, cargo: Cargo) -> DropTarget:
    if event.where == "away" or isinstance(sight, Away):
        return DropTarget(Refuse("none"), "", NoMark(), None)
    return resolve(document, sight, event.local_at, cargo, event.snap)


def _pointer_effects(
    previous: str,
    target: DropTarget,
    event: Pointer,
    cargo: Cargo,
    sight: Sight,
) -> Tuple[CarryEffect, ...]:
    effects: List[CarryEffect] = []
    if target.sentence != previous:
        effects.append(Say(target.sentence))
    if event.where == "away":
        effects.append(Repaint(None))
        effects.append(DragCursor(_cursor(target)))
        return tuple(effects)
    effects.append(Repaint(_paint(event.where, target, event.local_at, cargo, sight)))
    effects.append(DragCursor(_cursor(target)))
    return tuple(effects)


def _paint(
    where: Literal["canvas", "outline"],
    target: DropTarget,
    local: Point,
    cargo: Cargo,
    sight: Sight,
) -> DropPaint:
    ghost = _ghost_size(cargo, sight) if acceptable(target) else None
    dim = cargo.ids if isinstance(cargo, MoveCargo) else ()
    return DropPaint(where, target.mark, target.sentence, loud(target), dim, ghost, _ghost_point(target.mark, local))


def _cursor(target: DropTarget) -> Literal["move", "forbidden", "arrow"]:
    if acceptable(target):
        return "move"
    if loud(target):
        return "forbidden"
    return "arrow"


def _dwell(
    previous: Optional[Dwell],
    target: DropTarget,
    now_ms: int,
) -> Tuple[Optional[Dwell], Tuple[CarryEffect, ...]]:
    spring = target.spring
    if spring is None:
        return None, ()
    if previous is not None and previous.spring == spring:
        if previous.fired or now_ms - previous.since_ms < SPRING_MS:
            return previous, ()
        return Dwell(spring, previous.since_ms, True), (SpringOpen(spring),)
    return Dwell(spring, now_ms, False), ()


def _crossed(origin: Point, point: Point) -> bool:
    return abs(point.x - origin.x) >= DRAG_THRESHOLD or abs(point.y - origin.y) >= DRAG_THRESHOLD


def _ghost_size(cargo: Cargo, sight: Sight) -> Tuple[int, int]:
    if isinstance(cargo, NewCargo):
        return cargo.size
    entries = _sight_entries(sight)
    for node_id in cargo.ids:
        for entry in entries:
            if entry.node == node_id:
                return entry.rect.width, entry.rect.height
    return 80, 24


def _ghost_point(mark: Mark, local: Point) -> Point:
    if isinstance(mark, (GapMark, CellMark, FrameMark, GhostMark)):
        return Point(mark.rect.x, mark.rect.y)
    return local


def _sight_entries(sight: Sight) -> Tuple[GeoEntry, ...]:
    if isinstance(sight, (CanvasGeom, OutlineGeom)):
        return sight.entries
    return ()


def _perform(
    log: CommandLog,
    txn: Transaction,
    recipe: Union[Place, Beside, Buddy],
    cargo: Cargo,
) -> Tuple[Tuple[NodeId, ...], Optional[NodeId]]:
    if isinstance(recipe, Place):
        return _place(txn, recipe, cargo), None
    if isinstance(recipe, Beside):
        layout_id = txn.execute(Wrap((recipe.anchor,), None, recipe.layout_class))
        placed = InBoxLayout(layout_id, recipe.index)
        if isinstance(cargo, NewCargo):
            inserted = txn.execute(InsertFragment(placed, _fragment(cargo.class_name), False))
            return inserted.ids, None
        txn.execute(MoveNodes(cargo.ids, placed))
        return cargo.ids, None
    label = txn.execute(
        InsertFragment(
            InFormRow(recipe.layout, recipe.row, "label", True),
            _label_fragment(),
            False,
        )
    )
    label_id = label.ids[0]
    if isinstance(cargo, NewCargo):
        field = txn.execute(
            InsertFragment(InFormRow(recipe.layout, recipe.row, "field", False), _fragment(cargo.class_name), False)
        )
        field_id = field.ids[0]
    else:
        field_id = cargo.ids[0]
        txn.execute(MoveNodes(cargo.ids, InFormRow(recipe.layout, recipe.row, "field", False)))
    node = log.document.node(field_id)
    name = node.object_name if isinstance(node, WidgetNode) else ""
    txn.execute(SetBuddy(label_id, name or None))
    return (label_id, field_id), label_id


def _place(txn: Transaction, recipe: Place, cargo: Cargo) -> Tuple[NodeId, ...]:
    if isinstance(cargo, NewCargo):
        inserted = txn.execute(InsertFragment(recipe.placement, _fragment(cargo.class_name), recipe.auto_layout))
        return inserted.ids
    txn.execute(MoveNodes(cargo.ids, recipe.placement))
    return cargo.ids


def _label_fragment() -> Fragment:
    spec = NodeSpec(
        "widget",
        None,
        (("class_name", LABEL_CLASS), ("object_name", "label")),
        (PropertyEntry("property", "text", StringValue("New field:")),),
    )
    return Fragment(nodes=(spec,))


def _fragment(class_name: str) -> Fragment:
    if class_name == SPACER_CLASS:
        spec = NodeSpec("spacer", None, (("name", _OBJECT_NAMES[SPACER_CLASS]),))
        return Fragment(nodes=(spec,))
    tile = _tile(class_name)
    text = None if tile is None else tile.text
    props: Tuple[PropertyEntry, ...] = ()
    if text is not None:
        props = (PropertyEntry("property", "text", StringValue(text)),)
    name = _OBJECT_NAMES.get(class_name, class_name[:1].lower() + class_name[1:])
    spec = NodeSpec("widget", None, (("class_name", class_name), ("object_name", name)), props)
    return Fragment(nodes=(spec,))


def _tile(class_name: str) -> Optional[Tile]:
    for tile in TILES:
        if tile.class_name == class_name:
            return tile
    return None


def _move(
    log: CommandLog,
    moving: Tuple[NodeId, ...],
    placement: Union[InBoxLayout, InGridCell],
    pressed: NodeId,
) -> None:
    token = "nudge:" + ",".join(str(int(node_id)) for node_id in moving)
    with log.transaction("Move", merge_token=token, merge_within_s=1.0) as txn:
        txn.execute(MoveNodes(moving, placement))
        current = pressed if pressed in moving else moving[0]
        txn.select(moving, current)


def _nudge_form(
    log: CommandLog,
    document: UiDocument,
    layout: LayoutNode,
    moving: Tuple[NodeId, ...],
    pressed: NodeId,
    key: Literal["left", "right", "up", "down"],
) -> bool:
    if key in ("left", "right"):
        return False
    item = _item_of(document, moving[0])
    if item is None or item.row is None:
        return False
    rows = _form_rows(layout)
    selected = item.row
    if selected not in rows:
        return False
    other = selected - 1 if key == "up" else selected + 1
    if other not in rows:
        return False
    park = max(rows) + 1
    # Vacate first so the other row can occupy the cells this row leaves.
    waves = (
        _row_moves(layout.id, rows[selected], park),
        _row_moves(layout.id, rows[other], selected),
        _row_moves(layout.id, rows[selected], other),
    )
    token = "nudge:" + ",".join(str(int(node_id)) for node_id in moving)
    with log.transaction("Move", merge_token=token, merge_within_s=1.0) as txn:
        for wave in waves:
            for node_id, placement in wave:
                txn.execute(MoveNodes((node_id,), placement))
        current = pressed if pressed in moving else moving[0]
        txn.select(moving, current)
    return True


def _row_moves(
    layout_id: NodeId,
    row: Sequence[Tuple[NodeId, Literal["label", "field", "spanning"]]],
    dest: int,
) -> Tuple[Tuple[NodeId, InFormRow], ...]:
    return tuple((node_id, InFormRow(layout_id, dest, role, False)) for node_id, role in row)


def _form_rows(
    layout: LayoutNode,
) -> Dict[int, List[Tuple[NodeId, Literal["label", "field", "spanning"]]]]:
    rows: Dict[int, List[Tuple[NodeId, Literal["label", "field", "spanning"]]]] = {}
    for item in layout.items:
        content = item.content
        if content is None:
            continue
        row = 0 if item.row is None else item.row
        role = form_item_role(item.column, item.colspan)
        rows.setdefault(row, []).append((content.id, role))
    return rows


def _grid_step(
    document: UiDocument,
    layout: LayoutNode,
    node_id: NodeId,
    key: Literal["left", "right", "up", "down"],
) -> Optional[InGridCell]:
    item = _item_of(document, node_id)
    if item is None:
        return None
    row = 0 if item.row is None else item.row
    column = 0 if item.column is None else item.column
    rowspan = item.rowspan or 1
    colspan = item.colspan or 1
    if key == "left":
        column -= 1
    elif key == "right":
        column += 1
    elif key == "up":
        row -= 1
    else:
        row += 1
    if row < 0 or column < 0:
        return None
    rows, cols = _grid_span(layout)
    if row + rowspan > rows or column + colspan > cols:
        return None
    if _grid_taken(layout, node_id, row, column, rowspan, colspan):
        return None
    return InGridCell(layout.id, row, column, rowspan, colspan, "cell")


def _grid_span(layout: LayoutNode) -> Tuple[int, int]:
    rows = 0
    cols = 0
    for item in layout.items:
        rows = max(rows, (0 if item.row is None else item.row) + (item.rowspan or 1))
        cols = max(cols, (0 if item.column is None else item.column) + (item.colspan or 1))
    return rows, cols


def _grid_taken(
    layout: LayoutNode,
    moving: NodeId,
    row: int,
    column: int,
    rowspan: int,
    colspan: int,
) -> bool:
    for item in layout.items:
        content = item.content
        if content is None or content.id == moving:
            continue
        other_row = 0 if item.row is None else item.row
        other_col = 0 if item.column is None else item.column
        if row < other_row + (item.rowspan or 1) and other_row < row + rowspan:
            if column < other_col + (item.colspan or 1) and other_col < column + colspan:
                return True
    return False


def _box_delta(class_name: str, key: str) -> Optional[int]:
    if class_name == "QVBoxLayout" and key == "up":
        return -1
    if class_name == "QVBoxLayout" and key == "down":
        return 1
    if class_name == "QHBoxLayout" and key == "left":
        return -1
    if class_name == "QHBoxLayout" and key == "right":
        return 1
    return None


def _box_start(layout: LayoutNode, moving: Sequence[NodeId], delta: int) -> Optional[int]:
    wanted = set(moving)
    indexes = []
    for index, item in enumerate(layout.items):
        content = item.content
        if content is not None and content.id in wanted:
            indexes.append(index)
    if len(indexes) != len(wanted):
        return None
    first = indexes[0]
    last = indexes[-1]
    if delta < 0:
        if first == 0:
            return None
        return first - 1
    if last == len(layout.items) - 1:
        return None
    return last + 2


def _movable(document: UiDocument, pressed: NodeId, selected: Tuple[NodeId, ...]) -> Tuple[NodeId, ...]:
    """Who moves.

    Pressed not in ``selected`` → ``(pressed,)``. A grid or a form moves only
    the pressed id. Otherwise the selected siblings, ancestors removed.
    """
    if document.get(pressed) is None:
        return ()
    if pressed not in selected:
        return (pressed,)
    home = _home(document, pressed)
    if home is None:
        return (pressed,)
    if home[0] == "layout":
        layout = document.get(home[1])
        if isinstance(layout, LayoutNode) and layout.class_name in ("QGridLayout", "QFormLayout"):
            return (pressed,)
    chosen = []
    for node_id in selected:
        if _home(document, node_id) == home:
            chosen.append(node_id)
    if pressed not in chosen:
        chosen.append(pressed)
    return _ordered(document, _without_ancestors(document, chosen))


def _home(document: UiDocument, node_id: NodeId) -> Optional[Tuple[str, NodeId]]:
    node = document.get(node_id)
    if node is None:
        return None
    parent = document.parent(node_id)
    if isinstance(parent, LayoutItemNode) and parent.parent_id is not None:
        layout = document.get(parent.parent_id)
        if isinstance(layout, LayoutNode):
            return ("layout", layout.id)
    if isinstance(parent, WidgetNode):
        return ("widget", parent.id)
    return None


def _without_ancestors(document: UiDocument, ids: Sequence[NodeId]) -> List[NodeId]:
    kept = []
    for node_id in ids:
        if any(other != node_id and document.is_ancestor(node_id, other) for other in ids):
            continue
        kept.append(node_id)
    return kept


def _ordered(document: UiDocument, ids: Sequence[NodeId]) -> Tuple[NodeId, ...]:
    rank = {}
    for index, node in enumerate(document.iter_preorder()):
        rank[node.id] = index
    return tuple(sorted(ids, key=lambda node_id: rank.get(node_id, 0)))


def _item_of(document: UiDocument, node_id: NodeId) -> Optional[LayoutItemNode]:
    parent = document.parent(node_id)
    if isinstance(parent, LayoutItemNode):
        return parent
    return None
