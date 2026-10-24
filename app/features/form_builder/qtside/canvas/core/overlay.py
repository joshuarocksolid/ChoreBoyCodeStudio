"""Builds the overlay frame. Qt-free.

Two layers. The static layer depends only on the document, the fresh index
and the view map, and is cached on (epoch, view). The dynamic layer adds
selection, hover, the gesture, focus, chips and badges, and is rebuilt per
frame. Neither reads Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Hashable, List, Literal, Mapping, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.hit_index import GeoEntry, HitIndex, Rect
from app.features.form_builder.engine.query.selection import SelectionState
from app.features.form_builder.engine.query.slots import (
    CellMark,
    DropPaint,
    FrameMark,
    GapMark,
    GhostMark,
    NoMark,
    PageControl,
)
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutNode, SpacerNode, WidgetNode
from app.features.form_builder.engine.ui4.values import EnumValue, NumberValue
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
    FrameBasis,
    Glyph,
    Handle,
    Item,
    OnChip,
    OnHandle,
    OnPageEdge,
    OnSpace,
    OnWidget,
    OpenLayoutPopover,
    OpenProblem,
    OverlayFrame,
    Pill,
    Role,
    ShowCanvasPage,
    Spring,
    StackPager,
    Stroke,
    Target,
)
from app.features.form_builder.qtside.canvas.core.gesture import (
    Banding,
    Gesture,
    Idle,
    Moving,
    PageResizing,
    Resizing,
    band_hits,
    band_rect,
    drawn_rect,
    handles_for,
    page_size,
    previewing,
    resized_drawn,
)
from app.features.form_builder.qtside.canvas.core.space import (
    CanvasPoint,
    CanvasRect,
    CanvasSize,
    Compass,
    ViewMap,
)
from app.features.form_builder.qtside.canvas.core.structure import (
    Free,
    LaidOut,
    Positioning,
    ancestors,
    effective_class,
    effective_selection,
    managed_container,
    positioning_of,
)
from app.features.form_builder.qtside.canvas.core.words import SizingWord, chip_text, no_layout_text

#: UX-EMPTY-002 canvas-only minimum for an empty layout or container mark.
EMPTY_MIN_WIDTH = 48
EMPTY_MIN_HEIGHT = 32
EMPTY_CAPTION_MIN_WIDTH = 120

# A childless one of these is an empty container. A button or a label is not.
_EMPTY_CONTAINER = frozenset({"QWidget", "QFrame", "QGroupBox", "QDialog", "QScrollArea"})
_STACKED = frozenset({"QStackedWidget", "QToolBox"})

LABEL_HEIGHT = 18
LABEL_PADDING = 6
BADGE_SLOT = 16
HANDLE_SIZE = 7
HANDLE_HIT = 12
PILL_LONG = 32
PILL_SHORT = 4

_EMPTY_FORM = (
    "Drop a widget here",
    "or press / to search for one.",
    "/ insert · Ctrl+Shift+G wrap · F2 rename",
)
_EMPTY_NESTED = "Drop widgets here"
_EMPTY_PAGE = "Drop widgets on this page"
_PAGE_HOSTS = frozenset({"QTabWidget", "QStackedWidget", "QToolBox"})
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
    sizing: Optional[Tuple[Optional[SizingWord], Optional[SizingWord]]]
    #: Page chip and size readout label rects. Backdrop chrome, not overlay chips.
    chrome: Tuple[CanvasRect, ...]
    #: Advance of chip text at 11 px semibold. The only font fact needed.
    measure: Callable[[str], int]
    #: Visible canvas. None keeps a loose gutter around the page for callers
    #: that have not measured the viewport yet.
    viewport: Optional[CanvasRect] = None
    #: Chrome strip for a selection chip with no clear seat (the page caption).
    dock: Optional[CanvasRect] = None
    paint: Optional[DropPaint] = None


@dataclass(frozen=True)
class _Face:
    kind: Literal["chip", "badge"]
    node: NodeId
    role: Role
    text: str
    action: Optional[ChipAction]


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
                    _empty_words(document, node),
                )
            continue
        if isinstance(node, SpacerNode):
            placed.append(Obstacle(node.id, canvas))
            springs.append(Spring(canvas, _spacer_axis(node)))
            continue
        if not isinstance(node, WidgetNode):
            continue
        placed.append(Obstacle(node.id, canvas))
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
                _empty_words(document, node),
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

    return StaticLayer(
        index.epoch,
        view,
        tuple(layouts + springs + empties + bare),
        tuple(content),
        tuple(unlaid),
        tuple(targets),
        tuple(placed),
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
    items: List[Item] = []
    if not previewing(gesture):
        items.extend(static.items)
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
    place = positioning_of(document, primary) if primary is not None else None
    handle_hits = _handles(items, primary, primary_rect, place)
    page, hot = _page_canvas(view, gesture)
    grabbers = _grabbers(page, hot)
    items.extend(grabbers)
    if inputs.focused and primary is not None and primary_rect is not None:
        if not isinstance(document.get(primary), LayoutNode):
            items.append(Stroke(primary_rect.grown(3), "select", 1, "dotted"))
    if isinstance(gesture, Banding):
        _band(items, view, gesture)

    faces, requests = _requests(static, inputs, shown, rects)
    _drop_paint(items, faces, requests, inputs)
    _page_arrows(faces, requests, static, inputs)
    fixed = tuple(hit for hit, _target in handle_hits) + inputs.chrome
    viewport = inputs.viewport if inputs.viewport is not None else page.grown(400)
    seats = place_chips(requests, static.content, fixed, page, viewport, inputs.dock)
    chip_hits, chip_rows = _seat_items(items, seats, faces, inputs.dock is not None)
    controls = _page_controls(seats, view)
    targets: List[Tuple[CanvasRect, Target]] = []
    targets.extend(reversed(chip_hits))
    targets.extend((pill.rect, OnPageEdge(pill.at)) for pill in reversed(grabbers))
    targets.extend(reversed(handle_hits))
    if not previewing(gesture):
        targets.extend(static.targets)
    return OverlayFrame(
        FrameBasis(static.epoch, view, inputs.selection, inputs.problems_revision),
        tuple(items),
        tuple(targets),
        tuple(chip_rows),
        inputs.dock,
        controls,
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


def _empty_words(document: UiDocument, node: Union[LayoutNode, WidgetNode]) -> str:
    widget_id = node.owner_widget_id() if isinstance(node, LayoutNode) else node.id
    if widget_id is None:
        return _EMPTY_NESTED
    parent = document.parent(widget_id)
    if isinstance(parent, WidgetNode) and parent.class_name in _PAGE_HOSTS:
        return _EMPTY_PAGE
    return _EMPTY_NESTED


def _empty_mark(
    items: List[Item],
    targets: List[Tuple[CanvasRect, Target]],
    canvas: CanvasRect,
    target: Target,
    words: str,
) -> None:
    mark = _at_least(canvas, EMPTY_MIN_WIDTH, EMPTY_MIN_HEIGHT)
    items.append(Stroke(mark, "layout_faint", 1, "dashed"))
    if mark.width >= EMPTY_CAPTION_MIN_WIDTH:
        items.append(Caption(mark, (words,)))
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


def _handles(
    items: List[Item],
    primary: Optional[NodeId],
    rect: Optional[CanvasRect],
    place: Optional[Positioning],
) -> List[Tuple[CanvasRect, Target]]:
    if primary is None or rect is None or place is None:
        return []
    writes = isinstance(place, Free)
    hits: List[Tuple[CanvasRect, Target]] = []
    for at in handles_for(place):
        centre = _handle_point(rect, at)
        items.append(Handle(_around(centre, HANDLE_SIZE), at))
        hits.append((_around(centre, HANDLE_HIT), OnHandle(primary, at, writes)))
    return hits


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


def _band(items: List[Item], view: ViewMap, gesture: Banding) -> None:
    area = view.to_canvas(band_rect(gesture))
    items.append(Fill(area, "drop_fill"))
    items.append(Stroke(area, "select", 1, "solid"))
    hit_ids = set(band_hits(gesture))
    for node, form_rect in gesture.candidates:
        if node not in hit_ids:
            continue
        items.append(Stroke(view.to_canvas(form_rect).grown(1), "hover", 1, "solid"))


def _drop_paint(
    items: List[Item],
    faces: Dict[Hashable, _Face],
    requests: List[ChipRequest],
    inputs: FrameInputs,
) -> None:
    paint = inputs.paint
    if paint is None or paint.where != "canvas" or isinstance(paint.mark, NoMark):
        return
    mark = paint.mark
    canvas = inputs.view.to_canvas(mark.rect)
    role: Role = "problem" if paint.trouble else "select"
    if isinstance(mark, CellMark):
        items.append(Stroke(canvas, role, 1, "dashed"))
        items.append(Fill(canvas, "drop_fill"))
    elif isinstance(mark, (GapMark, FrameMark, GhostMark)):
        style: Literal["solid", "dashed"] = "solid" if isinstance(mark, GapMark) else "dashed"
        width = 2.0 if isinstance(mark, GapMark) else 1.0
        items.append(Stroke(canvas, role, width, style))
    if paint.trouble or not paint.sentence:
        return
    text = paint.sentence
    faces[("drop",)] = _Face("chip", inputs.document.root.id, role, text, None)
    requests.append(
        ChipRequest(
            ("drop",),
            canvas,
            _label_size(text, inputs.measure),
            LABEL_CORNERS,
            frozenset(),
            required=True,
        )
    )


def _page_arrows(
    faces: Dict[Hashable, _Face],
    requests: List[ChipRequest],
    static: StaticLayer,
    inputs: FrameInputs,
) -> None:
    document = inputs.document
    for node in document.iter_preorder():
        if not isinstance(node, WidgetNode) or node.class_name not in _STACKED:
            continue
        pages = node.child_widgets
        if len(pages) < 2:
            continue
        rect = _shown_rect(static, inputs.view, document, inputs.gesture, node.id)
        if rect is None:
            continue
        current = _stack_index(node)
        shown = current if 0 <= current < len(pages) else 0
        label = "◀ %d / %d ▶" % (shown + 1, len(pages))
        _ask(
            faces,
            requests,
            ("pager", node.id, shown, len(pages)),
            rect,
            _label_size(label, inputs.measure),
            ("above_left",),
            document,
            _Face(
                "chip",
                node.id,
                "select",
                label,
                StackPager(node.id, shown, len(pages), pages[shown].object_name),
            ),
        )


def _page_controls(seats: Sequence[ChipSeat], view: ViewMap) -> Tuple[PageControl, ...]:
    found: List[PageControl] = []
    for seat in seats:
        key = seat.key
        if not isinstance(key, tuple) or len(key) != 4 or key[0] != "pager":
            continue
        container, current, count = key[1], key[2], key[3]
        if not isinstance(current, int) or not isinstance(count, int):
            continue
        left, right = _halves(seat.rect)
        if current > 0:
            found.append(PageControl(_form_rect(view, left), container, current - 1))
        if current + 1 < count:
            found.append(PageControl(_form_rect(view, right), container, current + 1))
    return tuple(found)


def _halves(rect: CanvasRect) -> Tuple[CanvasRect, CanvasRect]:
    left_width = max(1, rect.width // 2)
    return (
        CanvasRect(rect.x, rect.y, left_width, rect.height),
        CanvasRect(rect.x + left_width, rect.y, max(1, rect.width - left_width), rect.height),
    )


def _stack_index(node: WidgetNode) -> int:
    entry = node.prop("currentIndex")
    if entry is None or not isinstance(entry.value, NumberValue):
        return 0
    return entry.value.value


def _form_rect(view: ViewMap, canvas: CanvasRect) -> Rect:
    origin = view.to_form(CanvasPoint(canvas.x, canvas.y))
    factor = view.factor if view.factor else 1.0
    return Rect(
        int(origin.x),
        int(origin.y),
        max(1, int(round(canvas.width / factor))),
        max(1, int(round(canvas.height / factor))),
    )


def _requests(
    static: StaticLayer,
    inputs: FrameInputs,
    shown: SelectionState,
    rects: Mapping[NodeId, CanvasRect],
) -> Tuple[Dict[Hashable, _Face], List[ChipRequest]]:
    document = inputs.document
    faces: Dict[Hashable, _Face] = {}
    requests: List[ChipRequest] = []
    primary = shown.current
    if primary is not None and primary in rects and primary != document.root.id:
        text = chip_text(document, inputs.selection, inputs.sizing)
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
    return faces, requests


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
) -> None:
    faces[key] = face
    exempt = ancestors(document, face.node)
    if own_frame:
        exempt = exempt | {face.node}
    requests.append(ChipRequest(key, target, size, corners, exempt, required=required))


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
            items.append(Chip(seat.rect, face.text, face.role, leader, chrome_dock and isinstance(seat, DockSeat)))
        rows.append((seat.rect, face.node))
        hits.extend(_chip_hits(seat.rect, face.action))
    return hits, rows


def _chip_hits(rect: CanvasRect, action: Optional[ChipAction]) -> List[Tuple[CanvasRect, Target]]:
    if isinstance(action, StackPager):
        left, right = _halves(rect)
        hits: List[Tuple[CanvasRect, Target]] = []
        if action.current > 0:
            hits.append((left, OnChip(ShowCanvasPage(action.container, action.current - 1, action.page_name))))
        if action.current + 1 < action.count:
            hits.append((right, OnChip(ShowCanvasPage(action.container, action.current + 1, action.page_name))))
        return hits
    if action is None:
        return []
    return [(rect, OnChip(action))]


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
    if isinstance(gesture, Resizing) and gesture.item.node == node:
        return view.to_canvas(resized_drawn(gesture))
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
