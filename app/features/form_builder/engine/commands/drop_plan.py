from __future__ import annotations

from dataclasses import replace
from typing import Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.commands.base import Command
from app.features.form_builder.engine.commands.catalog import (
    InsertFragment,
    MoveNodes,
    SetLayoutCell,
    SetProperty,
)
from app.features.form_builder.engine.commands.catalog_ext.drop import (
    AdoptIntoBox,
    InsertFormRow,
    InsertPage,
    SpliceReading,
    SwapFormRows,
    WrapWithNew,
)
from app.features.form_builder.engine.commands.placement import (
    InBoxLayout,
    InContainer,
    InFormRow,
    InGridCell,
    Placement,
)
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.drop_target import (
    AcceptedDrop,
    DropIndicator,
    DropPayload,
    DropTarget,
    RefusedDrop,
)
from app.features.form_builder.engine.query.hit_index import Rect
from app.features.form_builder.engine.query.tree import form_rows, grid_shape, is_page_container
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec
from app.features.form_builder.engine.ui4.values import NumberValue, RectValue


def commands_for(
    doc: UiDocument,
    target: DropTarget,
    payload: DropPayload,
    fragment: Optional[Fragment],
) -> Tuple[Command, ...]:
    if not isinstance(target, AcceptedDrop):
        return ()
    if payload.kind == "spacer" and target.action in ("form_cell", "form_row"):
        return ()
    action = target.action
    sources = payload.source_ids
    if action == "box":
        return _place(doc, InBoxLayout(target.host, target.index), sources, fragment, False)
    if action == "splitter":
        return _place(doc, InContainer(target.host, target.index), sources, fragment, False)
    if action == "grid_cell":
        return _place(doc, _grid(target, "cell"), sources, fragment, False)
    if action == "grid_row":
        return _place(doc, _grid(target, "insert_row"), sources, fragment, False)
    if action == "grid_reading":
        return (SpliceReading(target.host, target.index, sources, fragment),)
    if action == "grid_column":
        return _place(doc, _grid(target, "insert_column"), sources, fragment, False)
    if action == "form_cell":
        role = target.role if target.role in ("label", "field", "spanning") else "field"
        return _place(doc, InFormRow(target.host, target.row, role, False), sources, fragment, False)
    if action == "form_row":
        return _form_row(doc, target, payload, fragment)
    if action == "wrap":
        return _wrap(doc, target, sources, fragment)
    if action == "auto_layout":
        return _adopt(target.host, sources, fragment)
    if action == "free":
        return _free(doc, target, payload, sources, fragment)
    if action == "page":
        return _page(doc, target, payload, sources, fragment)
    if action == "new_page":
        return _new_page(target, sources, fragment)
    return ()


def auto_commands(
    doc: UiDocument,
    anchor: Optional[NodeId],
    payload: DropPayload,
    fragment: Optional[Fragment],
) -> Tuple[Command, ...]:
    target = auto_target(doc, anchor, payload)
    if target is None:
        return ()
    return commands_for(doc, target, payload, fragment)


def indicate_preview(doc: UiDocument, index: object, target: AcceptedDrop) -> AcceptedDrop:
    """Fill the line and the sentence Enter would show. ``index`` has ``rect_of``."""

    sentence = _preview_words(doc, target)
    frame = _rect_of(index, target.host) or Rect(0, 0, 1, 1)
    return replace(
        target,
        sentence=sentence,
        chip=sentence,
        indicator=DropIndicator(_preview_line(doc, index, target, frame), dashed=target.action not in ("box", "form_row")),
        frame=frame,
    )


def _preview_words(doc: UiDocument, target: AcceptedDrop) -> str:
    if target.action == "box":
        layout = doc.get(target.host)
        if isinstance(layout, LayoutNode) and target.index > 0:
            for item in layout.items:
                content = item.content
                if item.slot_index == target.index - 1 and content is not None:
                    name = getattr(content, "object_name", "") or ""
                    if name:
                        return "Goes right after %s." % name
        if target.index == 0:
            return "Goes at the start."
    if target.action == "form_row":
        return "Goes on a new row."
    if target.action == "form_cell":
        return "Goes in this cell."
    if target.action in ("grid_cell", "grid_row", "grid_column", "grid_reading"):
        return "Goes in the grid."
    if target.action == "free":
        return "Goes at x %d, y %d." % (target.x, target.y)
    if target.action == "auto_layout":
        return "Goes inside, in a vertical layout."
    return "Goes here."


