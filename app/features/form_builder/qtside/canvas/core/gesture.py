"""The canvas input machine. ``step`` is a table lookup and writes nothing."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Dict, FrozenSet, Literal, Optional, Tuple, Union, get_args

from app.features.form_builder.engine.commands.base import Command
from app.features.form_builder.engine.commands.catalog import SetGeometry, SetProperty
from app.features.form_builder.engine.commands.catalog_ext.drop import InsertFormRow
from app.features.form_builder.engine.commands.drop_plan import nudge_commands
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.drop_target import AcceptedDrop, DropPayload, NoDrop, RefusedDrop
from app.features.form_builder.engine.query.hit_index import HitIndex, Rect
from app.features.form_builder.engine.query.selection import SelectionState
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.values import RectValue
from app.features.form_builder.qtside.canvas.core.place import drop_commands, payload_for, resolve_at
from app.features.form_builder.qtside.canvas.core.frame import (
    ChipAction,
    OnChip,
    OnHandle,
    OnPageEdge,
    OnSpace,
    OnWidget,
    OverlayFrame,
    Target,
)
from app.features.form_builder.engine.query.direct import GRID, snap_resize
from app.features.form_builder.qtside.canvas.core.snap import snap_move, snap_page
from app.features.form_builder.qtside.canvas.core.space import (
    CanvasPoint,
    Compass,
    FormPoint,
    PortPoint,
    Size,
    ViewMap,
    ZoomChange,
    ZoomFit,
    ZoomStep,
    ZoomTo,
)
from app.features.form_builder.qtside.canvas.core.structure import (
    Free,
    LaidOut,
    Managed,
    Positioning,
    band_candidates,
    effective_selection,
    first_child,
    free_origin,
    nearest_in_direction,
    next_in_outline,
    parent_step,
    positioning_of,
)
from app.features.form_builder.qtside.canvas.core.text import TextTarget, enter_opens_editor, next_text_target, text_commit, text_target
from app.features.form_builder.qtside.canvas.core.words import (
    FIRST_FOCUS_HINT,
    MOVE_IN_LAYOUT_LATER,
    RESIZE_IN_LAYOUT_LATER,
    hover_sentence,
)

DRAG_THRESHOLD = 4

Button = Literal["left", "middle", "right"]
KeyName = Literal[
    "escape",
    "enter",
    "tab",
    "backtab",
    "left",
    "right",
    "up",
    "down",
    "space",
    "shift",
    "zoom_in",
    "zoom_out",
    "zoom_reset",
    "zoom_fit",
    "other",
]
_ARROWS = frozenset({"left", "right", "up", "down"})
_NUDGE = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}
_ZOOM_KEYS = frozenset({"zoom_in", "zoom_out", "zoom_reset", "zoom_fit"})
_CLAIMED = frozenset(
    {"tab", "backtab", "left", "right", "up", "down", "enter", "space", "zoom_in", "zoom_out", "zoom_reset", "zoom_fit"}
)
_FREE_HANDLES: Tuple[Compass, ...] = ("nw", "n", "ne", "e", "se", "s", "sw", "w")
_LAID_HANDLES: Tuple[Compass, ...] = ("e", "s", "se")


@dataclass(frozen=True)
class Mods:
    shift: bool = False
    ctrl: bool = False
    alt: bool = False


@dataclass(frozen=True)
class Press:
    at: CanvasPoint
    port: PortPoint
    button: Button
    mods: Mods
    double: bool


@dataclass(frozen=True)
class Move:
    at: CanvasPoint
    port: PortPoint
    held: FrozenSet[Button]
    mods: Mods


@dataclass(frozen=True)
class Release:
    at: CanvasPoint
    port: PortPoint
    button: Button
    mods: Mods


@dataclass(frozen=True)
class Wheel:
    port: PortPoint
    dx: int
    dy: int
    mods: Mods


@dataclass(frozen=True)
class Key:
    key: KeyName
    mods: Mods


@dataclass(frozen=True)
class KeyUp:
    key: KeyName


@dataclass(frozen=True)
class Probe:
    key: KeyName
    mods: Mods


@dataclass(frozen=True)
class Leave:
    pass


@dataclass(frozen=True)
class Focus:
    gained: bool
    first: bool


@dataclass(frozen=True)
class EditorDone:
    how: Literal["enter", "tab", "backtab", "escape", "focus_out"]
    text: str


@dataclass(frozen=True)
class DocumentChanged:
    removed: FrozenSet[NodeId]
    replaced: bool


@dataclass(frozen=True)
class ZoomAsked:
    change: ZoomChange


@dataclass(frozen=True)
class HoverFrom:
    node: Optional[NodeId]


@dataclass(frozen=True)
class EditTextAsked:
    pass


@dataclass(frozen=True)
class PlaceAsked:
    at: CanvasPoint
    payload: DropPayload
    insert_key: str = ""


@dataclass(frozen=True)
class PlaceHover:
    at: CanvasPoint
    snap: bool = True
    target: Optional[DropTarget] = None
    outside: bool = False
    #: False when the outline draws the indicator. The canvas keeps the sentence.
    draw: bool = True


@dataclass(frozen=True)
class PlaceDrop:
    at: CanvasPoint
    snap: bool = True
    target: Optional[DropTarget] = None
    outside: bool = False
    draw: bool = True


DropTarget = Union[AcceptedDrop, RefusedDrop, NoDrop]


HostEvent = Union[ZoomAsked, HoverFrom, EditTextAsked, PlaceAsked, PlaceHover, PlaceDrop]
Event = Union[
    Press,
    Move,
    Release,
    Wheel,
    Key,
    KeyUp,
    Probe,
    Leave,
    Focus,
    EditorDone,
    DocumentChanged,
    ZoomAsked,
    HoverFrom,
    EditTextAsked,
    PlaceAsked,
    PlaceHover,
    PlaceDrop,
]


@dataclass(frozen=True)
class Idle:
    hover: Optional[NodeId] = None


@dataclass(frozen=True)
class PanArmed:
    pass


@dataclass(frozen=True)
class MovedItem:
    node: NodeId
    origin: RectValue
    drawn: Rect


@dataclass(frozen=True)
class Moving:
    token: str
    primary: NodeId
    items: Tuple[MovedItem, ...]
    anchor: FormPoint
    pointer: FormPoint
    snap: bool


@dataclass(frozen=True)
class Resizing:
    token: str
    item: MovedItem
    at: Compass
    anchor: FormPoint
    pointer: FormPoint
    snap: bool


@dataclass(frozen=True)
class PageResizing:
    token: str
    at: Compass
    origin: Size
    minimum: Size
    anchor: FormPoint
    pointer: FormPoint
    snap: bool


@dataclass(frozen=True)
class Banding:
    owner: NodeId
    start: FormPoint
    pointer: FormPoint
    additive: bool
    base: Tuple[NodeId, ...]
    candidates: Tuple[Tuple[NodeId, Rect], ...]


@dataclass(frozen=True)
class Inert:
    sentence: str


@dataclass(frozen=True)
class Placing:
    """A layout drag. The original stays put until release."""

    token: str
    payload: DropPayload
    insert_key: str
    pointer: FormPoint
    grab: FormPoint
    target: DropTarget
    outside: bool
    #: False while the outline owns the indicator. The status sentence stays.
    draw: bool = True


@dataclass(frozen=True)
class Panning:
    last: PortPoint
    armed: bool


Drag = Union[Moving, Resizing, PageResizing, Banding, Inert, Placing]
_DRAG = get_args(Drag)
_PREVIEW = (Moving, Resizing, PageResizing)


@dataclass(frozen=True)
class Pressed:
    origin: PortPoint
    on_click: Tuple["Effect", ...]
    on_drag: Drag


@dataclass(frozen=True)
class Editing:
    target: TextTarget
    token: str


Gesture = Union[
    Idle, PanArmed, Pressed, Moving, Resizing, PageResizing, Banding, Inert, Placing, Panning, Editing
]


@dataclass(frozen=True)
class Select:
    ids: Tuple[NodeId, ...]
    current: NodeId


@dataclass(frozen=True)
class Toggle:
    """Add or remove one node. A result that would be empty is ``Select`` of the form."""

    node: NodeId


@dataclass(frozen=True)
class Commit:
    label: str
    commands: Tuple[Command, ...]
    token: str
    #: After the entry, open the in-place editor on the new selection.
    edit: Optional[str] = None


@dataclass(frozen=True)
class Preview:
    rects: Tuple[Tuple[NodeId, RectValue], ...]


@dataclass(frozen=True)
class PreviewPage:
    size: Size


@dataclass(frozen=True)
class EndPreview:
    pass


@dataclass(frozen=True)
class Zoom:
    change: ZoomChange
    anchor: Optional[PortPoint]


@dataclass(frozen=True)
class ScrollBy:
    dx: int
    dy: int


@dataclass(frozen=True)
class Reveal:
    rect: Rect


CursorShape = Literal[
    "arrow",
    "move",
    "forbidden",
    "pointing",
    "size_h",
    "size_v",
    "size_fdiag",
    "size_bdiag",
    "open_hand",
    "closed_hand",
]


@dataclass(frozen=True)
class Cursor:
    shape: CursorShape


@dataclass(frozen=True)
class Tip:
    text: str
    port: PortPoint


@dataclass(frozen=True)
class OpenEditor:
    target: TextTarget


@dataclass(frozen=True)
class CloseEditor:
    pass


@dataclass(frozen=True)
class CanvasPressed:
    pass


@dataclass(frozen=True)
class Narrate:
    sentence: str


@dataclass(frozen=True)
class HoverChanged:
    node: Optional[NodeId]


@dataclass(frozen=True)
class RunChipAction:
    action: ChipAction


ModelEffect = Union[Select, Toggle, Commit]
ViewEffect = Union[Preview, PreviewPage, EndPreview, Zoom, ScrollBy, Reveal, Cursor, Tip]
EditorEffect = Union[OpenEditor, CloseEditor]
HostEffect = Union[CanvasPressed, Narrate, HoverChanged, RunChipAction]
Effect = Union[ModelEffect, ViewEffect, EditorEffect, HostEffect]


@dataclass(frozen=True)
class Step:
    gesture: Gesture
    effects: Tuple[Effect, ...] = ()
    consumed: bool = True


@dataclass(frozen=True)
class World:
    document: UiDocument
    selection: SelectionState
    index: HitIndex
    view: ViewMap
    frame: OverlayFrame
    page_minimum: Size
    fresh_token: str


def needs_fresh_geometry(gesture: Gesture, event: Event) -> bool:
    if isinstance(event, PlaceAsked):
        return True
    if isinstance(event, DocumentChanged) or isinstance(gesture, _DRAG) or isinstance(gesture, (Pressed, Panning)):
        return False
    if isinstance(event, EditorDone) and event.how in ("tab", "backtab"):
        return True
    return isinstance(gesture, (Idle, PanArmed, Editing)) and isinstance(event, (Press, Move, Wheel, Key))


def previewing(gesture: Gesture) -> bool:
    return isinstance(gesture, _PREVIEW)


def aim(
    at: CanvasPoint,
    frame: OverlayFrame,
    index: HitIndex,
    document: UiDocument,
    view: ViewMap,
) -> Target:
    for rect, target in frame.targets:
        if rect.contains(at):
            return target
    form = view.to_form(at)
    hit = index.query(int(form.x), int(form.y))
    root = document.root.id
    if hit is None:
        return OnSpace(root, root)
    if hit.kind == "layout":
        return OnSpace(hit.node, hit.node)
    if hit.node == root:
        return OnSpace(root, root)
    found = document.get(hit.node)
    if isinstance(found, WidgetNode) and found.layout is None and found.child_widgets:
        return OnSpace(hit.node, hit.node)
    site: Literal["widget", "page_tab", "menu_title"] = "widget"
    if hit.kind in ("page_tab", "menu_title"):
        site = hit.kind  # type: ignore[assignment]
    return OnWidget(hit.node, positioning_of(document, hit.node), site)


def moved_rects(state: Moving) -> Tuple[Tuple[NodeId, RectValue], ...]:
    dx, dy = _move_delta(state)
    return tuple(
        (item.node, RectValue(item.origin.x + dx, item.origin.y + dy, item.origin.width, item.origin.height))
        for item in state.items
    )


def drawn_rect(state: Moving, item: MovedItem) -> Rect:
    dx, dy = _move_delta(state)
    return Rect(item.drawn.x + dx, item.drawn.y + dy, item.drawn.width, item.drawn.height)


def resized_rect(state: Resizing) -> RectValue:
    delta = _delta(state.anchor, state.pointer)
    return snap_resize(state.item.origin, state.at, delta.x, delta.y, state.snap)


def resized_drawn(state: Resizing) -> Rect:
    new = resized_rect(state)
    item = state.item
    return Rect(
        item.drawn.x + new.x - item.origin.x,
        item.drawn.y + new.y - item.origin.y,
        new.width,
        new.height,
    )


def page_size(state: PageResizing) -> Size:
    return snap_page(state.origin, state.at, _delta(state.anchor, state.pointer), state.snap, state.minimum)


def band_rect(state: Banding) -> Rect:
    left = int(min(state.start.x, state.pointer.x))
    top = int(min(state.start.y, state.pointer.y))
    right = int(max(state.start.x, state.pointer.x))
    bottom = int(max(state.start.y, state.pointer.y))
    return Rect(left, top, max(0, right - left), max(0, bottom - top))


def band_hits(state: Banding) -> Tuple[NodeId, ...]:
    area = band_rect(state)
    return tuple(node for node, rect in state.candidates if rect.intersects(area))


def step(gesture: Gesture, event: Event, world: World) -> Step:
    handler = TABLE.get((type(gesture), type(event)))
    if handler is None:
        handler = ANY_STATE.get(type(event))
    if handler is None:
        return Step(gesture, (), False)
    return handler(gesture, event, world)


Handler = Callable[[Gesture, Event, World], Step]


def _idle_press(gesture: Idle, event: Press, world: World) -> Step:
    if event.button == "middle":
        return Step(Panning(event.port, False), (CanvasPressed(), HoverChanged(None), Cursor("closed_hand")))
    if event.button != "left":
        return Step(gesture, (CanvasPressed(),))
    target = aim(event.at, world.frame, world.index, world.document, world.view)
    if event.double and isinstance(target, OnWidget):
        editing = text_target(world.document, target.node, target.site)
        if editing is not None:
            return Step(
                Editing(editing, world.fresh_token),
                (CanvasPressed(), HoverChanged(None), Select((target.node,), target.node), OpenEditor(editing)),
            )
    point = world.view.to_form(event.at)
    snap = not event.mods.shift
    if isinstance(target, OnHandle):
        drag: Drag
        if target.writes:
            drag = Resizing(
                world.fresh_token,
                _moved(world, target.node),
                target.at,
                point,
                point,
                snap,
            )
        else:
            drag = Inert(RESIZE_IN_LAYOUT_LATER)
        return Step(Pressed(event.port, (), drag), (CanvasPressed(), HoverChanged(None)))
    if isinstance(target, OnPageEdge):
        drag = PageResizing(
            world.fresh_token,
            target.at,
            Size(world.view.page.width, world.view.page.height),
            world.page_minimum,
            point,
            point,
            snap,
        )
        root = world.document.root.id
        return Step(
            Pressed(event.port, (Select((root,), root),), drag),
            (CanvasPressed(), HoverChanged(None)),
        )
    if isinstance(target, OnChip):
        return Step(
            Pressed(event.port, (RunChipAction(target.action),), Inert("")),
            (CanvasPressed(), HoverChanged(None)),
        )
    if isinstance(target, OnWidget):
        if event.mods.shift or event.mods.ctrl:
            return Step(
                Pressed(event.port, (), Inert("")),
                (CanvasPressed(), HoverChanged(None), _toggle(world, target.node)),
            )
        if target.node not in world.selection.ids:
            return Step(
                Pressed(event.port, (), _move_or_inert(world, (target.node,), point, snap)),
                (CanvasPressed(), HoverChanged(None), Select((target.node,), target.node)),
            )
        return Step(
            Pressed(
                event.port,
                (Select((target.node,), target.node),),
                _move_or_inert(world, world.selection.ids, point, snap),
            ),
            (CanvasPressed(), HoverChanged(None)),
        )
    additive = event.mods.shift or event.mods.ctrl
    click: Tuple[Effect, ...] = () if additive else (Select((target.select,), target.select),)
    base = world.selection.ids if additive else ()
    drag = Banding(
        target.band_owner,
        point,
        point,
        additive,
        base,
        band_candidates(world.document, world.index, target.band_owner),
    )
    return Step(Pressed(event.port, click, drag), (CanvasPressed(), HoverChanged(None)))


def _idle_move(gesture: Idle, event: Move, world: World) -> Step:
    if event.held:
        return Step(gesture, (), False)
    target = aim(event.at, world.frame, world.index, world.document, world.view)
    node, cursor, sentence = _hover_readout(world, target)
    if gesture.hover == node:
        return Step(gesture, (Cursor(cursor),))
    effects: Tuple[Effect, ...] = (HoverChanged(node), Cursor(cursor))
    # A widget hover is the status hover sentence. Narrating it would stick as a gesture.
    if sentence and node is None:
        effects = effects + (Narrate(sentence),)
    return Step(Idle(node), effects)


def _idle_key(gesture: Idle, event: Key, world: World) -> Step:
    shown = effective_selection(world.document, world.selection)
    current = shown.current
    if current is None:
        return Step(gesture, (), True)
    if event.key == "escape":
        parent = parent_step(world.document, current)
        if parent is None:
            return Step(gesture, (), True)
        return Step(gesture, (Select((parent,), parent),))
    if event.key == "enter":
        if enter_opens_editor(world.document, current):
            target = text_target(world.document, current, "widget")
            if target is not None:
                return Step(Editing(target, world.fresh_token), (OpenEditor(target),))
        child = first_child(world.document, current)
        if child is None:
            return Step(gesture, (), True)
        return Step(gesture, (Select((child,), child),))
    if event.key in ("tab", "backtab"):
        nxt = next_in_outline(world.document, current, event.key == "backtab")
        if nxt is None:
            return Step(gesture, (), True)
        return Step(gesture, _select_and_reveal(world, (nxt,), nxt))
    if event.key in _ARROWS and event.mods.alt:
        return _nudge(gesture, event, world)
    if event.key in _ARROWS:
        nxt = nearest_in_direction(world.document, world.index, current, event.key)  # type: ignore[arg-type]
        if nxt is None:
            return Step(gesture, (), True)
        if event.mods.shift:
            ids = tuple(dict.fromkeys(world.selection.ids + (nxt,)))
            if not ids:
                ids = (nxt,)
            return Step(gesture, _select_and_reveal(world, ids, nxt))
        return Step(gesture, _select_and_reveal(world, (nxt,), nxt))
    if event.key == "space":
        return Step(PanArmed(), (HoverChanged(None), Cursor("open_hand")))
    if event.key in _ZOOM_KEYS:
        return Step(gesture, (_zoom_effect(event.key),))
    return Step(gesture, (), False)


def _nudge(gesture: Idle, event: Key, world: World) -> Step:
    shown = effective_selection(world.document, world.selection)
    nodes = shown.ids
    if not nodes:
        return Step(gesture, (), True)
    if any(not isinstance(positioning_of(world.document, node), Free) for node in nodes):
        commands = nudge_commands(world.document, nodes, event.key)
        if not commands:
            return Step(gesture, (), True)
        return Step(gesture, (Commit("Nudge", tuple(commands), world.fresh_token),))
    delta = _NUDGE.get(event.key)
    if delta is None:
        return Step(gesture, (), True)
    step_px = 1 if event.mods.shift else GRID
    dx, dy = delta
    commands = []
    for node in nodes:
        origin = free_origin(world.document, world.index, node)
        commands.append(
            SetGeometry(
                node,
                RectValue(origin.x + dx * step_px, origin.y + dy * step_px, origin.width, origin.height),
            )
        )
    return Step(gesture, (Commit("Nudge", tuple(commands), world.fresh_token),))


def _edit_text(gesture: Idle, event: EditTextAsked, world: World) -> Step:
    del event
    shown = effective_selection(world.document, world.selection)
    current = shown.current
    if current is None or not enter_opens_editor(world.document, current):
        return Step(gesture, (), True)
    target = text_target(world.document, current, "widget")
    if target is None:
        return Step(gesture, (), True)
    return Step(Editing(target, world.fresh_token), (OpenEditor(target),))


def _idle_probe(gesture: Idle, event: Probe, world: World) -> Step:
    return Step(gesture, (), event.key in _CLAIMED)


def _busy_probe(gesture: Gesture, event: Probe, world: World) -> Step:
    return Step(gesture, (), True)


def _pressed_move(gesture: Pressed, event: Move, world: World) -> Step:
    if "left" not in event.held:
        return Step(gesture, (), True)
    dx = event.port.x - gesture.origin.x
    dy = event.port.y - gesture.origin.y
    if dx * dx + dy * dy <= DRAG_THRESHOLD * DRAG_THRESHOLD:
        return Step(gesture, (), True)
    entered = _retarget(gesture.on_drag, world.view.to_form(event.at), not event.mods.shift, world)
    return Step(entered, _begin_effects(entered))


def _pressed_release(gesture: Pressed, event: Release, world: World) -> Step:
    return Step(Idle(None), gesture.on_click)


def _drag_move(gesture: Drag, event: Move, world: World) -> Step:
    if "left" not in event.held:
        return Step(gesture, (), True)
    moved = _retarget(gesture, world.view.to_form(event.at), not event.mods.shift, world)
    effects = _live_effects(moved)
    if isinstance(gesture, _PREVIEW) and not isinstance(moved, _PREVIEW):
        effects = (EndPreview(),) + effects
    return Step(moved, effects)


def _drag_shift(gesture: Drag, event: Union[Key, KeyUp], world: World) -> Step:
    if isinstance(event, Key) and event.key != "shift":
        return Step(gesture, (), True)
    snap = isinstance(event, KeyUp)
    moved = _retarget(gesture, _pointer_of(gesture), snap, world)
    return Step(moved, _live_effects(moved))


def _drag_release(gesture: Drag, event: Release, world: World) -> Step:
    if isinstance(gesture, Placing):
        return _finish_place(gesture, world)
    if isinstance(gesture, _PREVIEW):
        commands = _commands(gesture, world)
        effects: Tuple[Effect, ...] = (EndPreview(),)
        if commands:
            effects = effects + (Commit(_commit_label(gesture), commands, gesture.token),)
        return Step(Idle(None), effects + (Cursor("arrow"),))
    if isinstance(gesture, Banding):
        hits = band_hits(gesture)
        if hits:
            ids = _merge(gesture.base, hits) if gesture.additive else hits
            return Step(Idle(None), (Select(ids, hits[-1]), Cursor("arrow")))
        if gesture.additive:
            return Step(Idle(None), (Cursor("arrow"),))
        return Step(Idle(None), (Select((gesture.owner,), gesture.owner), Cursor("arrow")))
    return Step(Idle(None), (Cursor("arrow"),))


def _drag_escape(gesture: Union[Pressed, Drag], event: Key, world: World) -> Step:
    if event.key == "shift" and isinstance(gesture, _DRAG):
        return _drag_shift(gesture, event, world)
    if event.key != "escape":
        return Step(gesture, (), True)
    if isinstance(gesture, _PREVIEW) or (isinstance(gesture, Pressed) and isinstance(gesture.on_drag, _PREVIEW)):
        return Step(Idle(None), (EndPreview(), Cursor("arrow")))
    if isinstance(gesture, Placing) or (isinstance(gesture, Pressed) and isinstance(gesture.on_drag, Placing)):
        return Step(Idle(None), (Cursor("arrow"), Narrate("")))
    return Step(Idle(None), (Cursor("arrow"),))


def _panning_move(gesture: Panning, event: Move, world: World) -> Step:
    delta = ScrollBy(gesture.last.x - event.port.x, gesture.last.y - event.port.y)
    return Step(Panning(event.port, gesture.armed), (delta,))


def _panning_release(gesture: Panning, event: Release, world: World) -> Step:
    if gesture.armed:
        return Step(PanArmed(), (Cursor("open_hand"),))
    return Step(Idle(None), (Cursor("arrow"),))


def _armed_press(gesture: PanArmed, event: Press, world: World) -> Step:
    if event.button == "left":
        return Step(Panning(event.port, True), (CanvasPressed(), Cursor("closed_hand")))
    return _idle_press(Idle(), event, world)


def _armed_key_up(gesture: PanArmed, event: KeyUp, world: World) -> Step:
    if event.key == "space":
        return Step(Idle(None), (Cursor("arrow"),))
    return Step(gesture, (), True)


def _editing_done(gesture: Editing, event: EditorDone, world: World) -> Step:
    if event.how == "escape":
        return Step(Idle(None), (CloseEditor(),))
    effects_list = []
    command = text_commit(gesture.target, event.text)
    if command is not None:
        stamped = replace(command, merge_token=gesture.token)
        effects_list.append(Commit("Edit text", (stamped,), gesture.token))
    effects_list.append(CloseEditor())
    if event.how in ("tab", "backtab"):
        nxt = next_text_target(world.document, gesture.target.owner, event.how == "backtab")
        if nxt is not None:
            rect = world.index.rect_of(nxt.owner)
            effects_list.append(Select((nxt.owner,), nxt.owner))
            if rect is not None:
                effects_list.append(Reveal(rect))
            effects_list.append(OpenEditor(nxt))
            return Step(Editing(nxt, world.fresh_token), tuple(effects_list))
    return Step(Idle(None), tuple(effects_list))


def _editing_press(gesture: Editing, event: Press, world: World) -> Step:
    followed = _idle_press(Idle(), event, world)
    return Step(followed.gesture, (CloseEditor(),) + followed.effects)


def _on_document(gesture: Gesture, event: DocumentChanged, world: World) -> Step:
    if isinstance(gesture, Editing):
        if event.replaced or gesture.target.owner in event.removed:
            return Step(Idle(None), (CloseEditor(),))
        return Step(gesture, (), False)
    if isinstance(gesture, _PREVIEW) or (isinstance(gesture, Pressed) and isinstance(gesture.on_drag, _PREVIEW)):
        return Step(Idle(None), (EndPreview(),))
    if isinstance(gesture, Idle):
        hover = None if event.replaced or gesture.hover in event.removed else gesture.hover
        return Step(Idle(hover), (), False)
    return Step(Idle(None), (), False)


def _on_zoom(gesture: Gesture, event: ZoomAsked, world: World) -> Step:
    return Step(gesture, (Zoom(event.change, None),))


def _on_wheel(gesture: Gesture, event: Wheel, world: World) -> Step:
    if event.mods.ctrl:
        if event.dy == 0:
            return Step(gesture, (), True)
        direction = 1 if event.dy > 0 else -1
        return Step(gesture, (Zoom(ZoomStep(direction), event.port),))
    if event.mods.shift:
        return Step(gesture, (ScrollBy(-(event.dx + event.dy), 0),))
    return Step(gesture, (ScrollBy(-event.dx, -event.dy),))


def _on_focus(gesture: Gesture, event: Focus, world: World) -> Step:
    if not event.gained and (
        isinstance(gesture, _PREVIEW)
        or isinstance(gesture, (Pressed, Banding, Panning, Inert))
    ):
        effects: Tuple[Effect, ...] = (EndPreview(),) if previewing(gesture) or (
            isinstance(gesture, Pressed) and isinstance(gesture.on_drag, _PREVIEW)
        ) else ()
        return Step(Idle(None), effects)
    if event.gained and event.first:
        return Step(gesture, (Narrate(FIRST_FOCUS_HINT),))
    return Step(gesture, (), False)


def _on_leave(gesture: Idle, event: Leave, world: World) -> Step:
    if gesture.hover is None:
        return Step(gesture, (Cursor("arrow"),))
    return Step(Idle(None), (HoverChanged(None), Cursor("arrow")))


def _on_hover_from(gesture: Idle, event: HoverFrom, world: World) -> Step:
    if gesture.hover == event.node:
        return Step(gesture, (), False)
    return Step(Idle(event.node), (HoverChanged(event.node),))


def _toggle(world: World, node: NodeId) -> Union[Select, Toggle]:
    ids = list(world.selection.ids)
    if node in ids:
        ids.remove(node)
        if not ids:
            root = world.document.root.id
            return Select((root,), root)
        current = world.selection.current if world.selection.current in ids else ids[-1]
        return Toggle(node) if current is not None else Select((root_of(world),), root_of(world))
    return Toggle(node)


def root_of(world: World) -> NodeId:
    return world.document.root.id


def _move_or_inert(world: World, nodes: Tuple[NodeId, ...], point: FormPoint, snap: bool) -> Drag:
    places = [positioning_of(world.document, node) for node in nodes]
    if nodes and all(isinstance(place, Free) for place in places):
        primary = world.selection.current if world.selection.current in nodes else nodes[0]
        items = tuple(_moved(world, node) for node in nodes)
        return Moving(world.fresh_token, primary, items, point, point, snap)
    if any(isinstance(place, (LaidOut, Managed)) for place in places):
        return _placing(world, nodes, point, snap, "")
    return Inert("")


def _moved(world: World, node: NodeId) -> MovedItem:
    rect = world.index.rect_of(node) or Rect(0, 0, 1, 1)
    return MovedItem(node, free_origin(world.document, world.index, node), rect)


def _retarget(state: Drag, point: FormPoint, snap: bool, world: World) -> Drag:
    if isinstance(state, Banding):
        return replace(state, pointer=point)
    if isinstance(state, Moving) and _all_free(world, tuple(item.node for item in state.items)):
        landed = _land_in_layout(state, point, snap, world)
        if landed is not None:
            return landed
    if isinstance(state, Placing) and _all_free(world, state.payload.source_ids):
        payload = replace(state.payload, snap=snap)
        target = resolve_at(world.document, world.index, point, payload)
        if not _lays_out(target):
            return _resume_free_move(state, point, snap, world)
        return replace(state, payload=payload, pointer=point, target=target, outside=False, draw=True)
    if isinstance(state, Placing):
        payload = replace(state.payload, snap=snap)
        target = resolve_at(world.document, world.index, point, payload)
        return replace(state, payload=payload, pointer=point, target=target, outside=False, draw=True)
    if isinstance(state, _PREVIEW):
        return replace(state, pointer=point, snap=snap)
    return state


def _all_free(world: World, nodes: Tuple[NodeId, ...]) -> bool:
    if not nodes:
        return False
    return all(isinstance(positioning_of(world.document, node), Free) for node in nodes if world.document.contains(node))


def _lays_out(target: DropTarget) -> bool:
    return isinstance(target, AcceptedDrop) and target.action != "free"


def _land_in_layout(state: Moving, point: FormPoint, snap: bool, world: World) -> Optional[Placing]:
    nodes = tuple(item.node for item in state.items)
    payload = payload_for(world.document, nodes, snap)
    target = resolve_at(world.document, world.index, point, payload)
    if not _lays_out(target):
        return None
    return Placing(state.token, payload, "", point, FormPoint(0, 0), target, False)


def _resume_free_move(state: Placing, point: FormPoint, snap: bool, world: World) -> Moving:
    nodes = state.payload.source_ids
    primary = nodes[0]
    items = tuple(_moved(world, node) for node in nodes)
    return Moving(state.token, primary, items, point, point, snap)


def _pointer_of(state: Drag) -> FormPoint:
    if isinstance(state, (Moving, Resizing, PageResizing, Banding, Placing)):
        return state.pointer
    return FormPoint(0, 0)


def _begin_effects(state: Drag) -> Tuple[Effect, ...]:
    effects = _live_effects(state)
    if isinstance(state, Inert) and state.sentence:
        return effects + (Narrate(state.sentence),)
    return effects


def _live_effects(state: Drag) -> Tuple[Effect, ...]:
    if isinstance(state, Moving):
        return (Preview(moved_rects(state)), Cursor("move"))
    if isinstance(state, Resizing):
        return (Preview(((state.item.node, resized_rect(state)),)), Cursor(_handle_cursor(state.at)))
    if isinstance(state, PageResizing):
        cursor: CursorShape = "size_h" if state.at == "e" else "size_v"
        return (PreviewPage(page_size(state)), Cursor(cursor))
    if isinstance(state, Inert):
        return (Cursor("forbidden"),)
    if isinstance(state, Placing):
        return _place_effects(state)
    return ()


def _commands(state: Union[Moving, Resizing, PageResizing], world: World) -> Tuple[SetGeometry, ...]:
    if isinstance(state, Moving):
        found = []
        for node, rect in moved_rects(state):
            item = next(candidate for candidate in state.items if candidate.node == node)
            if (rect.x, rect.y, rect.width, rect.height) != (
                item.origin.x,
                item.origin.y,
                item.origin.width,
                item.origin.height,
            ):
                found.append(SetGeometry(node, rect, state.token))
        return tuple(found)
    if isinstance(state, Resizing):
        rect = resized_rect(state)
        origin = state.item.origin
        if (rect.x, rect.y, rect.width, rect.height) == (origin.x, origin.y, origin.width, origin.height):
            return ()
        return (SetGeometry(state.item.node, rect, state.token),)
    size = page_size(state)
    if size == state.origin:
        return ()
    root = world.document.root
    entry = root.prop("geometry")
    x = entry.value.x if entry is not None and isinstance(entry.value, RectValue) else 0
    y = entry.value.y if entry is not None and isinstance(entry.value, RectValue) else 0
    return (SetGeometry(root.id, RectValue(x, y, size.width, size.height), state.token),)


def _commit_label(state: Union[Moving, Resizing, PageResizing]) -> str:
    if isinstance(state, Moving):
        return "Move"
    if isinstance(state, Resizing):
        return "Resize"
    return "Resize form"


def _select_and_reveal(world: World, ids: Tuple[NodeId, ...], current: NodeId) -> Tuple[Effect, ...]:
    effects: Tuple[Effect, ...] = (Select(ids, current),)
    rect = world.index.rect_of(current)
    if rect is not None:
        effects = effects + (Reveal(rect),)
    return effects


def _zoom_effect(key: KeyName) -> Zoom:
    if key == "zoom_in":
        return Zoom(ZoomStep(1), None)
    if key == "zoom_out":
        return Zoom(ZoomStep(-1), None)
    if key == "zoom_fit":
        return Zoom(ZoomFit(), None)
    return Zoom(ZoomTo(1.0), None)


def _hover_readout(world: World, target: Target) -> Tuple[Optional[NodeId], CursorShape, str]:
    if isinstance(target, OnHandle):
        return target.node, _handle_cursor(target.at), ""
    if isinstance(target, OnPageEdge):
        cursor: CursorShape = "size_h" if target.at == "e" else "size_v"
        return None, cursor, ""
    if isinstance(target, OnChip):
        message = target.action.message if hasattr(target.action, "message") else ""
        return None, "pointing", message
    if isinstance(target, OnWidget):
        edits = text_target(world.document, target.node, target.site) is not None
        return target.node, "arrow", hover_sentence(world.document, target.node, edits)
    if isinstance(target, OnSpace):
        found = world.document.get(target.select)
        if isinstance(found, LayoutNode):
            return target.select, "arrow", hover_sentence(world.document, target.select, False)
    return None, "arrow", ""


def _handle_cursor(at: Compass) -> CursorShape:
    if at in ("n", "s"):
        return "size_v"
    if at in ("e", "w"):
        return "size_h"
    if at in ("nw", "se"):
        return "size_fdiag"
    return "size_bdiag"


def _delta(anchor: FormPoint, pointer: FormPoint) -> FormPoint:
    return FormPoint(pointer.x - anchor.x, pointer.y - anchor.y)


def _move_delta(state: Moving) -> Tuple[int, int]:
    primary = next(item for item in state.items if item.node == state.primary)
    return snap_move(primary.origin, _delta(state.anchor, state.pointer), state.snap)


def _merge(base: Tuple[NodeId, ...], extra: Tuple[NodeId, ...]) -> Tuple[NodeId, ...]:
    return tuple(dict.fromkeys(base + extra))


def _placing(
    world: World,
    nodes: Tuple[NodeId, ...],
    point: FormPoint,
    snap: bool,
    insert_key: str,
) -> Placing:
    payload = payload_for(world.document, nodes, snap)
    rect = world.index.rect_of(nodes[0]) if nodes else None
    grab = FormPoint(0, 0) if rect is None else FormPoint(point.x - rect.x, point.y - rect.y)
    return Placing(
        world.fresh_token,
        payload,
        insert_key,
        point,
        grab,
        resolve_at(world.document, world.index, point, payload),
        False,
    )


def _place_effects(state: Placing) -> Tuple[Effect, ...]:
    if state.outside or isinstance(state.target, NoDrop):
        return (Cursor("move"), Narrate(""))
    cursor: CursorShape = "forbidden" if isinstance(state.target, RefusedDrop) else "move"
    return (Cursor(cursor), Narrate(state.target.sentence))


def _finish_place(state: Placing, world: World) -> Step:
    if state.outside or not isinstance(state.target, AcceptedDrop):
        return Step(Idle(None), (Cursor("arrow"), Narrate("")))
    commands = drop_commands(world.document, state.target, state.payload, state.insert_key)
    if not commands:
        return Step(Idle(None), (Cursor("arrow"), Narrate("")))
    edit = "widget" if any(isinstance(command, InsertFormRow) for command in commands) else None
    label = "Move" if state.payload.source_ids else "Drop"
    return Step(Idle(None), (Commit(label, commands, state.token, edit), Cursor("arrow"), Narrate("")))


def _place_asked(gesture: Idle, event: PlaceAsked, world: World) -> Step:
    del gesture
    point = world.view.to_form(event.at)
    state = Placing(
        world.fresh_token,
        event.payload,
        event.insert_key,
        point,
        FormPoint(0, 0),
        resolve_at(world.document, world.index, point, event.payload),
        False,
    )
    return Step(state, (CanvasPressed(),) + _place_effects(state))


def _place_hover(gesture: Placing, event: PlaceHover, world: World) -> Step:
    if event.outside:
        nxt = replace(gesture, outside=True, target=NoDrop(), draw=False)
        return Step(nxt, _place_effects(nxt))
    if event.target is not None:
        nxt = replace(
            gesture,
            pointer=world.view.to_form(event.at),
            target=event.target,
            outside=False,
            draw=event.draw,
        )
        return Step(nxt, _place_effects(nxt))
    nxt = _retarget(gesture, world.view.to_form(event.at), event.snap, world)
    return Step(nxt, _live_effects(nxt))


def _place_drop(gesture: Placing, event: PlaceDrop, world: World) -> Step:
    if event.outside:
        return Step(Idle(None), (Cursor("arrow"), Narrate("")))
    current = gesture
    if event.target is not None:
        current = replace(gesture, target=event.target, outside=False)
    else:
        current = _retarget(gesture, world.view.to_form(event.at), event.snap, world)
    if not isinstance(current, Placing):
        return Step(Idle(None), (Cursor("arrow"),))
    return _finish_place(current, world)


def _placing_leave(gesture: Placing, event: Leave, world: World) -> Step:
    del event, world
    nxt = replace(gesture, outside=True, target=NoDrop())
    return Step(nxt, _place_effects(nxt))


def handles_for(place: Positioning) -> Tuple[Compass, ...]:
    if isinstance(place, Free):
        return _FREE_HANDLES
    if isinstance(place, LaidOut):
        return _LAID_HANDLES
    return ()


TABLE: Dict[Tuple[type, type], Handler] = {
    (Idle, Press): _idle_press,
    (Idle, Move): _idle_move,
    (Idle, Key): _idle_key,
    (Idle, EditTextAsked): _edit_text,
    (Idle, Probe): _idle_probe,
    (Idle, Leave): _on_leave,
    (Idle, HoverFrom): _on_hover_from,
    (PanArmed, Press): _armed_press,
    (PanArmed, KeyUp): _armed_key_up,
    (PanArmed, Probe): _busy_probe,
    (Pressed, Move): _pressed_move,
    (Pressed, Release): _pressed_release,
    (Pressed, Key): _drag_escape,
    (Pressed, Probe): _busy_probe,
    (Panning, Move): _panning_move,
    (Panning, Release): _panning_release,
    (Panning, Probe): _busy_probe,
    (Editing, EditorDone): _editing_done,
    (Editing, Press): _editing_press,
}
DRAG_ROWS: Dict[type, Handler] = {
    Move: _drag_move,
    Release: _drag_release,
    Key: _drag_escape,
    KeyUp: _drag_shift,
    Probe: _busy_probe,
}
TABLE.update({(state, event): handler for state in _DRAG for event, handler in DRAG_ROWS.items()})
TABLE[(Idle, PlaceAsked)] = _place_asked
TABLE[(Placing, PlaceHover)] = _place_hover
TABLE[(Placing, PlaceDrop)] = _place_drop
TABLE[(Placing, Leave)] = _placing_leave

ANY_STATE: Dict[type, Handler] = {
    DocumentChanged: _on_document,
    ZoomAsked: _on_zoom,
    Wheel: _on_wheel,
    Focus: _on_focus,
}
