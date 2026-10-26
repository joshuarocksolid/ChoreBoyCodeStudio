"""Builds the overlay frame. Qt-free.

Two layers. The static layer depends only on the document, the fresh index
and the view map, and is cached on (epoch, view). The dynamic layer adds
selection, hover, the gesture, focus, chips and badges, and is rebuilt per
frame. Neither reads Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Hashable, List, Literal, Mapping, Optional, Sequence, Set, Tuple, Union

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.direct import EMPTY, KnobSet, Readout, Turn
from app.features.form_builder.engine.query.drop_target import AcceptedDrop, NoDrop, RefusedDrop
from app.features.form_builder.engine.query.hit_index import GeoEntry, HitIndex, Rect
from app.features.form_builder.engine.query.selection import SelectionState
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutNode, SpacerNode, WidgetNode
from app.features.form_builder.engine.ui4.values import EnumValue
from app.features.form_builder.qtside.canvas.core.chips import (
    BADGE_CORNERS,
    BARE_CORNERS,
    LABEL_CORNERS,
    ChipRequest,
    ChipSeat,
    Corner,
    CornerSeat,
    DockSeat,
    Obstacle,
    place_chips,
)
from app.features.form_builder.qtside.canvas.core.frame import (
    Badge,
    Caption,
    Chip,
    ChipAction,
    Fill,
    FocusShare,
    FrameBasis,
    Glyph,
    Handle,
    Item,
    AddPage,
    OnChip,
    OnHandle,
    OnKnob,
    OnPageEdge,
    OnSpace,
    OnWidget,
    OpenLayoutPopover,
    OpenProblem,
    ShowStacked,
    OverlayFrame,
    Pill,
    Role,
    Spring,
    Stroke,
    Target,
)
from app.features.form_builder.qtside.canvas.core.gesture import (
    Banding,
    Gesture,
    Idle,
    Moving,
    Placing,
    PageResizing,
    Turning,
    band_hits,
    band_rect,
    drawn_rect,
    page_size,
    previewing,
    turned,
)
from app.features.form_builder.qtside.canvas.core.space import CanvasRect, CanvasSize, Compass, ViewMap
from app.features.form_builder.qtside.canvas.core.structure import (
    LaidOut,
    ancestors,
    effective_class,
    effective_selection,
    managed_container,
    positioning_of,
)
from app.features.form_builder.qtside.canvas.core.words import chip_text, no_layout_text

#: UX-EMPTY-002 canvas-only minimum for an empty layout or container mark.
EMPTY_MIN_WIDTH = 48
EMPTY_MIN_HEIGHT = 32
EMPTY_CAPTION_MIN_WIDTH = 120

# A childless one of these is an empty container. A button or a label is not.
_EMPTY_CONTAINER = frozenset({"QWidget", "QFrame", "QGroupBox", "QDialog", "QScrollArea"})

LABEL_HEIGHT = 18
LABEL_PADDING = 6
BADGE_SLOT = 16
HANDLE_SIZE = 7
HANDLE_HIT = 12
PILL_LONG = 32
PILL_SHORT = 4
#: Gap bars are this many screen pixels across at every zoom.
GAP_BAR = 2
GRIP_GLYPH = CanvasSize(6, 16)
_INERT_HANDLES: Tuple[Compass, ...] = ("e", "s", "se")
_THIN_KINDS = frozenset({"gap", "margin"})
_TICK_CORNERS: Dict[str, Tuple[Corner, ...]] = {
    "top": ("above_left", "above_right"),
    "bottom": ("below_left", "below_right"),
}

_EMPTY_FORM = (
    "Drop a widget here",
    "or press / to search for one.",
    "/ insert · Ctrl+Shift+G wrap · F2 rename",
)
_EMPTY_NESTED = "Drop widgets here"
_EMPTY_PAGE = "Drop widgets on this page"
_PAGE_PARENTS = frozenset({"QTabWidget", "QStackedWidget", "QToolBox"})
_PLUS = 12
_TITLES = frozenset({"page_tab", "menu_title"})
_DESCENDS = frozenset({"widget", "layout"})


@dataclass(frozen=True)
class StaticLayer:
    epoch: int
    view: ViewMap
    #: Layout frames, spacer springs, empty marks, "No layout" frames. Paint order.
    items: Tuple[Item, ...]
    #: Visible widget and spacer rects clipped to the page, for the solver.
    content: Tuple[Obstacle, ...]
    #: Containers with children and no layout, excluding the root, in pre-order.
    unlaid: Tuple[NodeId, ...]
    #: Empty-mark targets. A click selects the empty layout.
    targets: Tuple[Tuple[CanvasRect, Target], ...]
    #: Unclipped canvas rect of every visible widget, layout and spacer.
    placed: Tuple[Obstacle, ...]
    #: Tab-title rects. ``(tab widget, canvas rect of one title)``.
    tabs: Tuple[Tuple[NodeId, CanvasRect], ...] = ()
    #: Stacked widgets. ``(widget, canvas rect, page object names)``.
    stacks: Tuple[Tuple[NodeId, CanvasRect, Tuple[str, ...]], ...] = ()
    #: Visible splitters in pre-order. Their grips are hittable with any selection.
    splitters: Tuple[NodeId, ...] = ()


@dataclass(frozen=True)
class FrameInputs:
    document: UiDocument
    selection: SelectionState
    gesture: Gesture
    view: ViewMap
    focused: bool
    #: First error message per node, from ``DiagnosticsStore``.
    problems: Mapping[NodeId, str]
    problems_revision: int
    #: The primary's (width, height) words, read from the live widget.
    sizing: Optional[Tuple[Optional[str], Optional[str]]]
    #: Page chip and size readout label rects. Backdrop chrome, not overlay chips.
    chrome: Tuple[CanvasRect, ...]
    #: Advance of chip text at 11 px semibold. The only font fact needed.
    measure: Callable[[str], int]
    #: Visible canvas. None keeps a loose gutter around the page for callers
    #: that have not measured the viewport yet.
    viewport: Optional[CanvasRect] = None
    #: Chrome strip for a selection chip with no clear seat (the page caption).
    dock: Optional[CanvasRect] = None
    #: Where Enter would insert, drawn while the Insert list has a tile focused.
    preview: Optional[AcceptedDrop] = None
    #: Canvas-only page shown for a stacked widget. Absent keys use the property.
    shown_pages: Optional[Mapping[NodeId, int]] = None
    #: Knobs measured from live geometry for the selection's neighbourhood.
    knobs: KnobSet = EMPTY
    #: What a landed knob commit still reads. The controller clears it.
    readout: Optional[Readout] = None


@dataclass(frozen=True)
class _Face:
    kind: Literal["chip", "badge"]
    node: NodeId
    role: Role
    text: str
    action: Optional[ChipAction]
    tip: str = ""


def build_static(document: UiDocument, index: HitIndex, view: ViewMap) -> StaticLayer:
    """Caller has made ``index`` fresh."""
    page = view.page_rect()
    visible, titles = _visible(index, document.root.id)
    root_layout = document.root.layout
    layouts: List[Item] = []
    springs: List[Item] = []
    empties: List[Item] = []
    bare: List[Item] = []
    content: List[Obstacle] = []
    placed: List[Obstacle] = []
    unlaid: List[NodeId] = []
    targets: List[Tuple[CanvasRect, Target]] = []
    tabs: List[Tuple[NodeId, CanvasRect]] = []
    stacks: List[Tuple[NodeId, CanvasRect, Tuple[str, ...]]] = []
    splitters: List[NodeId] = []

    for node in document.iter_preorder():
        if node.id != document.root.id and not visible.get(node.id, False):
            continue
        form_rect = index.rect_of(node.id)
        if form_rect is None:
            continue
        canvas = view.to_canvas(form_rect)
        if isinstance(node, LayoutNode):
            placed.append(Obstacle(node.id, canvas))
            layouts.append(Stroke(canvas, "layout_faint", 1, "dashed"))
            if _layout_filled(node):
                continue
            if root_layout is not None and node.id == root_layout.id:
                empties.append(Caption(canvas, _EMPTY_FORM))
                targets.append((canvas, OnSpace(node.id, node.id)))
            else:
                _empty_mark(
                    empties,
                    targets,
                    canvas,
                    OnSpace(node.id, node.id),
                    _drop_caption(document, node),
                )
            continue
        if isinstance(node, SpacerNode):
            placed.append(Obstacle(node.id, canvas))
            springs.append(Spring(canvas, _spacer_axis(node)))
            continue
        if not isinstance(node, WidgetNode):
            continue
        placed.append(Obstacle(node.id, canvas))
        if effective_class(document, node) == "QSplitter":
            splitters.append(node.id)
        if node.class_name == "QStackedWidget" and node.child_widgets:
            names = tuple(child.object_name or "page" for child in node.child_widgets)
            stacks.append((node.id, canvas, names))
        clipped = _clip(canvas, page)
        if clipped is not None:
            content.append(Obstacle(node.id, clipped))
        if node.id == document.root.id or managed_container(document, node):
            continue
        if node.layout is not None:
            continue
        if node.child_widgets:
            unlaid.append(node.id)
            bare.append(Stroke(canvas, "tab", 1, "dashed"))
        elif effective_class(document, node) in _EMPTY_CONTAINER:
            # The body stays a widget hit so a drag moves the container.
            _empty_mark(
                empties,
                targets,
                canvas,
                OnWidget(node.id, positioning_of(document, node.id), "widget"),
                _drop_caption(document, node),
            )

    for obstacle in placed:
        found = document.get(obstacle.node)
        if isinstance(found, SpacerNode):
            clipped = _clip(obstacle.rect, page)
            if clipped is not None:
                content.append(Obstacle(obstacle.node, clipped))
    for entry in titles:
        clipped = _clip(view.to_canvas(entry.rect), page)
        if clipped is not None:
            content.append(Obstacle(entry.node, clipped))
        if entry.kind == "page_tab" and entry.container is not None:
            tabs.append((entry.container, view.to_canvas(entry.rect)))
    for entry in index.title_entries():
        if entry.kind == "page_tab" and entry.container is not None:
            tabs.append((entry.container, view.to_canvas(entry.rect)))

    return StaticLayer(
        index.epoch,
        view,
        tuple(layouts + springs + empties + bare),
        tuple(content),
        tuple(unlaid),
        tuple(targets),
        tuple(placed),
        tuple(tabs),
        tuple(stacks),
        tuple(splitters),
    )


def shift_static(
    layer: StaticLayer,
    view: ViewMap,
    updates: Mapping[NodeId, Rect],
) -> Optional[StaticLayer]:
    """Move obstacles whose form rect changed. None means the caller rebuilds.

    Layout strokes carry no node id, so a layout move is a rebuild. A widget
    or spacer that was not placed is a rebuild too.
    """
    if not updates:
        return layer
    page = view.page_rect()
    placed: List[Obstacle] = []
    previous = {}
    found = set()
    for obstacle in layer.placed:
        rect = updates.get(obstacle.node)
        if rect is None:
            placed.append(obstacle)
            previous.setdefault(obstacle.node, obstacle.rect)
            continue
        canvas = view.to_canvas(rect)
        placed.append(Obstacle(obstacle.node, canvas))
        previous.setdefault(obstacle.node, obstacle.rect)
        found.add(obstacle.node)
    if found != set(updates):
        return None
    content: List[Obstacle] = []
    seen = set()
    for obstacle in layer.content:
        rect = updates.get(obstacle.node)
        old = previous.get(obstacle.node)
        if rect is None or old is None or not _same_canvas(obstacle.rect, old, page):
            content.append(obstacle)
            continue
        seen.add(obstacle.node)
        clipped = _clip(view.to_canvas(rect), page)
        if clipped is not None:
            content.append(Obstacle(obstacle.node, clipped))
    for node, rect in updates.items():
        if node in seen:
            continue
        clipped = _clip(view.to_canvas(rect), page)
        if clipped is not None:
            content.append(Obstacle(node, clipped))
    return StaticLayer(
        layer.epoch,
        layer.view,
        layer.items,
        tuple(content),
        layer.unlaid,
        layer.targets,
        tuple(placed),
        splitters=layer.splitters,
    )


def build_frame(static: StaticLayer, inputs: FrameInputs) -> OverlayFrame:
    """Static layer, then hover, selection, handles, grabbers, focus, band, chips.

    During a live preview the static layer is omitted. The moved widgets and
    the page's reflowed layouts no longer match the frozen index.
    """
    document = inputs.document
    gesture = inputs.gesture
    view = inputs.view
    shown = effective_selection(document, inputs.selection)
    live = previewing(gesture)
    items: List[Item] = []
    if not live:
        items.extend(static.items)
        _sites(items, view, inputs.knobs)
    _hover(items, static, document, gesture)
    rects: Dict[NodeId, CanvasRect] = {}
    for node_id in shown.ids:
        rect = _shown_rect(static, view, document, gesture, node_id)
        if rect is not None:
            rects[node_id] = rect
            found = document.get(node_id)
            if isinstance(found, LayoutNode):
                items.append(Stroke(rect, "layout", 1.5, "solid"))
            else:
                items.append(Stroke(rect.grown(1), "select", 2, "solid"))

    primary = shown.current
    primary_rect = rects.get(primary) if primary is not None else None
    knob_hits = _knob_handles(items, inputs.knobs, primary, primary_rect)
    inert_hits = _inert_handles(items, document, primary, primary_rect)
    page, hot = _page_canvas(view, gesture)
    grabbers = _grabbers(page, hot)
    items.extend(grabbers)
    if inputs.focused and primary is not None and primary_rect is not None:
        if not isinstance(document.get(primary), LayoutNode):
            items.append(Stroke(primary_rect.grown(3), "select", 1, "dotted"))
    if isinstance(gesture, Banding):
        _band(items, view, gesture)
    if isinstance(gesture, Turning):
        _turn_mark(items, view, turned(gesture))
    else:
        _grip_hover(items, view, inputs.knobs, gesture)
    _drop_marks(items, view, inputs)
    plus_hits = _plus_hits(items, static, document, gesture, shown)

    faces, requests = _requests(static, inputs, shown, rects)
    fixed = tuple(hit for hit, _target in knob_hits + inert_hits) + inputs.chrome
    viewport = inputs.viewport if inputs.viewport is not None else page.grown(400)
    seats = place_chips(requests, static.content, fixed, page, viewport, inputs.dock)
    chip_hits, chip_rows = _seat_items(items, seats, faces, inputs.dock is not None)
    targets: List[Tuple[CanvasRect, Target]] = []
    targets.extend(reversed(plus_hits))
    targets.extend(reversed(chip_hits))
    targets.extend((pill.rect, OnPageEdge(pill.at)) for pill in reversed(grabbers))
    targets.extend(reversed(knob_hits))
    if not live:
        targets.extend((view.to_canvas(site.hit), OnKnob(site.knob)) for site in inputs.knobs.sites)
    targets.extend(reversed(inert_hits))
    if not live:
        targets.extend(static.targets)
    return OverlayFrame(
        FrameBasis(static.epoch, view, inputs.selection, inputs.problems_revision),
        tuple(items),
        tuple(targets),
        tuple(chip_rows),
        inputs.dock,
    )


def frame_basis(
    index: HitIndex, view: ViewMap, selection: SelectionState, problems_revision: int
) -> FrameBasis:
    return FrameBasis(index.epoch, view, selection, problems_revision)


def _visible(index: HitIndex, root: NodeId) -> Tuple[Dict[NodeId, bool], Tuple[GeoEntry, ...]]:
    flags = {root: True}
    titles: List[GeoEntry] = []
    stack = [root]
    while stack:
        parent = stack.pop()
        for entry in index.children_of(parent):
            if entry.kind in _TITLES:
                if entry.visible:
                    titles.append(entry)
                continue
            flags[entry.node] = entry.visible
            if entry.kind in _DESCENDS:
                stack.append(entry.node)
    return flags, tuple(titles)


def _layout_filled(layout: LayoutNode) -> bool:
    return any(item.content is not None for item in layout.items)


def _spacer_axis(node: SpacerNode) -> Literal["horizontal", "vertical"]:
    value = node.value("orientation")
    if isinstance(value, EnumValue) and value.key()[1] == "Vertical":
        return "vertical"
    return "horizontal"


def _drop_caption(document: UiDocument, node: object) -> str:
    owner = getattr(node, "id", None)
    if isinstance(node, LayoutNode):
        found = node.owner_widget_id()
        if found is not None:
            owner = found
    parent = document.parent(owner) if owner is not None else None
    parent_node = document.get(parent) if parent is not None else None
    if isinstance(parent_node, WidgetNode) and parent_node.class_name in _PAGE_PARENTS:
        return _EMPTY_PAGE
    return _EMPTY_NESTED


def _empty_mark(
    items: List[Item],
    targets: List[Tuple[CanvasRect, Target]],
    canvas: CanvasRect,
    target: Target,
    caption: str = _EMPTY_NESTED,
) -> None:
    mark = _at_least(canvas, EMPTY_MIN_WIDTH, EMPTY_MIN_HEIGHT)
    items.append(Stroke(mark, "layout_faint", 1, "dashed"))
    if mark.width >= EMPTY_CAPTION_MIN_WIDTH:
        items.append(Caption(mark, (caption,)))
    else:
        items.append(Glyph(_centred(mark, _PLUS, _PLUS), "plus", "layout_faint"))
    targets.append((mark, target))


def _hover(
    items: List[Item], static: StaticLayer, document: UiDocument, gesture: Gesture
) -> None:
    if not isinstance(gesture, Idle) or gesture.hover is None:
        return
    found = document.get(gesture.hover)
    if isinstance(found, (WidgetNode, SpacerNode)):
        rect = _placed(static, gesture.hover)
        if rect is not None:
            items.append(Stroke(rect.grown(1), "hover", 1, "solid"))
    parent = _parent_layout(document, gesture.hover)
    if parent is None:
        return
    rect = _placed(static, parent)
    if rect is not None:
        items.append(Stroke(rect, "layout", 1, "solid", 0.6))


def _parent_layout(document: UiDocument, node: NodeId) -> Optional[NodeId]:
    place = positioning_of(document, node)
    if isinstance(place, LaidOut):
        return place.layout
    return None


def _knob_handles(
    items: List[Item],
    knobs: KnobSet,
    primary: Optional[NodeId],
    rect: Optional[CanvasRect],
) -> List[Tuple[CanvasRect, Target]]:
    """The primary widget's size handles. Each one turns a knob."""
    if primary is None or rect is None:
        return []
    hits: List[Tuple[CanvasRect, Target]] = []
    for knob in knobs.handles:
        if knob.subject != primary:
            continue
        centre = _handle_point(rect, knob.pull)
        items.append(Handle(_around(centre, HANDLE_SIZE), knob.pull))
        hits.append((_around(centre, HANDLE_HIT), OnKnob(knob)))
    return hits