def _preview_line(doc: UiDocument, index: object, target: AcceptedDrop, frame: Rect) -> Rect:
    if target.action == "box":
        layout = doc.get(target.host)
        if isinstance(layout, LayoutNode) and target.index > 0:
            for item in layout.items:
                content = item.content
                if item.slot_index == target.index - 1 and content is not None:
                    rect = _rect_of(index, content.id)
                    if rect is not None:
                        return Rect(frame.x + 4, rect.y + rect.height, max(frame.width - 8, 2), 2)
        return Rect(frame.x + 4, frame.y + 3, max(frame.width - 8, 2), 2)
    if target.action == "form_row":
        return Rect(frame.x + 4, frame.y + max(frame.height - 3, 0), max(frame.width - 8, 2), 2)
    if target.action == "free":
        return Rect(target.x, target.y, target.width or 80, target.height or 24)
    return frame


def _rect_of(index: object, node: NodeId) -> Optional[Rect]:
    found = getattr(index, "rect_of", None)
    if found is None:
        return None
    rect = found(node)
    return rect if isinstance(rect, Rect) else None


def auto_target(
    doc: UiDocument,
    anchor: Optional[NodeId],
    payload: DropPayload,
) -> Optional[Union[AcceptedDrop, RefusedDrop]]:
    """The target Enter would use. None when there is nowhere to put it."""
    if payload.kind == "spacer":
        layout = _anchor_layout(doc, anchor)
        if isinstance(layout, LayoutNode) and layout.class_name == "QFormLayout":
            return None
    layout = _anchor_layout(doc, anchor)
    if isinstance(layout, LayoutNode):
        return _layout_target(doc, layout, anchor, payload)
    bare = _anchor_bare(doc, anchor)
    if bare is None:
        return None
    if bare.child_widgets:
        return _free_target(bare.id, 8, 8, payload)
    return _blank("auto_layout", bare.id)


def _form_row(
    doc: UiDocument,
    target: AcceptedDrop,
    payload: DropPayload,
    fragment: Optional[Fragment],
) -> Tuple[Command, ...]:
    if target.role == "label" or payload.kind == "label":
        return _place(
            doc,
            InFormRow(target.host, target.row, "label", True),
            payload.source_ids,
            fragment,
            False,
        )
    if len(payload.source_ids) == 1:
        return (InsertFormRow(target.host, target.row, existing=payload.source_ids[0]),)
    if len(payload.source_ids) > 1:
        return _place(
            doc,
            InFormRow(target.host, target.row, "field", True),
            payload.source_ids,
            fragment,
            False,
        )
    if fragment is None:
        return ()
    return (InsertFormRow(target.host, target.row, fragment=_plain(fragment)),)


def _wrap(
    doc: UiDocument,
    target: AcceptedDrop,
    sources: Tuple[NodeId, ...],
    fragment: Optional[Fragment],
) -> Tuple[Command, ...]:
    neighbour = target.wrap_neighbour
    if neighbour is None:
        return ()
    if len(sources) != 1:
        index = target.index if target.wrap_side == "before" else target.index + 1
        return _place(doc, InBoxLayout(target.host, index), sources, fragment, False)
    return (
        WrapWithNew(
            neighbour,
            target.wrap_side or "after",
            target.wrap_layout or "QHBoxLayout",
            fragment=None if sources else _plain(fragment) if fragment is not None else None,
            existing=sources[0] if sources else None,
        ),
    )


def _page(
    doc: UiDocument,
    target: AcceptedDrop,
    payload: DropPayload,
    sources: Tuple[NodeId, ...],
    fragment: Optional[Fragment],
) -> Tuple[Command, ...]:
    page_id = target.page
    if page_id is None or not doc.contains(page_id):
        return ()
    page = doc.node(page_id)
    if isinstance(page, WidgetNode) and page.layout is not None:
        nested = _layout_target(doc, page.layout, None, payload)
        return commands_for(doc, nested, payload, fragment)
    if isinstance(page, WidgetNode) and page.child_widgets:
        return _free(doc, _free_target(page.id, 8, 8, payload), payload, sources, fragment)
    return _adopt(page_id, sources, fragment)


def _new_page(
    target: AcceptedDrop,
    sources: Tuple[NodeId, ...],
    fragment: Optional[Fragment],
) -> Tuple[Command, ...]:
    if sources:
        return (InsertPage(target.host, existing=sources),)
    if fragment is None:
        return ()
    return (InsertPage(target.host, fragment=_plain(fragment)),)


def _free(
    doc: UiDocument,
    target: AcceptedDrop,
    payload: DropPayload,
    sources: Tuple[NodeId, ...],
    fragment: Optional[Fragment],
) -> Tuple[Command, ...]:
    width = target.width or payload.default_size[0]
    height = target.height or payload.default_size[1]
    host = doc.node(target.host) if doc.contains(target.host) else None
    count = len(host.child_widgets) if isinstance(host, WidgetNode) else 0
    place = InContainer(target.host, count, RectValue(target.x, target.y, width, height))
    return _place(doc, place, sources, fragment, False)


