"""Where a node sits, and the keyboard and rubber-band rules that follow from it."""

from __future__ import annotations

import weakref
from dataclasses import dataclass
from typing import FrozenSet, List, Literal, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.hit_index import HitIndex, Rect
from app.features.form_builder.engine.query.selection import SelectionState
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import (
    CustomWidgetNode,
    LayoutItemNode,
    LayoutNode,
    SpacerNode,
    WidgetNode,
)
from app.features.form_builder.engine.ui4.values import RectValue

_MANAGED = frozenset(
    {
        "QTabWidget",
        "QStackedWidget",
        "QToolBox",
        "QSplitter",
        "QWizard",
        "QMdiArea",
        "QScrollArea",
        "QMainWindow",
        "QDockWidget",
    }
)


@dataclass(frozen=True)
class Free:
    parent: NodeId


@dataclass(frozen=True)
class LaidOut:
    layout: NodeId


@dataclass(frozen=True)
class Managed:
    container: NodeId


@dataclass(frozen=True)
class Root:
    pass


Positioning = Union[Free, LaidOut, Managed, Root]
Direction = Literal["left", "right", "up", "down"]

_WIDGETS: "weakref.WeakKeyDictionary[UiDocument, Tuple[int, Tuple[NodeId, ...]]]" = weakref.WeakKeyDictionary()
_VISIBLE: "weakref.WeakKeyDictionary[HitIndex, Tuple[int, UiDocument, int, Tuple[Tuple[NodeId, Rect], ...]]]" = (
    weakref.WeakKeyDictionary()
)


def positioning_of(document: UiDocument, node: NodeId) -> Positioning:
    found = document.get(node)
    if isinstance(found, WidgetNode) and found.id == document.root.id:
        return Root()
    if isinstance(found, SpacerNode):
        return LaidOut(_layout_of_item(document, found.parent_id) or node)
    if isinstance(found, WidgetNode):
        parent = document.parent(found.id)
        if isinstance(parent, LayoutItemNode):
            return LaidOut(_layout_of_item(document, parent.id) or found.id)
        if isinstance(parent, WidgetNode):
            if effective_class(document, parent) in _MANAGED:
                return Managed(parent.id)
            return Free(parent.id)
    if isinstance(found, LayoutNode):
        return LaidOut(found.id)
    return Root()


def effective_class(document: UiDocument, node: WidgetNode) -> str:
    custom = document.custom_widget(node.class_name)
    if isinstance(custom, CustomWidgetNode) and custom.extends:
        return custom.extends.split("::")[-1]
    return node.class_name


def managed_container(document: UiDocument, node: WidgetNode) -> bool:
    """Tab widgets, splitters and the rest keep pages without a layout slot."""
    return effective_class(document, node) in _MANAGED


def effective_selection(document: UiDocument, state: SelectionState) -> SelectionState:
    """Empty selection is drawn as the form. Nothing writes that back."""
    if state.ids and state.current is not None:
        return state
    root = document.root.id
    return SelectionState((root,), root)


def parent_step(document: UiDocument, node: NodeId) -> Optional[NodeId]:
    if node == document.root.id:
        return None
    current = document.parent(node)
    while current is not None:
        if isinstance(current, LayoutItemNode) or current.kind == "ui":
            current = document.parent(current.id)
            continue
        if isinstance(current, (WidgetNode, LayoutNode)):
            return current.id
        current = document.parent(current.id)
    return None


def first_child(document: UiDocument, node: NodeId) -> Optional[NodeId]:
    found = document.get(node)
    if isinstance(found, WidgetNode):
        if found.layout is not None:
            return found.layout.id
        if found.child_widgets:
            return found.child_widgets[0].id
        return None
    if isinstance(found, LayoutNode):
        for item in found.items:
            content = item.content
            if isinstance(content, (WidgetNode, LayoutNode, SpacerNode)):
                return content.id
    return None


def next_in_outline(document: UiDocument, node: NodeId, backwards: bool) -> Optional[NodeId]:
    widgets = _widgets(document)
    if len(widgets) < 2:
        return None
    if node in widgets:
        index = widgets.index(node)
        step = -1 if backwards else 1
        return widgets[(index + step) % len(widgets)]
    # A layout is not in the widget list. The anchor is already the next widget.
    anchor = _outline_index(document, node, widgets)
    if backwards:
        return widgets[(anchor - 1) % len(widgets)]
    return widgets[anchor % len(widgets)]


def nearest_in_direction(
    document: UiDocument, index: HitIndex, node: NodeId, direction: Direction
) -> Optional[NodeId]:
    origin = index.rect_of(node)
    if origin is None:
        return None
    order = {widget_id: position for position, widget_id in enumerate(_widgets(document))}
    best: Optional[NodeId] = None
    best_key: Optional[Tuple[float, int]] = None
    for widget_id, rect in _visible_widgets(index, document):
        if widget_id == node:
            continue
        if document.is_ancestor(widget_id, node) or document.is_ancestor(node, widget_id):
            continue
        gap = _past_edge(origin, rect, direction)
        if gap is None:
            continue
        along, across = gap
        key = (along + 2.0 * across, order.get(widget_id, 0))
        if best_key is None or key < best_key:
            best_key = key
            best = widget_id
    return best


