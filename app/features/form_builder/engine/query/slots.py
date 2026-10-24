"""Slot hits for a drag.

Public names are in ``__all__``. The layout rules live in the private
functions below ``resolve``. Do not split them into a package: a second
module becomes a second way to aim.

``resolve`` is called by ``engine/drop.py`` ``step`` and by tests. The
surface does not call it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Literal, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.commands.placement import (
    InBoxLayout,
    InContainer,
    InFormRow,
    InGridCell,
    Placement,
)
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.hit_index import GeoEntry, Rect
from app.features.form_builder.engine.query.tree import is_page_container
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import (
    LayoutItemNode,
    LayoutNode,
    SpacerNode,
    WidgetNode,
)
from app.features.form_builder.engine.ui4.values import RectValue

LABEL_CLASS = "QLabel"
SPACER_CLASS = "Spacer"

__all__ = [
    "LABEL_CLASS",
    "SPACER_CLASS",
    "Away",
    "Beside",
    "Buddy",
    "CanvasGeom",
    "Cargo",
    "CellMark",
    "DropPaint",
    "DropTarget",
    "FrameMark",
    "GapMark",
    "GhostMark",
    "Mark",
    "MoveCargo",
    "NewCargo",
    "NoMark",
    "OpenRow",
    "OutlineGeom",
    "PageControl",
    "Place",
    "Point",
    "Recipe",
    "Refuse",
    "ShowPage",
    "Sight",
    "Spring",
    "Stay",
    "acceptable",
    "loud",
    "resolve",
]

BESIDE_PX = 8
GHOST_BAND = 24
_H_BOX = "QHBoxLayout"
_V_BOX = "QVBoxLayout"
_SPLITTER = "QSplitter"
_PAGE_HOSTS = frozenset({"QTabWidget", "QStackedWidget", "QToolBox"})
_BARE = frozenset(
    {
        "QWidget",
        "QFrame",
        "QGroupBox",
        "QDialog",
        "QScrollArea",
        "QMainWindow",
        "QDockWidget",
        "QWizardPage",
    }
)


@dataclass(frozen=True)
class Point:
    x: int
    y: int


@dataclass(frozen=True)
class PageControl:
    """A stacked-widget arrow the overlay already measured. Not a document node."""

    rect: Rect
    container: NodeId
    index: int


@dataclass(frozen=True)
class CanvasGeom:
    entries: Tuple[GeoEntry, ...]
    #: Empty-layout hit floor, passed in by the host from the overlay constants.
    floor: Tuple[int, int]
    controls: Tuple[PageControl, ...]


@dataclass(frozen=True)
class OutlineGeom:
    entries: Tuple[GeoEntry, ...]
    collapsed: FrozenSet[NodeId]


class Away:
    pass


Sight = Union[CanvasGeom, OutlineGeom, Away]


@dataclass(frozen=True)
class NewCargo:
    """A palette tile. ``class_name`` is ``SPACER_CLASS`` or a widget class. ``size`` is the host's size hint."""

    class_name: str
    size: Tuple[int, int]


@dataclass(frozen=True)
class MoveCargo:
    """Nodes that will move, document order, siblings only. Grid and form holds one id."""

    ids: Tuple[NodeId, ...]


Cargo = Union[NewCargo, MoveCargo]


@dataclass(frozen=True)
class Place:
    placement: Placement
    auto_layout: bool


@dataclass(frozen=True)
class Beside:
    """UX-BOX-003. Wrap ``anchor`` in a new box, then put the cargo at ``index`` (0 before, 1 after)."""

    anchor: NodeId
    layout_class: str
    index: int


@dataclass(frozen=True)
class Buddy:
    """UX-FORML-002. A new form row: QLabel ``New field:`` plus the non-label cargo, then SetBuddy."""

    layout: NodeId
    row: int


class Stay:
    """The cargo is already in this slot. No indicator, no entry."""


@dataclass(frozen=True)
class Refuse:
    """``self`` ``spacer`` ``span`` are loud. ``center`` and ``none`` draw nothing."""

    reason: Literal["self", "spacer", "span", "center", "none"]
    #: Span that did not fit. Zero unless ``reason == "span"``.
    need_columns: int = 0
    need_rows: int = 0


Recipe = Union[Place, Beside, Buddy, Stay, Refuse]


@dataclass(frozen=True)
class GapMark:
    """A 2 px line. No fill."""

    rect: Rect
    axis: Literal["horizontal", "vertical"]


@dataclass(frozen=True)
class CellMark:
    """An empty cell or a ghost cell past the grid. The only mark the painter fills."""

    rect: Rect


@dataclass(frozen=True)
class FrameMark:
    """Dashed interior of an empty layout-less container. No fill."""

    rect: Rect


@dataclass(frozen=True)
class GhostMark:
    """Snapped free geometry on a container that already has free children."""

    rect: Rect


class NoMark:
    pass


Mark = Union[GapMark, CellMark, FrameMark, GhostMark, NoMark]


@dataclass(frozen=True)
class OpenRow:
    node: NodeId


@dataclass(frozen=True)
class ShowPage:
    """Canvas-only page. Does not write ``currentIndex``."""

    container: NodeId
    index: int


Spring = Union[OpenRow, ShowPage]


@dataclass(frozen=True)
class DropTarget:
    recipe: Recipe
    sentence: str
    mark: Mark
    spring: Optional[Spring]


@dataclass(frozen=True)
class DropPaint:
    where: Literal["canvas", "outline"]
    mark: Mark
    sentence: str
    trouble: bool
    dim: Tuple[NodeId, ...]
    ghost_size: Optional[Tuple[int, int]]
    ghost_at: Point


def acceptable(target: DropTarget) -> bool:
    return isinstance(target.recipe, (Place, Beside, Buddy))


def loud(target: DropTarget) -> bool:
    return isinstance(target.recipe, Refuse) and target.recipe.reason in ("self", "spacer", "span")


@dataclass(frozen=True)
class _Facts:
    band: Optional[NodeId] = None
    rect: Rect = Rect(0, 0, 0, 0)
    axis: Literal["horizontal", "vertical"] = "horizontal"
    before: Optional[NodeId] = None
    after: Optional[NodeId] = None
    anchor: Optional[NodeId] = None
    row: int = 0
    column: int = 0
    ghost: str = ""
    edge: str = ""
    place: str = ""
    x: int = 0
    y: int = 0
    page: str = ""