def _inert_handles(
    items: List[Item],
    document: UiDocument,
    primary: Optional[NodeId],
    rect: Optional[CanvasRect],
) -> List[Tuple[CanvasRect, Target]]:
    """A selected layout or spacer shows where its size comes from. Its handles write nothing."""
    if primary is None or rect is None or not isinstance(document.get(primary), (LayoutNode, SpacerNode)):
        return []
    hits: List[Tuple[CanvasRect, Target]] = []
    for at in _INERT_HANDLES:
        centre = _handle_point(rect, at)
        items.append(Handle(_around(centre, HANDLE_SIZE), at))
        hits.append((_around(centre, HANDLE_HIT), OnHandle(primary, at)))
    return hits


def _sites(items: List[Item], view: ViewMap, knobs: KnobSet) -> None:
    """Gap bars, margin bands and root-layout ticks. Grips draw only under the pointer."""
    for site in knobs.sites:
        if site.look == "bar":
            items.append(Fill(_thin(view.to_canvas(site.mark), GAP_BAR), "gap"))
        elif site.look == "band":
            band = view.to_canvas(site.mark)
            if band.width > 0 and band.height > 0:
                items.append(Fill(band, "gap_fill"))
    for tick in knobs.ticks:
        items.append(Stroke(view.to_canvas(tick.rect), "layout", 1.5, "solid", caps=True))