def _adopt(
    container: NodeId,
    sources: Tuple[NodeId, ...],
    fragment: Optional[Fragment],
) -> Tuple[Command, ...]:
    if sources:
        return (AdoptIntoBox(container, existing=sources),)
    if fragment is None:
        return ()
    return (AdoptIntoBox(container, fragment=_plain(fragment)),)


def _place(
    doc: UiDocument,
    place: Placement,
    sources: Sequence[NodeId],
    fragment: Optional[Fragment],
    auto: bool,
) -> Tuple[Command, ...]:
    if sources:
        commands: list = [MoveNodes(tuple(sources), place)]
        if not isinstance(place, InContainer) or place.geometry is None:
            for node_id in sources:
                if doc.contains(node_id) and doc.node(node_id).prop("geometry") is not None:
                    commands.append(SetProperty(node_id, "geometry", None))
        return tuple(commands)
    if fragment is None:
        return ()
    body = fragment if isinstance(place, InContainer) and place.geometry is not None else _plain(fragment)
    return (InsertFragment(place, body, auto_layout=auto),)


def _grid(target: AcceptedDrop, mode: str) -> InGridCell:
    return InGridCell(
        target.host,
        target.row,
        target.column,
        target.rowspan,
        target.colspan,
        mode,  # type: ignore[arg-type]
    )


def _layout_target(
    doc: UiDocument,
    layout: LayoutNode,
    anchor: Optional[NodeId],
    payload: DropPayload,
) -> AcceptedDrop:
    if layout.class_name == "QFormLayout":
        return _form_auto(doc, layout, payload)
    if layout.class_name == "QGridLayout":
        return _grid_auto(doc, layout, payload)
    index = _after(doc, layout, anchor)
    return _blank("box", layout.id, index=index)


def _form_auto(doc: UiDocument, layout: LayoutNode, payload: DropPayload) -> AcceptedDrop:
    rows = form_rows(doc, layout.id)
    role = "label" if payload.kind == "label" else "field"
    if rows:
        _label, field, spanning = rows[-1]
        if spanning is None and field is None and role == "field":
            return _blank("form_cell", layout.id, row=len(rows) - 1, role="field")
        if spanning is None and _label is None and role == "label":
            return _blank("form_cell", layout.id, row=len(rows) - 1, role="label")
    return _blank("form_row", layout.id, row=len(rows), role=role)


def _grid_auto(doc: UiDocument, layout: LayoutNode, payload: DropPayload) -> AcceptedDrop:
    shape = grid_shape(doc, layout.id)
    if shape.empty:
        row, column = shape.empty[0]
        return _blank(
            "grid_cell",
            layout.id,
            row=row,
            column=column,
            rowspan=payload.rowspan,
            colspan=payload.colspan,
        )
    row = shape.rows
    return _blank(
        "grid_cell",
        layout.id,
        row=row,
        column=0,
        rowspan=payload.rowspan,
        colspan=payload.colspan,
    )


def _anchor_layout(doc: UiDocument, anchor: Optional[NodeId]) -> Optional[LayoutNode]:
    node = doc.get(anchor) if anchor is not None else None
    if isinstance(node, LayoutNode):
        return node
    if isinstance(node, WidgetNode) and is_page_container(doc, node.id):
        page = _current_page(node)
        if page is None:
            return None
        if page.layout is not None:
            return page.layout
        return None
    if isinstance(node, WidgetNode) and node.layout is not None and not is_page_container(doc, node.id):
        return node.layout
    if node is not None:
        parent = doc.parent(node.id)
        if isinstance(parent, LayoutItemNode):
            layout = doc.parent(parent.id)
            if isinstance(layout, LayoutNode):
                return layout
    root_layout = doc.root.layout
    return root_layout


def _anchor_bare(doc: UiDocument, anchor: Optional[NodeId]) -> Optional[WidgetNode]:
    node = doc.get(anchor) if anchor is not None else doc.root
    if isinstance(node, WidgetNode) and is_page_container(doc, node.id):
        return _current_page(node)
    if isinstance(node, WidgetNode) and node.layout is None and not is_page_container(doc, node.id):
        return node
    if doc.root.layout is None:
        return doc.root
    return None


def _current_page(widget: WidgetNode) -> Optional[WidgetNode]:
    pages = widget.child_widgets
    if not pages:
        return None
    entry = widget.prop("currentIndex")
    index = 0
    if entry is not None and isinstance(entry.value, NumberValue):
        index = entry.value.value
    if index < 0 or index >= len(pages):
        index = 0
    return pages[index]