@dataclass(frozen=True)
class _Laid:
    node: NodeId
    rect: Rect
    row: int
    column: int
    rowspan: int
    colspan: int
    z: int


def resolve(
    document: UiDocument,
    sight: Sight,
    point: Point,
    cargo: Cargo,
    snap: int,
) -> DropTarget:
    """One target for this point.

    ``snap`` moves only a free-geometry ghost. Laid-out slots ignore it.
    """
    if isinstance(sight, Away):
        return _target(document, Refuse("none"), _Facts(), None)
    sprung = _page_spring(document, sight, point)
    if sprung is not None:
        return sprung
    hit = _deepest(document, sight, point)
    if hit is None:
        return _target(document, Refuse("none"), _Facts(), None)
    built = _from_hit(document, sight, point, cargo, snap, hit)
    if built is None:
        return _target(document, Refuse("none"), _Facts(), None)
    recipe, facts = built
    spring: Optional[Spring] = None
    if isinstance(sight, OutlineGeom) and hit.node in sight.collapsed:
        spring = OpenRow(hit.node)
    if _hits_self(document, cargo, facts.band, recipe):
        recipe = Refuse("self")
    elif _same_slot(document, cargo, recipe):
        recipe = Stay()
    return _target(document, recipe, facts, spring)


def _speak(document: UiDocument, recipe: Recipe, facts: _Facts) -> str:
    if isinstance(recipe, Stay):
        return ""
    if isinstance(recipe, Refuse):
        return _refuse_sentence(recipe, facts)
    if isinstance(recipe, Beside):
        row = "horizontal" if recipe.layout_class == _H_BOX else "vertical"
        return "Beside %s · makes a %s row" % (_name(document, recipe.anchor), row)
    if isinstance(recipe, Buddy):
        return _row_sentence(document, facts)
    if not isinstance(recipe, Place):
        return ""
    placement = recipe.placement
    if isinstance(placement, InBoxLayout):
        return _box_sentence(document, facts)
    if isinstance(placement, InGridCell):
        return _grid_sentence(document, placement, facts)
    if isinstance(placement, InFormRow):
        if placement.insert_row:
            return _row_sentence(document, facts)
        if placement.role == "label":
            return "Label of row %d" % (placement.row + 1)
        return "Field of row %d" % (placement.row + 1)
    if isinstance(placement, InContainer):
        return _container_sentence(document, recipe, facts)
    return ""


def _mark(recipe: Recipe, facts: _Facts) -> Mark:
    """CellMark only for an empty or ghost grid cell. GapMark, FrameMark, and GhostMark do not fill."""
    if isinstance(recipe, Stay):
        return NoMark()
    if isinstance(recipe, Refuse) and recipe.reason in ("center", "none"):
        return NoMark()
    if facts.place == "cell":
        return CellMark(facts.rect)
    if facts.place == "page" and isinstance(recipe, Place):
        if isinstance(recipe.placement, InBoxLayout):
            return GapMark(facts.rect, facts.axis)
        return FrameMark(facts.rect)
    if facts.place == "frame":
        return FrameMark(facts.rect)
    if facts.place == "ghost":
        return GhostMark(facts.rect)
    if facts.place in ("gap", "beside", "pane", "form-gap"):
        return GapMark(facts.rect, facts.axis)
    return NoMark()


def _target(
    document: UiDocument,
    recipe: Recipe,
    facts: _Facts,
    spring: Optional[Spring],
) -> DropTarget:
    """The only constructor ``resolve`` uses."""
    return DropTarget(recipe, _speak(document, recipe, facts), _mark(recipe, facts), spring)


def _refuse_sentence(recipe: Refuse, facts: _Facts) -> str:
    if recipe.reason == "self":
        return "A widget can't go inside itself."
    if recipe.reason == "spacer":
        return "A spacer can't go in a form."
    if recipe.reason == "span":
        if recipe.need_rows > 1 and recipe.need_columns <= 1:
            return "Needs %d free rows here." % recipe.need_rows
        count = recipe.need_columns or 1
        noun = "column" if count == 1 else "columns"
        return "Needs %d free %s here." % (count, noun)
    if facts.page:
        return facts.page
    return ""


def _box_sentence(document: UiDocument, facts: _Facts) -> str:
    if facts.place == "page" and facts.page:
        return "Into the %s tab" % facts.page
    before = _name(document, facts.before)
    after = _name(document, facts.after)
    if before and after:
        return "Insert between %s and %s" % (before, after)
    if after:
        return "Insert before %s" % after
    if before:
        return "Insert after %s" % before
    if facts.page:
        return "Into the %s tab" % facts.page
    return ""


def _grid_sentence(document: UiDocument, placement: InGridCell, facts: _Facts) -> str:
    if placement.mode == "cell":
        if facts.ghost == "row":
            return "New row %d" % (placement.row + 1)
        if facts.ghost == "column":
            return "New column %d" % (placement.column + 1)
        return "Row %d, column %d" % (placement.row + 1, placement.column + 1)
    kind = "row" if placement.mode == "insert_row" else "column"
    edge = facts.edge or "before"
    return "New %s %s %s" % (kind, edge, _name(document, facts.anchor))


def _row_sentence(document: UiDocument, facts: _Facts) -> str:
    name = _name(document, facts.anchor)
    if not name:
        return "New row %d" % (facts.row + 1)
    edge = facts.edge or "after"
    return "New row %s %s" % (edge, name)


def _container_sentence(document: UiDocument, recipe: Place, facts: _Facts) -> str:
    placement = recipe.placement
    if not isinstance(placement, InContainer):
        return ""
    if facts.place == "ghost":
        return "x %d, y %d" % (facts.x, facts.y)
    if facts.place == "pane":
        name = _name(document, facts.anchor)
        if facts.edge == "before":
            return "New pane before %s" % name
        return "New pane after %s" % name
    if facts.place == "page" and facts.page:
        return "Into the %s tab" % facts.page
    if recipe.auto_layout:
        return "Into %s · makes a vertical layout" % _name(document, placement.widget)
    return ""