def _turn_mark(items: List[Item], view: ViewMap, done: Turn) -> None:
    mark = done.mark
    if mark is None:
        return
    canvas = view.to_canvas(mark)
    kind = done.readout.key[0]
    if kind in _THIN_KINDS:
        items.append(Fill(canvas, "gap_fill"))
        items.append(Stroke(canvas, "gap", 1, "solid"))
    elif kind == "grip":
        items.append(Glyph(_grip_box(canvas), "grip", "select"))
    else:
        items.append(Fill(canvas, "drop_fill"))
        items.append(Stroke(canvas, "select", 1.5, "dashed"))


def _grip_hover(items: List[Item], view: ViewMap, knobs: KnobSet, gesture: Gesture) -> None:
    """The splitter's own handle stays visible. The glyph sits on top of it."""
    if not isinstance(gesture, Idle) or gesture.knob is None or gesture.knob[0] != "grip":
        return
    for site in knobs.sites:
        if site.knob.key == gesture.knob:
            items.append(Glyph(_grip_box(view.to_canvas(site.mark)), "grip", "select"))
            return


def _thin(rect: CanvasRect, across: int) -> CanvasRect:
    if rect.width <= rect.height:
        return CanvasRect(rect.x + rect.width // 2 - across // 2, rect.y, across, rect.height)
    return CanvasRect(rect.x, rect.y + rect.height // 2 - across // 2, rect.width, across)


def _grip_box(handle: CanvasRect) -> CanvasRect:
    if handle.width <= handle.height:
        return _centred(handle, GRIP_GLYPH.width, GRIP_GLYPH.height)
    return _centred(handle, GRIP_GLYPH.height, GRIP_GLYPH.width)


def _grabbers(page: CanvasRect, hot: bool) -> Tuple[Pill, ...]:
    east = Pill(
        CanvasRect(
            page.x + page.width - PILL_SHORT // 2,
            page.y + page.height // 2 - PILL_LONG // 2,
            PILL_SHORT,
            PILL_LONG,
        ),
        "e",
        hot,
    )
    south = Pill(
        CanvasRect(
            page.x + page.width // 2 - PILL_LONG // 2,
            page.y + page.height - PILL_SHORT // 2,
            PILL_LONG,
            PILL_SHORT,
        ),
        "s",
        hot,
    )
    return (east, south)


def _shown_drop(inputs: FrameInputs) -> Optional[Tuple[Union[AcceptedDrop, RefusedDrop], str]]:
    gesture = inputs.gesture
    if isinstance(gesture, Placing) and not gesture.outside and gesture.draw:
        if isinstance(gesture.target, NoDrop):
            return None
        return gesture.target, gesture.token
    if inputs.preview is not None and not isinstance(gesture, (Placing, Moving)):
        return inputs.preview, "preview"
    return None


def _drop_chip(
    faces: Dict[Hashable, _Face],
    requests: List[ChipRequest],
    inputs: FrameInputs,
) -> None:
    shown = _shown_drop(inputs)
    if shown is None:
        return
    target, token = shown
    text = target.chip or target.sentence
    if not text:
        return
    host = target.host if isinstance(target, (AcceptedDrop, RefusedDrop)) and target.host is not None else inputs.document.root.id
    role: Role = "problem" if isinstance(target, RefusedDrop) or target.indicator.role == "problem" else "select"
    _ask(
        faces,
        requests,
        ("drop", token),
        inputs.view.to_canvas(target.indicator.rect),
        _label_size(text, inputs.measure),
        LABEL_CORNERS,
        inputs.document,
        _Face("chip", host, role, text, None),
        required=True,
    )


def _drop_marks(items: List[Item], view: ViewMap, inputs: FrameInputs) -> None:
    shown = _shown_drop(inputs)
    if shown is None:
        return
    target = shown[0]
    if isinstance(target, NoDrop):
        return
    role: Role = "problem" if isinstance(target, RefusedDrop) else "layout"
    items.append(Stroke(view.to_canvas(target.frame), role, 1.5, "solid"))
    indicator = target.indicator
    paint: Role = "problem" if indicator.role == "problem" else "select"
    rect = view.to_canvas(indicator.rect)
    if indicator.dashed and indicator.role != "problem":
        items.append(Fill(rect, "drop_fill"))
    thin = min(rect.width, rect.height) <= 4
    items.append(
        Stroke(
            rect,
            paint,
            1.5 if indicator.dashed else 2,
            "dashed" if indicator.dashed else "solid",
            caps=thin and not indicator.dashed,
        )
    )


def _band(items: List[Item], view: ViewMap, gesture: Banding) -> None:
    area = view.to_canvas(band_rect(gesture))
    items.append(Fill(area, "drop_fill"))
    items.append(Stroke(area, "select", 1, "solid"))
    hit_ids = set(band_hits(gesture))
    for node, form_rect in gesture.candidates:
        if node not in hit_ids:
            continue
        items.append(Stroke(view.to_canvas(form_rect).grown(1), "hover", 1, "solid"))


def _requests(
    static: StaticLayer,
    inputs: FrameInputs,
    shown: SelectionState,
    rects: Mapping[NodeId, CanvasRect],
) -> Tuple[Dict[Hashable, _Face], List[ChipRequest]]:
    document = inputs.document
    faces: Dict[Hashable, _Face] = {}
    requests: List[ChipRequest] = []
    _drop_chip(faces, requests, inputs)
    primary = shown.current
    placing = isinstance(inputs.gesture, Placing)
    readout = turned(inputs.gesture).readout if isinstance(inputs.gesture, Turning) else inputs.readout
    if not placing and primary is not None and primary in rects and primary != document.root.id:
        text = chip_text(document, inputs.selection, inputs.sizing)
        if readout is not None and readout.key[0] == "size" and readout.key[1] == primary:
            text = readout.text
        role: Role = "layout" if isinstance(document.get(primary), LayoutNode) else "select"
        _ask(
            faces,
            requests,
            ("chip", primary),
            rects[primary],
            _label_size(text, inputs.measure),
            LABEL_CORNERS,
            document,
            _Face("chip", primary, role, text, None),
            required=True,
        )
    if readout is not None and readout.key[0] != "size":
        _readout_chip(faces, requests, inputs, readout)
    if not previewing(inputs.gesture):
        _knob_chips(faces, requests, inputs)
    # An empty map must not walk the form. Selection repaint is on an 8 ms budget.
    if inputs.problems:
        for node in document.iter_preorder():
            message = inputs.problems.get(node.id)
            if not message:
                continue
            rect = _shown_rect(static, inputs.view, document, inputs.gesture, node.id)
            if rect is None:
                continue
            _ask(
                faces,
                requests,
                ("badge", node.id),
                rect,
                CanvasSize(BADGE_SLOT, BADGE_SLOT),
                BADGE_CORNERS,
                document,
                _Face("badge", node.id, "problem", message, OpenProblem(node.id, message)),
            )
    for node_id in static.unlaid:
        rect = _shown_rect(static, inputs.view, document, inputs.gesture, node_id)
        if rect is None:
            continue
        text = no_layout_text()
        _ask(
            faces,
            requests,
            ("bare", node_id),
            rect,
            _label_size(text, inputs.measure),
            BARE_CORNERS,
            document,
            _Face("chip", node_id, "tab", text, OpenLayoutPopover(node_id)),
            own_frame=True,
        )
    _page_chips(faces, requests, static, inputs)
    return faces, requests


def _readout_chip(
    faces: Dict[Hashable, _Face],
    requests: List[ChipRequest],
    inputs: FrameInputs,
    readout: Readout,
) -> None:
    """A gap, margin or grip reads its number beside the site, rebuilt or not."""
    anchor = next((site.mark for site in inputs.knobs.sites if site.knob.key == readout.key), readout.anchor)
    role: Role = "gap" if readout.key[0] in _THIN_KINDS else "select"
    _ask(
        faces,
        requests,
        ("readout", readout.key),
        inputs.view.to_canvas(anchor),
        _label_size(readout.text, inputs.measure),
        LABEL_CORNERS,
        inputs.document,
        _Face("chip", readout.key[1], role, readout.text, None),
        required=True,
    )


def _knob_chips(faces: Dict[Hashable, _Face], requests: List[ChipRequest], inputs: FrameInputs) -> None:
    """Share chips, then the root layout's margin numbers in the gutter."""
    view = inputs.view
    for tag in inputs.knobs.shares:
        _ask(
            faces,
            requests,
            tag.key,
            view.to_canvas(tag.anchor),
            _label_size(tag.text, inputs.measure),
            LABEL_CORNERS,
            inputs.document,
            _Face("chip", tag.node, "layout", tag.text, FocusShare(tag.node, tag.axis)),
        )
    root_layout = inputs.document.root.layout
    if root_layout is None:
        return
    for tick in inputs.knobs.ticks:
        text = str(tick.pixels)
        _ask(
            faces,
            requests,
            ("tick", tick.side),
            view.to_canvas(tick.rect),
            _label_size(text, inputs.measure),
            _TICK_CORNERS.get(tick.side, ()),
            inputs.document,
            _Face("chip", root_layout.id, "layout", text, None),
            outside=True,
        )


def _page_chips(
    faces: Dict[Hashable, _Face],
    requests: List[ChipRequest],
    static: StaticLayer,
    inputs: FrameInputs,
) -> None:
    shown = inputs.shown_pages or {}
    for node_id, rect, names in static.stacks:
        if not names:
            continue
        current = shown.get(node_id, 0)
        if node_id not in shown:
            node = inputs.document.get(node_id)
            if isinstance(node, WidgetNode):
                entry = node.prop("currentIndex")
                value = getattr(getattr(entry, "value", None), "value", None)
                if isinstance(value, int):
                    current = value
        current = max(0, min(len(names) - 1, current))
        text = "◀ %d / %d ▶" % (current + 1, len(names))
        _ask(
            faces,
            requests,
            ("stack", node_id),
            rect,
            _label_size(text, inputs.measure),
            LABEL_CORNERS,
            inputs.document,
            _Face("chip", node_id, "select", text, ShowStacked(node_id, 0), names[current]),
            required=True,
        )


def _plus_hits(
    items: List[Item],
    static: StaticLayer,
    document: UiDocument,
    gesture: Gesture,
    shown: SelectionState,
) -> List[Tuple[CanvasRect, Target]]:
    groups: Dict[NodeId, List[CanvasRect]] = {}
    for container, rect in static.tabs:
        groups.setdefault(container, []).append(rect)
    hits: List[Tuple[CanvasRect, Target]] = []
    hot = _plus_ids(gesture, shown)
    dragging = isinstance(gesture, Placing)
    for container, rects in groups.items():
        node = document.get(container)
        if not isinstance(node, WidgetNode) or node.class_name != "QTabWidget":
            continue
        pages = {page.id for page in node.child_widgets}
        if not dragging and container not in hot and not pages.intersection(hot):
            continue
        last = max(rects, key=lambda rect: rect.x + rect.width)
        side = max(last.height, 18)
        plus = CanvasRect(last.x + last.width + 4, last.y, side, side)
        items.append(Chip(plus, "+", "select", None))
        hits.append((plus, OnChip(AddPage(container))))
    return hits


def _plus_ids(gesture: Gesture, shown: SelectionState) -> Set[NodeId]:
    found = set(shown.ids)
    if isinstance(gesture, Idle) and gesture.hover is not None:
        found.add(gesture.hover)
    return found


def _ask(
    faces: Dict[Hashable, _Face],
    requests: List[ChipRequest],
    key: Hashable,
    target: CanvasRect,
    size: CanvasSize,
    corners: Tuple[Corner, ...],
    document: UiDocument,
    face: _Face,
    required: bool = False,
    own_frame: bool = False,
    outside: bool = False,
) -> None:
    faces[key] = face
    exempt = ancestors(document, face.node)
    if own_frame:
        exempt = exempt | {face.node}
    requests.append(ChipRequest(key, target, size, corners, exempt, required=required, outside=outside))


def _seat_items(
    items: List[Item],
    seats: Sequence[ChipSeat],
    faces: Mapping[Hashable, _Face],
    chrome_dock: bool,
) -> Tuple[List[Tuple[CanvasRect, Target]], List[Tuple[CanvasRect, NodeId]]]:
    hits: List[Tuple[CanvasRect, Target]] = []
    rows: List[Tuple[CanvasRect, NodeId]] = []
    for seat in seats:
        face = faces[seat.key]
        leader = None if isinstance(seat, CornerSeat) else seat.leader
        if face.kind == "badge":
            items.append(Badge(seat.rect, "error", face.role, leader))
        else:
            items.append(
                Chip(seat.rect, face.text, face.role, leader, chrome_dock and isinstance(seat, DockSeat), face.tip)
            )
        rows.append((seat.rect, face.node))
        if isinstance(face.action, ShowStacked) and face.action.delta == 0:
            third = max(seat.rect.width // 3, 1)
            left = CanvasRect(seat.rect.x, seat.rect.y, third, seat.rect.height)
            right = CanvasRect(seat.rect.x + seat.rect.width - third, seat.rect.y, third, seat.rect.height)
            hits.append((left, OnChip(ShowStacked(face.action.container, -1))))
            hits.append((right, OnChip(ShowStacked(face.action.container, 1))))
        elif face.action is not None:
            hits.append((seat.rect, OnChip(face.action)))
    return hits, rows


def _shown_rect(
    static: StaticLayer,
    view: ViewMap,
    document: UiDocument,
    gesture: Gesture,
    node: NodeId,
) -> Optional[CanvasRect]:
    if isinstance(gesture, Moving):
        for item in gesture.items:
            if item.node == node:
                return view.to_canvas(drawn_rect(gesture, item))
    if isinstance(gesture, Turning) and gesture.knob.subject == node:
        outline = turned(gesture).outline
        if outline is not None:
            return view.to_canvas(outline)
    if isinstance(gesture, PageResizing) and node == document.root.id:
        return _page_canvas(view, gesture)[0]
    return _placed(static, node)


def _placed(static: StaticLayer, node: NodeId) -> Optional[CanvasRect]:
    for obstacle in static.placed:
        if obstacle.node == node:
            return obstacle.rect
    return None


def _page_canvas(view: ViewMap, gesture: Gesture) -> Tuple[CanvasRect, bool]:
    if isinstance(gesture, PageResizing):
        size = page_size(gesture)
        return (
            CanvasRect(
                view.page_origin.x,
                view.page_origin.y,
                max(1, int(round(size.width * view.factor))),
                max(1, int(round(size.height * view.factor))),
            ),
            True,
        )
    return view.page_rect(), False


def _handle_point(rect: CanvasRect, at: Compass) -> Tuple[int, int]:
    left = rect.x - 1
    right = rect.x + rect.width + 1
    top = rect.y - 1
    bottom = rect.y + rect.height + 1
    mid_x = rect.x + rect.width // 2
    mid_y = rect.y + rect.height // 2
    points = {
        "nw": (left, top),
        "n": (mid_x, top),
        "ne": (right, top),
        "e": (right, mid_y),
        "se": (right, bottom),
        "s": (mid_x, bottom),
        "sw": (left, bottom),
        "w": (left, mid_y),
    }
    return points[at]


def _around(point: Tuple[int, int], size: int) -> CanvasRect:
    x, y = point
    return CanvasRect(x - size // 2, y - size // 2, size, size)


def _at_least(rect: CanvasRect, min_width: int, min_height: int) -> CanvasRect:
    width = max(rect.width, min_width)
    height = max(rect.height, min_height)
    return CanvasRect(
        rect.x - (width - rect.width) // 2,
        rect.y - (height - rect.height) // 2,
        width,
        height,
    )


def _centred(host: CanvasRect, width: int, height: int) -> CanvasRect:
    return CanvasRect(
        host.x + (host.width - width) // 2,
        host.y + (host.height - height) // 2,
        width,
        height,
    )


def _same_canvas(rect: CanvasRect, placed: CanvasRect, page: CanvasRect) -> bool:
    """True when ``rect`` is the placed widget, or that widget clipped to the page.

    A tab title shares its page's node id and a different rect, so a page move
    must not drag the title.
    """
    if rect == placed:
        return True
    clipped = _clip(placed, page)
    return clipped is not None and rect == clipped


def _clip(rect: CanvasRect, page: CanvasRect) -> Optional[CanvasRect]:
    left = max(rect.x, page.x)
    top = max(rect.y, page.y)
    right = min(rect.x + rect.width, page.x + page.width)
    bottom = min(rect.y + rect.height, page.y + page.height)
    if right <= left or bottom <= top:
        return None
    return CanvasRect(left, top, right - left, bottom - top)


def _label_size(text: str, measure: Callable[[str], int]) -> CanvasSize:
    return CanvasSize(max(1, measure(text) + 2 * LABEL_PADDING), LABEL_HEIGHT)