def _after(doc: UiDocument, layout: LayoutNode, anchor: Optional[NodeId]) -> int:
    if anchor is None:
        return len(layout.items)
    for item in layout.items:
        content = item.content
        if content is not None and content.id == anchor:
            return item.slot_index + 1
    return len(layout.items)


def _free_target(host: NodeId, x: int, y: int, payload: DropPayload) -> AcceptedDrop:
    width, height = payload.default_size
    return _blank("free", host, x=x, y=y, width=width, height=height)


def _blank(action: str, host: NodeId, **fields: object) -> AcceptedDrop:
    indicator = DropIndicator(Rect(0, 0, 0, 0))
    return AcceptedDrop(
        sentence="",
        chip="",
        host=host,
        action=action,  # type: ignore[arg-type]
        indicator=indicator,
        frame=Rect(0, 0, 0, 0),
        **fields,  # type: ignore[arg-type]
    )


def _plain(fragment: Fragment) -> Fragment:
    return Fragment(
        nodes=tuple(_strip(node) for node in fragment.nodes),
        connections=fragment.connections,
        customwidgets=fragment.customwidgets,
        resources=fragment.resources,
    )


def nudge_commands(doc: UiDocument, ids: Tuple[NodeId, ...], direction: str) -> Tuple[Command, ...]:
    if direction not in ("left", "right", "up", "down") or not ids:
        return ()
    placed = []
    layout: Optional[LayoutNode] = None
    for node_id in ids:
        if not doc.contains(node_id):
            return ()
        item = doc.parent(node_id)
        if not isinstance(item, LayoutItemNode):
            return ()
        parent = doc.parent(item.id)
        if not isinstance(parent, LayoutNode):
            return ()
        if layout is None:
            layout = parent
        elif parent.id != layout.id:
            return ()
        placed.append((node_id, item))
    assert layout is not None
    if layout.class_name == "QFormLayout":
        return _nudge_form(doc, layout, placed, direction)
    if layout.class_name == "QGridLayout":
        return _nudge_grid(layout, placed, direction)
    vertical = layout.class_name != "QHBoxLayout"
    if vertical and direction in ("left", "right"):
        return ()
    if not vertical and direction in ("up", "down"):
        return ()
    forward = direction in ("down", "right")
    indexes = sorted(item.slot_index for _node, item in placed)
    if forward:
        start = indexes[-1] + 2
        if start > len(layout.items):
            return ()
    else:
        if indexes[0] == 0:
            return ()
        start = indexes[0] - 1
    return (MoveNodes(tuple(node_id for node_id, _item in placed), InBoxLayout(layout.id, start)),)


def _nudge_form(
    doc: UiDocument,
    layout: LayoutNode,
    placed: list,
    direction: str,
) -> Tuple[Command, ...]:
    if direction not in ("up", "down"):
        return ()
    rows = {0 if item.row is None else item.row for _node, item in placed}
    if len(rows) != 1:
        return ()
    row = next(iter(rows))
    delta = -1 if direction == "up" else 1
    count = len(form_rows(doc, layout.id))
    if row + delta < 0 or row + delta >= count:
        return ()
    return (SwapFormRows(layout.id, row, delta),)


def _nudge_grid(layout: LayoutNode, placed: list, direction: str) -> Tuple[Command, ...]:
    delta = {"left": (0, -1), "right": (0, 1), "up": (-1, 0), "down": (1, 0)}[direction]
    selected = {item.id for _node, item in placed}
    occupied = set()
    for item in layout.items:
        if item.id in selected:
            continue
        occupied.add((0 if item.row is None else item.row, 0 if item.column is None else item.column))
    commands = []
    destinations = set()
    for _node, item in placed:
        row = (0 if item.row is None else item.row) + delta[0]
        column = (0 if item.column is None else item.column) + delta[1]
        if row < 0 or column < 0 or (row, column) in occupied or (row, column) in destinations:
            return ()
        destinations.add((row, column))
        commands.append(
            SetLayoutCell(
                item.id,
                row,
                column,
                1 if item.rowspan is None else item.rowspan,
                1 if item.colspan is None else item.colspan,
            )
        )
    return tuple(commands)


def _strip(spec: NodeSpec) -> NodeSpec:
    properties = tuple(entry for entry in spec.properties if entry.name != "geometry")
    slots = tuple((name, tuple(_strip(child) for child in kids)) for name, kids in spec.slots)
    return NodeSpec(spec.kind, spec.id, spec.fields, properties, spec.attributes, slots, spec.extra_attrs)