def _page_spring(document: UiDocument, sight: Sight, point: Point) -> Optional[DropTarget]:
    if not isinstance(sight, CanvasGeom):
        return None
    for control in sight.controls:
        if control.rect.contains(point.x, point.y):
            return _show_page(document, control.container, control.index)
    for entry in sight.entries:
        if entry.kind != "page_tab" or not entry.visible or entry.container is None:
            continue
        if entry.rect.contains(point.x, point.y):
            index = _page_index(document, entry.container, entry.node)
            return _show_page(document, entry.container, index)
    return None


def _show_page(document: UiDocument, container: NodeId, index: int) -> DropTarget:
    page = _page_at(document, container, index)
    name = _name(document, page) if page is not None else ""
    return _target(document, Refuse("none"), _Facts(page=name, place="page"), ShowPage(container, index))


def _from_hit(
    document: UiDocument,
    sight: Sight,
    point: Point,
    cargo: Cargo,
    snap: int,
    hit: GeoEntry,
) -> Optional[Tuple[Recipe, _Facts]]:
    node = document.get(hit.node)
    if isinstance(node, LayoutNode):
        return _on_layout(document, sight, point, cargo, node)
    if isinstance(node, SpacerNode):
        layout = _host_layout(document, node.id)
        if layout is None:
            return None
        return _on_layout(document, sight, point, cargo, layout)
    if not isinstance(node, WidgetNode):
        return None
    parent_layout = _host_layout(document, node.id)
    if parent_layout is not None and not _opens_inside(document, node):
        return _on_layout(document, sight, point, cargo, parent_layout)
    if node.layout is not None:
        return _on_layout(document, sight, point, cargo, node.layout)
    splitter = _splitter_of(document, node)
    if splitter is not None:
        return _on_splitter(document, sight, point, splitter)
    if _opens_inside(document, node):
        return _on_bare(document, sight, point, cargo, snap, node)
    if parent_layout is not None:
        return _on_layout(document, sight, point, cargo, parent_layout)
    return None


def _on_layout(
    document: UiDocument,
    sight: Sight,
    point: Point,
    cargo: Cargo,
    layout: LayoutNode,
) -> Tuple[Recipe, _Facts]:
    if layout.class_name == "QGridLayout":
        if isinstance(sight, OutlineGeom):
            return _outline_grid(document, sight, point, cargo, layout)
        return _grid(document, sight, point, cargo, layout)
    if layout.class_name == "QFormLayout":
        if isinstance(sight, OutlineGeom):
            return _outline_form(document, sight, point, cargo, layout)
        return _form(document, sight, point, cargo, layout)
    return _box(document, sight, point, layout, layout.class_name == _H_BOX)


def _box(
    document: UiDocument,
    sight: Sight,
    point: Point,
    layout: LayoutNode,
    horizontal: bool,
) -> Tuple[Recipe, _Facts]:
    children = _box_children(sight, layout)
    beside = _beside(document, sight, point, children, horizontal)
    layout_rect = _rect_of(sight.entries, layout.id) or Rect(0, 0, 0, 0)
    if beside is not None:
        child, index = beside
        layout_class = _V_BOX if horizontal else _H_BOX
        facts = _Facts(
            band=child.node,
            rect=_beside_line(child.rect, index, horizontal),
            axis="horizontal" if horizontal else "vertical",
            anchor=child.node,
            place="beside",
        )
        return Beside(child.node, layout_class, index), facts
    index = _center_index(children, point, horizontal)
    before = children[index - 1].node if index > 0 else None
    after = children[index].node if index < len(children) else None
    page = _page_title(document, layout)
    place = "page" if page and not children else "gap"
    facts = _Facts(
        band=layout.id,
        rect=_box_line(layout_rect, children, index, horizontal),
        axis="vertical" if horizontal else "horizontal",
        before=before,
        after=after,
        place=place,
        page=page,
    )
    return Place(InBoxLayout(layout.id, index), False), facts


def _grid(
    document: UiDocument,
    sight: Sight,
    point: Point,
    cargo: Cargo,
    layout: LayoutNode,
) -> Tuple[Recipe, _Facts]:
    items = _laid(sight.entries, layout)
    rows, cols = _shape(items)
    hit = _item_containing(items, point)
    if hit is not None:
        return _occupied_cell(document, cargo, layout, hit, point)
    found = _empty_cell(items, point, rows, cols)
    if found is not None:
        row, column, rect = found
        return _open_cell(document, cargo, layout, row, column, rect, items, rows, cols, "")
    ghost = _ghost_cell(sight, layout, items, point, rows, cols)
    if ghost is not None:
        row, column, rect, kind = ghost
        return _open_cell(document, cargo, layout, row, column, rect, items, rows, cols, kind)
    return Refuse("none"), _Facts(band=layout.id)


def _occupied_cell(
    document: UiDocument,
    cargo: Cargo,
    layout: LayoutNode,
    hit: _Laid,
    point: Point,
) -> Tuple[Recipe, _Facts]:
    edge = _quarter(hit.rect, point)
    if edge is None:
        return Refuse("center"), _Facts(band=layout.id, rect=hit.rect, anchor=hit.node, place="cell")
    if edge in ("top", "bottom"):
        row = hit.row if edge == "top" else hit.row + hit.rowspan
        column = hit.column
        mode: Literal["insert_row", "insert_column"] = "insert_row"
        word = "before" if edge == "top" else "after"
    else:
        row = hit.row
        column = hit.column if edge == "left" else hit.column + hit.colspan
        mode = "insert_column"
        word = "before" if edge == "left" else "after"
    line, axis = _edge_line(hit.rect, edge)
    span_r, span_c = _span(document, cargo)
    facts = _Facts(
        band=layout.id,
        rect=line,
        axis=axis,
        anchor=hit.node,
        row=row,
        column=column,
        edge=word,
        place="gap",
    )
    return Place(InGridCell(layout.id, row, column, span_r, span_c, mode), False), facts


def _open_cell(
    document: UiDocument,
    cargo: Cargo,
    layout: LayoutNode,
    row: int,
    column: int,
    rect: Rect,
    items: Sequence[_Laid],
    rows: int,
    cols: int,
    ghost: str,
) -> Tuple[Recipe, _Facts]:
    span_r, span_c = _span(document, cargo)
    facts = _Facts(band=layout.id, rect=rect, row=row, column=column, ghost=ghost, place="cell")
    if not _hole_fits(items, row, column, span_r, span_c, rows, cols, _moving(cargo), ghost):
        return Refuse("span", span_c, span_r), facts
    return Place(InGridCell(layout.id, row, column, span_r, span_c, "cell"), False), facts