def _past_edge(origin: Rect, rect: Rect, direction: Direction) -> Optional[Tuple[float, float]]:
    """Distance past the facing edge, and the distance across that axis."""
    if direction == "right":
        edge = origin.x + origin.width
        if rect.x < edge:
            return None
        return (float(rect.x - edge), abs(_mid_y(rect) - _mid_y(origin)))
    if direction == "left":
        if rect.x + rect.width > origin.x:
            return None
        return (float(origin.x - (rect.x + rect.width)), abs(_mid_y(rect) - _mid_y(origin)))
    if direction == "down":
        edge = origin.y + origin.height
        if rect.y < edge:
            return None
        return (float(rect.y - edge), abs(_mid_x(rect) - _mid_x(origin)))
    if rect.y + rect.height > origin.y:
        return None
    return (float(origin.y - (rect.y + rect.height)), abs(_mid_x(rect) - _mid_x(origin)))


def _mid_x(rect: Rect) -> float:
    return rect.x + rect.width / 2.0


def _mid_y(rect: Rect) -> float:
    return rect.y + rect.height / 2.0


def band_candidates(
    document: UiDocument, index: HitIndex, owner: NodeId
) -> Tuple[Tuple[NodeId, Rect], ...]:
    found = document.get(owner)
    child_ids: List[NodeId] = []
    if isinstance(found, WidgetNode) and found.layout is not None:
        child_ids.extend(_layout_children(found.layout))
    elif isinstance(found, LayoutNode):
        child_ids.extend(_layout_children(found))
    elif isinstance(found, WidgetNode):
        child_ids.extend(child.id for child in found.child_widgets)
    seats: List[Tuple[NodeId, Rect]] = []
    for child_id in child_ids:
        rect = index.rect_of(child_id)
        if rect is not None:
            seats.append((child_id, rect))
    return tuple(seats)


def ancestors(document: UiDocument, node: NodeId) -> FrozenSet[NodeId]:
    return frozenset(document.ancestors(node))


def free_origin(document: UiDocument, index: HitIndex, node: NodeId) -> RectValue:
    found = document.get(node)
    if isinstance(found, WidgetNode):
        entry = found.prop("geometry")
        if entry is not None and isinstance(entry.value, RectValue):
            return entry.value
    rect = index.rect_of(node)
    if rect is None:
        return RectValue(0, 0, 1, 1)
    place = positioning_of(document, node)
    if isinstance(place, Free):
        parent = index.rect_of(place.parent)
        if parent is not None:
            return RectValue(rect.x - parent.x, rect.y - parent.y, rect.width, rect.height)
    return RectValue(rect.x, rect.y, rect.width, rect.height)


def _layout_of_item(document: UiDocument, item_id: Optional[NodeId]) -> Optional[NodeId]:
    if item_id is None:
        return None
    parent = document.parent(item_id)
    if isinstance(parent, LayoutNode):
        return parent.id
    return None


def _widgets(document: UiDocument) -> Tuple[NodeId, ...]:
    cached = _WIDGETS.get(document)
    if cached is not None and cached[0] == document.revision:
        return cached[1]
    found = tuple(node.id for node in document.iter_preorder() if isinstance(node, WidgetNode))
    _WIDGETS[document] = (document.revision, found)
    return found


def _outline_index(document: UiDocument, node: NodeId, widgets: Sequence[NodeId]) -> int:
    seen = False
    for current in document.iter_preorder():
        if current.id == node:
            seen = True
        if seen and current.id in widgets and current.id != node:
            return widgets.index(current.id)
    return 0


def _visible_widgets(index: HitIndex, document: UiDocument) -> Tuple[Tuple[NodeId, Rect], ...]:
    cached = _VISIBLE.get(index)
    if (
        cached is not None
        and cached[0] == index.epoch
        and cached[1] is document
        and cached[2] == document.revision
    ):
        return cached[3]
    found: List[Tuple[NodeId, Rect]] = []
    stack = [document.root.id]
    while stack:
        parent = stack.pop()
        for entry in index.children_of(parent):
            if not entry.visible:
                continue
            if entry.kind == "widget":
                found.append((entry.node, entry.rect))
            if entry.kind in ("widget", "layout"):
                stack.append(entry.node)
    rows = tuple(found)
    _VISIBLE[index] = (index.epoch, document, document.revision, rows)
    return rows


def _layout_children(layout: LayoutNode) -> List[NodeId]:
    child_ids: List[NodeId] = []
    for item in layout.items:
        content = item.content
        if isinstance(content, (WidgetNode, SpacerNode, LayoutNode)):
            child_ids.append(content.id)
    return child_ids