def _form(
    document: UiDocument,
    sight: Sight,
    point: Point,
    cargo: Cargo,
    layout: LayoutNode,
) -> Tuple[Recipe, _Facts]:
    items = _laid(sight.entries, layout)
    layout_rect = _rect_of(sight.entries, layout.id) or Rect(0, 0, 0, 0)
    if _is_spacer(document, cargo):
        return Refuse("spacer"), _Facts(band=layout.id, rect=layout_rect, place="frame")
    hit = _item_containing(items, point)
    if hit is not None:
        return _form_gap(document, cargo, layout, hit, point)
    empty = _empty_form_cell(items, layout_rect, point)
    if empty is not None:
        row, role, rect = empty
        return _form_cell(layout, row, role, rect)
    return _form_past(document, cargo, layout, items, point, layout_rect)


def _form_cell(
    layout: LayoutNode,
    row: int,
    role: Literal["label", "field"],
    rect: Rect,
) -> Tuple[Recipe, _Facts]:
    facts = _Facts(band=layout.id, rect=rect, row=row, place="frame")
    return Place(InFormRow(layout.id, row, role, False), False), facts


def _form_gap(
    document: UiDocument,
    cargo: Cargo,
    layout: LayoutNode,
    hit: _Laid,
    point: Point,
) -> Tuple[Recipe, _Facts]:
    before = point.y < hit.rect.y + (hit.rect.height // 2)
    row = hit.row if before else hit.row + max(hit.rowspan, 1)
    edge = "before" if before else "after"
    line, axis = _edge_line(hit.rect, "top" if before else "bottom")
    facts = _Facts(
        band=layout.id,
        rect=line,
        axis=axis,
        anchor=hit.node,
        row=row,
        edge=edge,
        place="form-gap",
    )
    return _new_form_row(document, cargo, layout, row, facts)


def _form_past(
    document: UiDocument,
    cargo: Cargo,
    layout: LayoutNode,
    items: Sequence[_Laid],
    point: Point,
    layout_rect: Rect,
) -> Tuple[Recipe, _Facts]:
    if not layout_rect.contains(point.x, point.y):
        return Refuse("none"), _Facts(band=layout.id)
    rows = 0
    anchor: Optional[NodeId] = None
    for item in items:
        if item.row + item.rowspan >= rows:
            rows = item.row + item.rowspan
            anchor = item.node
    line = Rect(
        layout_rect.x + 4,
        max(layout_rect.y, layout_rect.y + layout_rect.height - 3),
        max(1, layout_rect.width - 8),
        2,
    )
    facts = _Facts(
        band=layout.id,
        rect=line,
        axis="horizontal",
        anchor=anchor,
        row=rows,
        edge="after",
        place="form-gap",
    )
    return _new_form_row(document, cargo, layout, rows, facts)


def _new_form_row(
    document: UiDocument,
    cargo: Cargo,
    layout: LayoutNode,
    row: int,
    facts: _Facts,
) -> Tuple[Recipe, _Facts]:
    if _is_spacer(document, cargo):
        return Refuse("spacer"), facts
    if _is_label(document, cargo):
        return Place(InFormRow(layout.id, row, "label", True), False), facts
    return Buddy(layout.id, row), facts


def _outline_grid(
    document: UiDocument,
    sight: OutlineGeom,
    point: Point,
    cargo: Cargo,
    layout: LayoutNode,
) -> Tuple[Recipe, _Facts]:
    items = _laid(sight.entries, layout)
    reading = sorted(items, key=lambda item: (item.row, item.column, item.z))
    hit = _row_under(sight, layout.id, point)
    if hit is None:
        return Refuse("none"), _Facts(band=layout.id)
    found = next((item for item in reading if item.node == hit.node), None)
    if found is None:
        return Refuse("none"), _Facts(band=layout.id)
    index = reading.index(found)
    upper = point.y < hit.rect.y + hit.rect.height // 2
    if upper:
        prev = reading[index - 1] if index else None
        nxt: Optional[_Laid] = found
    else:
        prev = found
        nxt = reading[index + 1] if index + 1 < len(reading) else None
    return _reading_gap(document, cargo, layout, prev, nxt, hit.rect)


def _outline_form(
    document: UiDocument,
    sight: OutlineGeom,
    point: Point,
    cargo: Cargo,
    layout: LayoutNode,
) -> Tuple[Recipe, _Facts]:
    if _is_spacer(document, cargo):
        return Refuse("spacer"), _Facts(band=layout.id, place="frame")
    hit = _row_under(sight, layout.id, point)
    if hit is None:
        return Refuse("none"), _Facts(band=layout.id)
    found = next((item for item in _laid(sight.entries, layout) if item.node == hit.node), None)
    if found is None:
        return Refuse("none"), _Facts(band=layout.id)
    return _form_gap(document, cargo, layout, found, point)


def _reading_gap(
    document: UiDocument,
    cargo: Cargo,
    layout: LayoutNode,
    prev: Optional[_Laid],
    nxt: Optional[_Laid],
    rect: Rect,
) -> Tuple[Recipe, _Facts]:
    if nxt is not None and prev is not None and prev.row == nxt.row:
        mode: Literal["insert_row", "insert_column"] = "insert_column"
        row = nxt.row
        column = nxt.column
        anchor = nxt.node
        edge = "before"
        side = "left"
    elif nxt is not None:
        mode = "insert_row"
        row = nxt.row
        column = nxt.column
        anchor = nxt.node
        edge = "before"
        side = "top"
    elif prev is not None:
        mode = "insert_row"
        row = prev.row + prev.rowspan
        column = prev.column
        anchor = prev.node
        edge = "after"
        side = "bottom"
    else:
        return Refuse("none"), _Facts(band=layout.id)
    line, axis = _edge_line(rect, side)
    span_r, span_c = _span(document, cargo)
    facts = _Facts(
        band=layout.id,
        rect=line,
        axis=axis,
        anchor=anchor,
        row=row,
        column=column,
        edge=edge,
        place="gap",
    )
    return Place(InGridCell(layout.id, row, column, span_r, span_c, mode), False), facts


def _on_splitter(
    document: UiDocument,
    sight: Sight,
    point: Point,
    splitter: WidgetNode,
) -> Tuple[Recipe, _Facts]:
    panes = _pane_entries(document, sight, splitter)
    horizontal = _splitter_horizontal(splitter)
    index = _center_index(panes, point, horizontal)
    before = panes[index - 1].node if index else None
    after = panes[index].node if index < len(panes) else None
    anchor = before if before is not None else after
    rect = _rect_of(sight.entries, splitter.id) or Rect(0, 0, 0, 0)
    facts = _Facts(
        band=splitter.id,
        rect=_box_line(rect, panes, index, horizontal),
        axis="vertical" if horizontal else "horizontal",
        before=before,
        after=after,
        anchor=anchor,
        edge="after" if before is not None else "before",
        place="pane",
    )
    return Place(InContainer(splitter.id, index), False), facts


def _on_bare(
    document: UiDocument,
    sight: Sight,
    point: Point,
    cargo: Cargo,
    snap: int,
    widget: WidgetNode,
) -> Tuple[Recipe, _Facts]:
    rect = _rect_of(sight.entries, widget.id) or Rect(0, 0, 0, 0)
    if widget.child_widgets:
        width, height = _cargo_size(document, cargo, sight)
        x = _snap(point.x, snap)
        y = _snap(point.y, snap)
        facts = _Facts(band=widget.id, rect=Rect(x, y, width, height), place="ghost", x=x, y=y)
        return Place(InContainer(widget.id, len(widget.child_widgets), RectValue(x, y, width, height)), False), facts
    page = _as_page(document, widget)
    facts = _Facts(
        band=widget.id,
        rect=rect,
        place="page" if page else "frame",
        page=_name(document, widget.id) if page else "",
    )
    return Place(InContainer(widget.id, 0), True), facts


def _beside(
    document: UiDocument,
    sight: Sight,
    point: Point,
    children: Sequence[GeoEntry],
    horizontal: bool,
) -> Optional[Tuple[GeoEntry, int]]:
    best: Optional[Tuple[GeoEntry, int]] = None
    best_dist: Optional[int] = None
    for child in children:
        node = document.get(child.node)
        if isinstance(node, WidgetNode) and _layout_contains(sight, node, point):
            continue
        found = _beside_edge(child.rect, point, horizontal)
        if found is None:
            continue
        index, dist = found
        if best_dist is None or dist < best_dist:
            best = (child, index)
            best_dist = dist
    return best


def _beside_edge(rect: Rect, point: Point, horizontal: bool) -> Optional[Tuple[int, int]]:
    if horizontal:
        if point.x < rect.x or point.x >= rect.x + rect.width:
            return None
        top = abs(point.y - rect.y)
        bottom = abs(point.y - (rect.y + rect.height))
        if top <= BESIDE_PX and top <= bottom:
            return 0, top
        if bottom <= BESIDE_PX:
            return 1, bottom
        return None
    if point.y < rect.y or point.y >= rect.y + rect.height:
        return None
    left = abs(point.x - rect.x)
    right = abs(point.x - (rect.x + rect.width))
    if left <= BESIDE_PX and left <= right:
        return 0, left
    if right <= BESIDE_PX:
        return 1, right
    return None


def _center_index(children: Sequence[GeoEntry], point: Point, horizontal: bool) -> int:
    # Centres, not the gap: a point past a child's midpoint inserts after it.
    count = 0
    coord = point.x if horizontal else point.y
    for child in children:
        center = child.rect.x + child.rect.width // 2 if horizontal else child.rect.y + child.rect.height // 2
        if center < coord:
            count += 1
    return count


def _deepest(document: UiDocument, sight: Sight, point: Point) -> Optional[GeoEntry]:
    if isinstance(sight, OutlineGeom):
        containing = [
            entry
            for entry in sight.entries
            if entry.visible and entry.kind != "page_tab" and entry.rect.contains(point.x, point.y)
        ]
        if not containing:
            return None
        containers = {entry.container for entry in containing}
        leaves = [entry for entry in containing if entry.node not in containers]
        pool = leaves or containing
        pool.sort(key=lambda entry: entry.z)
        return pool[-1]
    if not isinstance(sight, CanvasGeom):
        return None
    grouped: Dict[Optional[NodeId], List[GeoEntry]] = {}
    for entry in sight.entries:
        if not entry.visible or entry.kind == "page_tab":
            continue
        grouped.setdefault(entry.container, []).append(entry)
    for group in grouped.values():
        group.sort(key=lambda entry: entry.z)

    def walk(level: Sequence[GeoEntry]) -> Optional[GeoEntry]:
        chosen: Optional[GeoEntry] = None
        for entry in reversed(level):
            if _hit_rect(document, sight, entry).contains(point.x, point.y):
                chosen = entry
                break
        if chosen is None:
            return None
        deeper = walk(grouped.get(chosen.node, ()))
        return deeper if deeper is not None else chosen

    return walk(grouped.get(None, ()))


def _hit_rect(document: UiDocument, sight: CanvasGeom, entry: GeoEntry) -> Rect:
    if entry.kind == "layout" and _layout_empty(document, entry.node):
        width = max(entry.rect.width, sight.floor[0])
        height = max(entry.rect.height, sight.floor[1])
        return Rect(
            entry.rect.x - (width - entry.rect.width) // 2,
            entry.rect.y - (height - entry.rect.height) // 2,
            width,
            height,
        )
    return entry.rect


def _layout_empty(document: UiDocument, node_id: NodeId) -> bool:
    node = document.get(node_id)
    if not isinstance(node, LayoutNode):
        return False
    return not any(item.content is not None for item in node.items)


def _box_children(sight: Sight, layout: LayoutNode) -> List[GeoEntry]:
    by_id: Dict[NodeId, GeoEntry] = {}
    for entry in sight.entries:
        if entry.container == layout.id and entry.kind != "page_tab":
            by_id[entry.node] = entry
    ordered: List[GeoEntry] = []
    for item in layout.items:
        content = item.content
        if content is not None and content.id in by_id:
            ordered.append(by_id[content.id])
    if isinstance(sight, OutlineGeom):
        ordered.sort(key=lambda entry: entry.z)
    return ordered


def _laid(entries: Sequence[GeoEntry], layout: LayoutNode) -> List[_Laid]:
    by_id = {entry.node: entry for entry in entries if entry.kind != "page_tab"}
    found: List[_Laid] = []
    for item in layout.items:
        content = item.content
        if content is None or content.id not in by_id:
            continue
        entry = by_id[content.id]
        found.append(
            _Laid(
                content.id,
                entry.rect,
                0 if item.row is None else item.row,
                0 if item.column is None else item.column,
                item.rowspan or 1,
                item.colspan or 1,
                entry.z,
            )
        )
    return found


def _shape(items: Sequence[_Laid]) -> Tuple[int, int]:
    rows = 0
    cols = 0
    for item in items:
        rows = max(rows, item.row + item.rowspan)
        cols = max(cols, item.column + item.colspan)
    return rows, cols


def _item_containing(items: Sequence[_Laid], point: Point) -> Optional[_Laid]:
    found = [item for item in items if item.rect.contains(point.x, point.y)]
    if not found:
        return None
    found.sort(key=lambda item: item.z)
    return found[-1]


def _empty_cell(
    items: Sequence[_Laid],
    point: Point,
    rows: int,
    cols: int,
) -> Optional[Tuple[int, int, Rect]]:
    if rows <= 0 or cols <= 0:
        return None
    xs = _edges(items, cols, horizontal=True)
    ys = _edges(items, rows, horizontal=False)
    column = _band(xs, point.x)
    row = _band(ys, point.y)
    if column is None or row is None or _occupant(items, row, column) is not None:
        return None
    return row, column, Rect(xs[column], ys[row], max(1, xs[column + 1] - xs[column]), max(1, ys[row + 1] - ys[row]))


def _edges(items: Sequence[_Laid], count: int, horizontal: bool) -> List[int]:
    start: List[Optional[int]] = [None] * count
    end: List[Optional[int]] = [None] * count
    for item in items:
        span = item.colspan if horizontal else item.rowspan
        if span != 1:
            continue
        index = item.column if horizontal else item.row
        if index < 0 or index >= count:
            continue
        origin = item.rect.x if horizontal else item.rect.y
        size = item.rect.width if horizontal else item.rect.height
        if start[index] is None or origin < (start[index] or 0):
            start[index] = origin
        stop = origin + size
        if end[index] is None or stop > (end[index] or 0):
            end[index] = stop
    edges = [0] * (count + 1)
    for index in range(count):
        if start[index] is not None:
            edges[index] = start[index] or 0
        if end[index] is not None:
            edges[index + 1] = end[index] or 0
    for index in range(1, count + 1):
        if edges[index] < edges[index - 1]:
            edges[index] = edges[index - 1]
    return edges


def _band(edges: Sequence[int], coord: int) -> Optional[int]:
    for index in range(len(edges) - 1):
        if edges[index] <= coord < edges[index + 1]:
            return index
    return None


def _occupant(items: Sequence[_Laid], row: int, column: int) -> Optional[NodeId]:
    for item in items:
        if item.row <= row < item.row + item.rowspan and item.column <= column < item.column + item.colspan:
            return item.node
    return None


def _ghost_cell(
    sight: Sight,
    layout: LayoutNode,
    items: Sequence[_Laid],
    point: Point,
    rows: int,
    cols: int,
) -> Optional[Tuple[int, int, Rect, str]]:
    if rows <= 0 or cols <= 0:
        return None
    xs = _edges(items, cols, horizontal=True)
    ys = _edges(items, rows, horizontal=False)
    owner = _owner_rect(sight, layout)
    if owner is None or not owner.contains(point.x, point.y):
        return None
    past_row = ys[-1] <= point.y < ys[-1] + GHOST_BAND and xs[0] <= point.x < xs[-1] + GHOST_BAND
    past_col = xs[-1] <= point.x < xs[-1] + GHOST_BAND and ys[0] <= point.y < ys[-1] + GHOST_BAND
    if past_row and past_col:
        if point.y - ys[-1] <= point.x - xs[-1]:
            past_col = False
        else:
            past_row = False
    if past_row:
        column = _band(xs, min(point.x, xs[-1] - 1))
        if column is None:
            column = max(0, cols - 1)
        width = max(1, xs[column + 1] - xs[column])
        return rows, column, Rect(xs[column], ys[-1], width, GHOST_BAND), "row"
    if past_col:
        row = _band(ys, min(point.y, ys[-1] - 1))
        if row is None:
            row = max(0, rows - 1)
        height = max(1, ys[row + 1] - ys[row])
        return row, cols, Rect(xs[-1], ys[row], GHOST_BAND, height), "column"
    return None


def _empty_form_cell(
    items: Sequence[_Laid],
    layout_rect: Rect,
    point: Point,
) -> Optional[Tuple[int, Literal["label", "field"], Rect]]:
    if not items:
        return None
    rows = max(item.row + item.rowspan for item in items)
    ys = _edges(items, rows, horizontal=False)
    label_x, field_x, field_right = _form_columns(items, layout_rect)
    row = _band(ys, point.y)
    if row is None:
        return None
    rect_y = ys[row]
    height = max(1, ys[row + 1] - ys[row])
    occupied = {(item.row, "label" if item.column == 0 and item.colspan <= 1 else "field") for item in items if item.rowspan <= 1}
    spanning = {item.row for item in items if item.colspan > 1}
    if row in spanning:
        return None
    if label_x <= point.x < field_x and (row, "label") not in occupied:
        return row, "label", Rect(label_x, rect_y, max(1, field_x - label_x), height)
    if field_x <= point.x < field_right and (row, "field") not in occupied:
        return row, "field", Rect(field_x, rect_y, max(1, field_right - field_x), height)
    return None


def _form_columns(items: Sequence[_Laid], layout_rect: Rect) -> Tuple[int, int, int]:
    label_x = layout_rect.x
    field_x = layout_rect.x + layout_rect.width // 2
    field_right = layout_rect.x + layout_rect.width
    for item in items:
        if item.colspan > 1:
            continue
        if item.column == 0:
            label_x = item.rect.x
            field_x = item.rect.x + item.rect.width
        elif item.column == 1:
            field_x = item.rect.x
            field_right = item.rect.x + item.rect.width
    return label_x, field_x, field_right


def _quarter(rect: Rect, point: Point) -> Optional[str]:
    if rect.width <= 0 or rect.height <= 0 or not rect.contains(point.x, point.y):
        return None
    fx = (point.x - rect.x) / float(rect.width)
    fy = (point.y - rect.y) / float(rect.height)
    across: Optional[Tuple[str, float]] = None
    down: Optional[Tuple[str, float]] = None
    if fx < 0.25:
        across = ("left", fx)
    elif fx >= 0.75:
        across = ("right", 1.0 - fx)
    if fy < 0.25:
        down = ("top", fy)
    elif fy >= 0.75:
        down = ("bottom", 1.0 - fy)
    if across and down:
        return across[0] if across[1] <= down[1] else down[0]
    if across:
        return across[0]
    if down:
        return down[0]
    return None


def _hole_fits(
    items: Sequence[_Laid],
    row: int,
    column: int,
    rowspan: int,
    colspan: int,
    rows: int,
    cols: int,
    moving: FrozenSet[NodeId],
    ghost: str,
) -> bool:
    limit_c = cols + (1 if ghost == "column" else 0)
    limit_r = rows + (1 if ghost == "row" else 0)
    if column < 0 or row < 0 or column + colspan > max(limit_c, cols) or row + rowspan > max(limit_r, rows):
        if ghost == "row" and row == rows and rowspan == 1 and column + colspan <= cols:
            return True
        if ghost == "column" and column == cols and colspan == 1 and row + rowspan <= rows:
            return True
        return False
    for r in range(row, row + rowspan):
        for c in range(column, column + colspan):
            if r >= rows or c >= cols:
                return False
            owner = _occupant(items, r, c)
            if owner is not None and owner not in moving:
                return False
    return True


def _hits_self(document: UiDocument, cargo: Cargo, band: Optional[NodeId], recipe: Recipe) -> bool:
    if not isinstance(cargo, MoveCargo):
        return False
    if isinstance(recipe, Beside) and recipe.anchor in cargo.ids:
        return True
    if band is None:
        return False
    for node_id in cargo.ids:
        if node_id == band or document.is_ancestor(node_id, band):
            return True
    return False


def _same_slot(document: UiDocument, cargo: Cargo, recipe: Recipe) -> bool:
    if not isinstance(cargo, MoveCargo) or not isinstance(recipe, Place):
        return False
    placement = recipe.placement
    if isinstance(placement, InBoxLayout):
        return _box_unchanged(document, cargo, placement)
    if isinstance(placement, InGridCell) and placement.mode == "cell" and len(cargo.ids) == 1:
        return _home_cell(document, cargo.ids[0]) == (placement.layout, placement.row, placement.column)
    if isinstance(placement, InFormRow) and not placement.insert_row and len(cargo.ids) == 1:
        return _home_form(document, cargo.ids[0]) == (placement.layout, placement.row, placement.role)
    return False


def _box_unchanged(document: UiDocument, cargo: MoveCargo, placement: InBoxLayout) -> bool:
    layout = document.get(placement.layout)
    if not isinstance(layout, LayoutNode):
        return False
    contents: List[NodeId] = []
    for item in layout.items:
        content = item.content
        if content is not None:
            contents.append(content.id)
    if any(node_id not in contents for node_id in cargo.ids):
        return False
    moving = set(cargo.ids)
    removed = sum(1 for node_id in contents[: placement.index] if node_id in moving)
    adjusted = placement.index - removed
    without = [node_id for node_id in contents if node_id not in moving]
    if adjusted < 0 or adjusted > len(without):
        return False
    return without[:adjusted] + [node_id for node_id in cargo.ids if node_id in moving] + without[adjusted:] == contents


def _home_cell(document: UiDocument, node_id: NodeId) -> Optional[Tuple[NodeId, int, int]]:
    parent = document.parent(node_id)
    if not isinstance(parent, LayoutItemNode) or parent.parent_id is None:
        return None
    layout = document.get(parent.parent_id)
    if not isinstance(layout, LayoutNode) or layout.class_name != "QGridLayout":
        return None
    return layout.id, parent.row or 0, parent.column or 0


def _home_form(document: UiDocument, node_id: NodeId) -> Optional[Tuple[NodeId, int, str]]:
    parent = document.parent(node_id)
    if not isinstance(parent, LayoutItemNode) or parent.parent_id is None:
        return None
    layout = document.get(parent.parent_id)
    if not isinstance(layout, LayoutNode) or layout.class_name != "QFormLayout":
        return None
    role = "spanning" if (parent.colspan or 1) > 1 else ("label" if (parent.column or 0) == 0 else "field")
    return layout.id, parent.row or 0, role


def _opens_inside(document: UiDocument, node: WidgetNode) -> bool:
    if node.layout is not None or node.child_widgets:
        return True
    if is_page_container(document, node.id):
        return True
    return node.class_name in _BARE


def _host_layout(document: UiDocument, node_id: NodeId) -> Optional[LayoutNode]:
    parent = document.parent(node_id)
    if not isinstance(parent, LayoutItemNode) or parent.parent_id is None:
        return None
    layout = document.get(parent.parent_id)
    if isinstance(layout, LayoutNode):
        return layout
    return None


def _splitter_of(document: UiDocument, node: WidgetNode) -> Optional[WidgetNode]:
    if node.class_name == _SPLITTER:
        return node
    parent = document.parent(node.id)
    if isinstance(parent, WidgetNode) and parent.class_name == _SPLITTER:
        return parent
    return None


def _layout_contains(sight: Sight, node: WidgetNode, point: Point) -> bool:
    if node.layout is None:
        return False
    rect = _rect_of(sight.entries, node.layout.id)
    return rect is not None and rect.contains(point.x, point.y)


def _pane_entries(document: UiDocument, sight: Sight, splitter: WidgetNode) -> List[GeoEntry]:
    by_id = {entry.node: entry for entry in sight.entries}
    return [by_id[child.id] for child in splitter.child_widgets if child.id in by_id]


def _splitter_horizontal(splitter: WidgetNode) -> bool:
    entry = splitter.prop("orientation")
    if entry is None:
        return True
    text = getattr(entry.value, "text", "")
    return "Vertical" not in str(text)


def _page_title(document: UiDocument, layout: LayoutNode) -> str:
    owner_id = layout.owner_widget_id()
    if owner_id is None:
        return ""
    owner = document.get(owner_id)
    if not isinstance(owner, WidgetNode) or not _as_page(document, owner):
        return ""
    if any(item.content is not None for item in layout.items):
        return ""
    return _name(document, owner.id)


def _as_page(document: UiDocument, widget: WidgetNode) -> bool:
    parent = document.parent(widget.id)
    return isinstance(parent, WidgetNode) and parent.class_name in _PAGE_HOSTS


def _page_index(document: UiDocument, container: NodeId, page: NodeId) -> int:
    host = document.get(container)
    if not isinstance(host, WidgetNode):
        return 0
    for index, child in enumerate(host.child_widgets):
        if child.id == page:
            return index
    return 0


def _page_at(document: UiDocument, container: NodeId, index: int) -> Optional[NodeId]:
    host = document.get(container)
    if not isinstance(host, WidgetNode):
        return None
    pages = host.child_widgets
    if index < 0 or index >= len(pages):
        return None
    return pages[index].id


def _owner_rect(sight: Sight, layout: LayoutNode) -> Optional[Rect]:
    owner = layout.owner_widget_id()
    if owner is None:
        parent = layout.parent_id
        return _rect_of(sight.entries, layout.id) if parent is None else _rect_of(sight.entries, parent)
    rect = _rect_of(sight.entries, owner)
    if rect is not None:
        return rect
    return _rect_of(sight.entries, layout.id)


def _row_under(sight: OutlineGeom, layout_id: NodeId, point: Point) -> Optional[GeoEntry]:
    rows = [
        entry
        for entry in sight.entries
        if entry.container == layout_id and entry.rect.contains(point.x, point.y)
    ]
    if not rows:
        return None
    rows.sort(key=lambda entry: entry.z)
    return rows[-1]


def _rect_of(entries: Sequence[GeoEntry], node_id: NodeId) -> Optional[Rect]:
    for entry in entries:
        if entry.node == node_id and entry.kind != "page_tab":
            return entry.rect
    return None


def _edge_line(rect: Rect, side: str) -> Tuple[Rect, Literal["horizontal", "vertical"]]:
    if side == "top":
        return Rect(rect.x, rect.y, max(1, rect.width), 2), "horizontal"
    if side == "bottom":
        return Rect(rect.x, max(rect.y, rect.y + rect.height - 2), max(1, rect.width), 2), "horizontal"
    if side == "left":
        return Rect(rect.x, rect.y, 2, max(1, rect.height)), "vertical"
    return Rect(max(rect.x, rect.x + rect.width - 2), rect.y, 2, max(1, rect.height)), "vertical"


def _box_line(layout_rect: Rect, children: Sequence[GeoEntry], index: int, horizontal: bool) -> Rect:
    if horizontal:
        x = _boundary(layout_rect.x, layout_rect.width, children, index, True)
        return Rect(x - 1, layout_rect.y + 4, 2, max(1, layout_rect.height - 8))
    y = _boundary(layout_rect.y, layout_rect.height, children, index, False)
    return Rect(layout_rect.x + 4, y - 1, max(1, layout_rect.width - 8), 2)


def _boundary(origin: int, size: int, children: Sequence[GeoEntry], index: int, horizontal: bool) -> int:
    if index <= 0:
        return origin + 3
    if index >= len(children):
        return origin + max(3, size - 3)
    prev = children[index - 1].rect
    nxt = children[index].rect
    if horizontal:
        start = prev.x + prev.width
        end = nxt.x
    else:
        start = prev.y + prev.height
        end = nxt.y
    if end > start:
        return (start + end) // 2
    return end


def _beside_line(rect: Rect, index: int, horizontal: bool) -> Rect:
    if horizontal:
        y = rect.y if index == 0 else rect.y + rect.height - 2
        return Rect(rect.x, y, max(1, rect.width), 2)
    x = rect.x if index == 0 else rect.x + rect.width - 2
    return Rect(x, rect.y, 2, max(1, rect.height))


def _span(document: UiDocument, cargo: Cargo) -> Tuple[int, int]:
    if not isinstance(cargo, MoveCargo) or len(cargo.ids) != 1:
        return 1, 1
    parent = document.parent(cargo.ids[0])
    if not isinstance(parent, LayoutItemNode):
        return 1, 1
    return parent.rowspan or 1, parent.colspan or 1


def _moving(cargo: Cargo) -> FrozenSet[NodeId]:
    if isinstance(cargo, MoveCargo):
        return frozenset(cargo.ids)
    return frozenset()


def _is_spacer(document: UiDocument, cargo: Cargo) -> bool:
    if isinstance(cargo, NewCargo):
        return cargo.class_name == SPACER_CLASS
    return any(isinstance(document.get(node_id), SpacerNode) for node_id in cargo.ids)


def _is_label(document: UiDocument, cargo: Cargo) -> bool:
    if isinstance(cargo, NewCargo):
        return cargo.class_name == LABEL_CLASS
    if len(cargo.ids) != 1:
        return False
    node = document.get(cargo.ids[0])
    return isinstance(node, WidgetNode) and node.class_name == LABEL_CLASS


def _cargo_size(document: UiDocument, cargo: Cargo, sight: Sight) -> Tuple[int, int]:
    if isinstance(cargo, NewCargo):
        return cargo.size
    if isinstance(cargo, MoveCargo) and cargo.ids:
        node = document.get(cargo.ids[0])
        if node is not None:
            entry = node.prop("geometry")
            value = None if entry is None else entry.value
            if isinstance(value, RectValue) and value.width > 0 and value.height > 0:
                return value.width, value.height
        rect = _rect_of(sight.entries, cargo.ids[0])
        if rect is not None:
            return max(1, rect.width), max(1, rect.height)
    return 80, 24


def _snap(value: int, snap: int) -> int:
    if snap <= 0:
        return value
    return int(round(float(value) / float(snap)) * snap)


def _name(document: UiDocument, node_id: Optional[NodeId]) -> str:
    if node_id is None:
        return ""
    node = document.get(node_id)
    if isinstance(node, WidgetNode):
        for key in ("text", "title"):
            entry = node.prop(key)
            if entry is None:
                continue
            text = getattr(entry.value, "text", None)
            if isinstance(text, str) and text:
                return text
        return node.object_name or "widget"
    if isinstance(node, SpacerNode):
        return node.name or "spacer"
    if isinstance(node, LayoutNode):
        return node.object_name or "layout"
    return ""
