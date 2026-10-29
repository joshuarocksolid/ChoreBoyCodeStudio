"""Turn catalog commands into primitive ops.

This module does not import ``mutate``. It only calls ``ctx.do``.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from functools import cmp_to_key
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple, Union

from app.features.form_builder.engine.clipboard import (
    connections_for_paste,
    fragment_logic_version,
    free_holder,
    without_logic_version,
)
from app.features.form_builder.engine.commands.base import CommandRejected, PlanContext
from app.features.form_builder.engine.commands.ops import (
    InsertNodeOp,
    MoveNodeOp,
    RemoveNodeOp,
    ReplaceRootOp,
    SetFieldOp,
    SetPropertyOp,
)
from app.features.form_builder.engine.commands.placement import (
    AsMainWindowPart,
    InActionList,
    InBoxLayout,
    InContainer,
    InFormRow,
    InGridCell,
    Placement,
)
from app.features.form_builder.engine.commands.refs import (
    NAME_FIELD,
    identity_name,
    native_delete_ops,
    native_rename_ops,
    rewrite_spec_refs,
)
from app.features.form_builder.engine.query.name_policy import explain_name
from app.features.form_builder.engine.query.pages import page_kind
from app.features.form_builder.engine.ids import IdAllocator, NodeId
from app.features.form_builder.engine.logic.codec import (
    canonical_logic_text,
    marker_read_only,
    read_marker,
    same_logic,
)
from app.features.form_builder.engine.logic.refs import opaque_mentions
from app.features.form_builder.engine.logic.storage import (
    CBCS_LAYOUT_KEYS,
    SUPPORTED_LOGIC_VERSION,
    is_logic_key,
    is_user_logic_key,
    logic_version_text,
)
from app.features.form_builder.engine.query.tree import (
    form_item_role,
    form_occupied_cells,
    form_rows,
    is_page_container,
)
from app.features.form_builder.engine.ui4.document import UiDocument, next_object_name
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, Node, SpacerNode, WidgetNode
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui
from app.features.form_builder.engine.ui4.schema import SCHEMA, SlotsDecl
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import (
    BoolValue,
    CStringValue,
    EnumValue,
    NumberValue,
    RectValue,
    SizePolicyValue,
    SizeValue,
    StringValue,
    Value,
    semantic_equal,
)
from app.features.form_builder.engine.ui4.writer import require_xml_text

_BOX = frozenset({"QVBoxLayout", "QHBoxLayout"})
_GRID = "QGridLayout"
_FORM = "QFormLayout"


def insert_fragment(
    doc: UiDocument,
    ctx: PlanContext,
    placement: Placement,
    fragment: Fragment,
    auto_layout: bool,
) -> Tuple[Tuple[NodeId, ...], Tuple[Tuple[str, str], ...], Tuple[str, ...], Tuple[str, ...]]:
    logic_before = doc.logic_property_count()
    source_version = fragment_logic_version(fragment)
    fragment = without_logic_version(fragment)
    pair = _form_pair_indexes(fragment.nodes) if isinstance(placement, InFormRow) else None
    if isinstance(placement, InFormRow) and pair is None:
        role = _lone_form_role(fragment.nodes)
        if role is not None:
            # Keep the caller's insert_row. Forcing a new row here split a
            # form-row insert: the field shifted the label onto the next row.
            placement = InFormRow(placement.layout, placement.row, role, placement.insert_row)
    incoming = 1 if pair is not None else len(fragment.nodes)
    if pair is not None and isinstance(placement, InFormRow):
        dest = _form_pair_dest(doc, ctx, placement)
    else:
        dest = _destination(doc, ctx, placement, auto_layout, moving=(), incoming=incoming)
    chosen: set = set()
    counts = _name_counts(fragment.nodes)
    mapping: Dict[str, str] = {}
    prepared = tuple(_assign_names(spec, doc, chosen, counts, mapping) for spec in fragment.nodes)
    prepared = tuple(rewrite_spec_refs(spec, mapping) for spec in prepared)
    if not dest.wrap and dest.slot == "children":
        prepared = tuple(_hold_free(spec, doc, chosen) for spec in prepared)
    conflicts = _merge_declarations(doc, ctx, fragment)
    _merge_resources(doc, ctx, fragment)
    top_ids: List[NodeId] = []
    scope: List[NodeId] = []
    for offset, spec in enumerate(prepared):
        if pair is not None:
            column = 0 if offset == pair[0] else 1
            spec = _item_spec(spec, row=dest.row, column=column)
        else:
            spec = _wrap_for_dest(spec, dest, offset)
        allocated = allocate_spec(ctx, spec)
        ctx.do(InsertNodeOp(dest.parent, dest.slot, dest.index + offset, allocated))
        if dest.geometry is not None:
            target = _content_spec_id(allocated)
            rect = dest.geometry
            if offset:
                rect = RectValue(rect.x + 16 * offset, rect.y + 16 * offset, rect.width, rect.height)
            set_property(doc, ctx, target, "geometry", rect)
        top_ids.append(_content_spec_id(allocated))
        scope.extend(allocated.ids())
    alive = doc.names()
    dangling: List[str] = []
    seen_dangling: Set[str] = set()
    pasted_connections = connections_for_paste(fragment, doc.names())
    for spec in pasted_connections:
        rewritten = rewrite_spec_refs(spec, mapping)
        allocated = allocate_spec(ctx, rewritten)
        count = len(doc.ui.children("connections"))
        ctx.do(InsertNodeOp(doc.ui.id, "connections", count, allocated))
        scope.extend(allocated.ids())
        for end in (rewritten.field("sender"), rewritten.field("receiver")):
            if isinstance(end, str) and end and end not in alive and end not in seen_dangling:
                seen_dangling.add(end)
                dangling.append(end)
    renames = tuple(mapping.items())
    if source_version is not None and source_version > SUPPORTED_LOGIC_VERSION:
        # Pasted behavior from a newer build is kept as copied: raise the marker first, so the
        # logic participants see read-only logic and leave the copied text alone (UX D20).
        _raise_logic_marker(doc, ctx, source_version)
    if renames:
        _participant_renames(ctx, doc, renames, scope)
    if doc.logic_property_count() != logic_before:
        _sync_logic_marker(doc, ctx)
    from app.features.form_builder.engine.commands.catalog_ext.tab_order import join_order

    join_order(doc, ctx, scope)
    current = top_ids[0] if top_ids else None
    ctx.select(tuple(top_ids), current)
    return tuple(top_ids), renames, conflicts, tuple(dangling)


def delete_nodes(doc: UiDocument, ctx: PlanContext, ids: Tuple[NodeId, ...]) -> Tuple[str, ...]:
    if not ids:
        return ()
    for node_id in ids:
        _require(doc, node_id)
    deleted = set(ids)
    roots = []
    for node_id in _sort_ids(doc, ids):
        if any(doc.is_ancestor(other, node_id) for other in deleted if other != node_id):
            continue
        node = doc.node(node_id)
        if node.parent_id is None or node.id == doc.root.id:
            raise CommandRejected("The form itself cannot be deleted.")
        roots.append(node_id)
    targets = []
    for node_id in roots:
        targets.append(_removal_target(doc, node_id))
    target_set = set(targets)
    final_targets = []
    for node_id in _sort_ids(doc, targets):
        if any(doc.is_ancestor(other, node_id) for other in target_set if other != node_id):
            continue
        if doc.contains(node_id):
            final_targets.append(node_id)
    if not final_targets:
        return ()
    logic_before = doc.logic_property_count()
    anchor = doc.node(final_targets[0])
    parent = doc.parent(final_targets[0])
    siblings = list(parent.children(anchor.parent_slot or "")) if parent is not None and anchor.parent_slot else []
    removed: set = set()
    names: List[str] = []
    for target in final_targets:
        for node in doc.iter_preorder(target):
            removed.add(node.id)
            name = identity_name(node)
            if name and name not in names:
                names.append(name)
    selection = _survivor(doc, siblings, anchor.slot_index, removed, parent)
    for target in final_targets:
        if doc.contains(target):
            ctx.do(RemoveNodeOp(target))
    codes: List[str] = []
    gone: List[str] = []
    for name in names:
        if doc.by_name(name):
            if "FB010" not in codes:
                codes.append("FB010")
        elif name not in gone:
            gone.append(name)
    for op in native_delete_ops(doc, tuple(gone)):
        ctx.do(op)
    for participant in ctx.participants():
        delete_ops = getattr(participant, "delete_ops", None)
        if delete_ops is None:
            continue
        for op in delete_ops(doc, tuple(gone)):
            ctx.do(op)
    if doc.logic_property_count() != logic_before:
        _sync_logic_marker(doc, ctx)
    if selection:
        ctx.select(selection)
    return tuple(codes)


def move_nodes(doc: UiDocument, ctx: PlanContext, ids: Tuple[NodeId, ...], placement: Placement) -> None:
    if not ids:
        return
    for node_id in ids:
        _require(doc, node_id)
    ordered = _sort_ids(doc, ids)
    if isinstance(placement, InBoxLayout):
        layout = _require_layout(doc, placement.layout)
        if layout.class_name == _FORM:
            _move_box_into_form(doc, ctx, ordered, placement)
        else:
            carriers = [_ensure_item(doc, ctx, node_id, placement.layout) for node_id in ordered]
            _reject_into_self(doc, carriers, placement.layout)
            place_nodes(doc, ctx, carriers, placement.layout, "layout_items", placement.index)
    elif isinstance(placement, (InGridCell, InFormRow)):
        _move_grid(doc, ctx, ordered, placement)
    elif isinstance(placement, InContainer):
        _move_container(doc, ctx, ordered, placement)
    elif isinstance(placement, InActionList):
        _require(doc, placement.widget)
        _reject_into_self(doc, ordered, placement.widget)
        place_nodes(doc, ctx, ordered, placement.widget, "add_actions", placement.index)
    elif isinstance(placement, AsMainWindowPart):
        _move_part(doc, ctx, ordered, placement)
    else:
        raise CommandRejected("That destination is not supported.")
    ctx.select(tuple(ordered))


def wrap_nodes(
    doc: UiDocument,
    ctx: PlanContext,
    ids: Tuple[NodeId, ...],
    container_class: Optional[str],
    layout_class: str,
    cells: Optional[Tuple[Tuple[NodeId, int, int], ...]],
) -> NodeId:
    if not ids:
        raise CommandRejected("There is nothing to wrap.")
    # Reject a gone id before any helper reads its parent. A transaction can
    # hold a wrap of a node that an earlier command in it deleted.
    for node_id in ids:
        _require(doc, node_id)
    ids = widgets_in_box_wrap(doc, ids, layout_class)
    ordered = _sort_ids(doc, [_require(doc, node_id).id for node_id in ids])
    carriers = []
    parents = set()
    for node_id in ordered:
        carrier = _item_carrier(doc, node_id) or node_id
        carriers.append(carrier)
        parent = doc.parent(carrier)
        slot = doc.node(carrier).parent_slot
        if parent is None or slot is None:
            raise CommandRejected("Those objects cannot be wrapped.")
        parents.add((parent.id, slot))
    if len(parents) != 1:
        raise CommandRejected("Wrap only works on siblings.")
    parent_id, slot = next(iter(parents))
    parent = doc.node(parent_id)
    if isinstance(parent, LayoutNode) and parent.class_name in (_FORM, _GRID):
        ordered = _sort_by_cell(doc, ordered)
        carriers = [_item_carrier(doc, node_id) or node_id for node_id in ordered]
    anchor = _form_anchor(doc, parent, carriers)
    first = min(doc.node(carrier).slot_index for carrier in carriers)
    if container_class is None:
        if parent.kind != "layout":
            raise CommandRejected("A layout-only wrap needs a parent layout.")
        layout = _alloc_layout(doc, ctx, layout_class)
        item = _alloc_item_holding(ctx, layout)
        ctx.do(InsertNodeOp(parent_id, slot, first, item))
        place_nodes(doc, ctx, carriers, layout.id, "layout_items", 0, keep_order=True)  # type: ignore[arg-type]
        _apply_named_cells(doc, ctx, layout.id, cells)  # type: ignore[arg-type]
        _finish_form_layout(doc, ctx, layout.id, bool(cells))  # type: ignore[arg-type]
        _clear_box_cells(doc, ctx, layout.id, layout_class)  # type: ignore[arg-type]
        if anchor is not None:
            _place_wrapped_form_row(doc, ctx, parent_id, item.id, anchor, layout_class)  # type: ignore[arg-type]
        ctx.select((layout.id,))  # type: ignore[arg-type]
        return layout.id  # type: ignore[return-value]
    widget, layout = _alloc_container(doc, ctx, container_class, layout_class)
    held: Optional[NodeSpec] = None
    if parent.kind == "layout":
        held = _alloc_item_holding(ctx, widget)
        ctx.do(InsertNodeOp(parent_id, slot, first, held))
    else:
        ctx.do(InsertNodeOp(parent_id, slot, first, widget))
    place_nodes(doc, ctx, carriers, layout.id, "layout_items", 0, keep_order=True)  # type: ignore[arg-type]
    _apply_named_cells(doc, ctx, layout.id, cells)  # type: ignore[arg-type]
    _finish_form_layout(doc, ctx, layout.id, bool(cells))  # type: ignore[arg-type]
    _clear_box_cells(doc, ctx, layout.id, layout_class)  # type: ignore[arg-type]
    if anchor is not None and held is not None:
        _place_wrapped_form_row(doc, ctx, parent_id, held.id, anchor, layout_class)  # type: ignore[arg-type]
    ctx.select((widget.id,))  # type: ignore[arg-type]
    return widget.id  # type: ignore[return-value]


def unwrap_node(doc: UiDocument, ctx: PlanContext, node_id: NodeId) -> None:
    node = _require(doc, node_id)
    if node.id == doc.root.id or (isinstance(node, WidgetNode) and is_page_container(doc, node.id)):
        raise CommandRejected("That object cannot be unwrapped.")
    if isinstance(node, LayoutNode):
        _lift_layout(doc, ctx, node)
        return
    if not isinstance(node, WidgetNode) or node.layout is None:
        raise CommandRejected("That object has nothing to unwrap.")
    item_id = _item_carrier(doc, node.id)
    if item_id is None:
        raise CommandRejected("Unwrap needs the container to sit in a layout.")
    parent = doc.parent(item_id)
    if parent is None or parent.kind != "layout":
        raise CommandRejected("Unwrap needs a parent layout.")
    index = doc.node(item_id).slot_index
    children = [item.id for item in node.layout.items]
    for offset, child in enumerate(children):
        ctx.do(MoveNodeOp(child, parent.id, "layout_items", index + offset))
    ctx.do(RemoveNodeOp(item_id))
    _reseat_form_items(doc, ctx, parent.id, children)
    ctx.select(tuple(_content_id(doc, child) for child in children))


def apply_layout_command(
    doc: UiDocument,
    ctx: PlanContext,
    widget_id: NodeId,
    layout_class: str,
    order: Tuple[NodeId, ...],
    cells: Optional[Tuple[Tuple[NodeId, int, int, int, int], ...]],
) -> NodeId:
    widget = _require(doc, widget_id)
    if not isinstance(widget, WidgetNode):
        raise CommandRejected("That object is not a widget.")
    if widget.layout is not None:
        raise CommandRejected("That container already has a layout.")
    layout = _alloc_layout(doc, ctx, layout_class)
    ctx.do(InsertNodeOp(widget_id, "layout", 0, layout))
    child_ids = list(order) if order else [child.id for child in widget.child_widgets]
    cell_map = {}
    if cells:
        for child_id, row, column, rowspan, colspan in cells:
            cell_map[child_id] = (row, column, rowspan, colspan)
    for index, child_id in enumerate(child_ids):
        _require(doc, child_id)
        row = column = None
        rowspan = colspan = 1
        if child_id in cell_map:
            row, column, rowspan, colspan = cell_map[child_id]
        item = allocate_spec(
            ctx,
            _item_spec(
                None,
                row=row,
                column=column,
                rowspan=None if rowspan == 1 else rowspan,
                colspan=None if colspan == 1 else colspan,
            ),
        )
        ctx.do(InsertNodeOp(layout.id, "layout_items", index, item))  # type: ignore[arg-type]
        ctx.do(MoveNodeOp(child_id, item.id, "content", 0))  # type: ignore[arg-type]
        if doc.node(child_id).prop("geometry") is not None:
            ctx.do(SetPropertyOp(child_id, "property", "geometry", None, None))
    _finish_form_layout(doc, ctx, layout.id, bool(cell_map))  # type: ignore[arg-type]
    ctx.select((layout.id,))  # type: ignore[arg-type]
    return layout.id  # type: ignore[return-value]


def break_layout(
    doc: UiDocument,
    ctx: PlanContext,
    layout_id: NodeId,
    geometries: Tuple[Tuple[NodeId, RectValue], ...],
) -> None:
    layout = _require_layout(doc, layout_id)
    parent = doc.parent(layout_id)
    if parent is None:
        raise CommandRejected("That layout cannot be broken.")
    if parent.kind == "widget" and layout.parent_slot == "layout":
        contents = []
        for item in layout.items:
            content = item.content
            if content is not None:
                contents.append(content.id)
        geom = {node_id: rect for node_id, rect in geometries}
        count = len(parent.children("children"))
        for offset, content_id in enumerate(contents):
            ctx.do(MoveNodeOp(content_id, parent.id, "children", count + offset))
            if content_id in geom:
                set_property(doc, ctx, content_id, "geometry", geom[content_id])
        ctx.do(RemoveNodeOp(layout_id))
        ctx.select((parent.id,))
        return
    if layout.parent_slot == "content" and parent.kind == "layoutitem":
        _lift_layout(doc, ctx, layout)
        return
    raise CommandRejected("That layout cannot be broken.")


def morph_layout(doc: UiDocument, ctx: PlanContext, layout_id: NodeId, new_class: str) -> None:
    layout = _require_layout(doc, layout_id)
    old = str(layout.field("class_name"))
    if old == new_class:
        ctx.select((layout_id,))
        return
    items = list(layout.items)
    set_field(doc, ctx, layout_id, "class_name", new_class)
    _drop_properties(doc, ctx, layout_id, new_class)
    if old in _BOX and new_class == _GRID:
        vertical = old == "QVBoxLayout"
        for index, item in enumerate(items):
            if vertical:
                _set_cell(doc, ctx, item.id, index, 0, 1, 1)
            else:
                _set_cell(doc, ctx, item.id, 0, index, 1, 1)
    elif new_class == _FORM and (old in _BOX or old == _GRID):
        _normalize_form_items(doc, ctx, layout_id)
    elif old in (_GRID, _FORM) and new_class in _BOX:
        _reorder_reading(doc, ctx, layout_id)
        _clear_cells(doc, ctx, layout_id)
    ctx.select((layout_id,))


def morph_widget(
    doc: UiDocument,
    ctx: PlanContext,
    node_id: NodeId,
    new_class: str,
    accepted: Optional[Tuple[str, ...]] = None,
) -> Tuple[str, ...]:
    node = _require(doc, node_id)
    if node.kind != "widget":
        raise CommandRejected("That object is not a widget.")
    if node.field("class_name") == new_class:
        return ()
    if _holds_content(node) and _class_holds(ctx, doc, new_class) is False:
        raise CommandRejected("The new class cannot hold the contents of this widget.")
    old_class = node.field("class_name")
    set_field(doc, ctx, node_id, "class_name", new_class)
    for old_name, new_name in morph_renames(old_class if isinstance(old_class, str) else "", new_class):
        entry = doc.node(node_id).prop(old_name)
        if entry is None or doc.node(node_id).prop(new_name) is not None:
            continue
        set_property(doc, ctx, node_id, new_name, entry.value)
        set_property(doc, ctx, node_id, old_name, None)
    for old_name, new_name in page_renames(old_class if isinstance(old_class, str) else "", new_class):
        for page in doc.node(node_id).child_widgets:  # type: ignore[attr-defined]
            entry = page.attr(old_name)
            if entry is None or page.attr(new_name) is not None:
                continue
            set_property(doc, ctx, page.id, new_name, entry.value, kind="attribute")
            set_property(doc, ctx, page.id, old_name, None, kind="attribute")
    return _drop_properties(doc, ctx, node_id, new_class, accepted)


def page_renames(old_class: str, new_class: str) -> Tuple[Tuple[str, str], ...]:
    """Page attributes a class change carries over: a tab's title is a toolbox page's label."""
    if old_class == "QTabWidget" and new_class == "QToolBox":
        return (("title", "label"),)
    if old_class == "QToolBox" and new_class == "QTabWidget":
        return (("label", "title"),)
    return ()


_TEXT_EDITS = ("QTextEdit", "QPlainTextEdit", "QTextBrowser")


def morph_renames(old_class: str, new_class: str) -> Tuple[Tuple[str, str], ...]:
    """Properties a class change carries over under a new name, as Designer does.

    A line edit's ``text`` is a text box's ``plainText``, and back.
    """
    if old_class == "QLineEdit" and new_class in _TEXT_EDITS:
        return (("text", "plainText"),)
    if old_class in _TEXT_EDITS and new_class == "QLineEdit":
        return (("plainText", "text"),)
    return ()


def hold_layout(
    doc: UiDocument,
    ctx: PlanContext,
    layout_id: NodeId,
    minimum: SizeValue,
    geometries: Tuple[Tuple[NodeId, RectValue], ...],
    policy: Optional[SizePolicyValue] = None,
) -> NodeId:
    """Put a plain widget in a nested layout's cell and keep the children's boxes."""
    layout = _require_layout(doc, layout_id)
    item = doc.parent(layout_id)
    if item is None or item.kind != "layoutitem":
        raise CommandRejected("That layout is not nested.")
    grand = doc.parent(item.id)
    if grand is None or not isinstance(grand, LayoutNode):
        raise CommandRejected("That layout is not nested.")
    owner_id = grand.owner_widget_id()
    if owner_id is None:
        raise CommandRejected("That layout is not nested.")
    geom = {node_id: rect for node_id, rect in geometries}
    widgets: List[NodeId] = []
    spacers: List[NodeId] = []
    for entry in layout.items:
        content = entry.content
        if isinstance(content, WidgetNode):
            widgets.append(content.id)
        elif isinstance(content, SpacerNode):
            spacers.append(content.id)
        elif isinstance(content, LayoutNode):
            raise CommandRejected("Remove the inner layouts first.")
    for spacer_id in spacers:
        target = _removal_target(doc, spacer_id)
        if doc.contains(target):
            ctx.do(RemoveNodeOp(target))
    base = layout.object_name or ""
    name = _take_name(base + "Widget" if base else "widget", doc, set())
    holder = allocate_spec(ctx, _widget_spec("QWidget", name))
    count = len(doc.node(owner_id).children("children"))
    ctx.do(InsertNodeOp(owner_id, "children", count, holder))
    for index, widget_id in enumerate(widgets):
        ctx.do(MoveNodeOp(widget_id, holder.id, "children", index))  # type: ignore[arg-type]
        if widget_id in geom:
            set_property(doc, ctx, widget_id, "geometry", geom[widget_id])
    ctx.do(RemoveNodeOp(layout_id))
    ctx.do(MoveNodeOp(holder.id, item.id, "content", 0))  # type: ignore[arg-type]
    # A plain widget has no size hint, so without a floor the parent cell
    # would collapse. Only a floor: the cell keeps its share of spare room,
    # so the other cells size as they did at any window size.
    set_property(doc, ctx, holder.id, "minimumSize", minimum)  # type: ignore[arg-type]
    if policy is not None:
        set_property(doc, ctx, holder.id, "sizePolicy", policy)  # type: ignore[arg-type]
    ctx.select((holder.id,))  # type: ignore[arg-type]
    return holder.id  # type: ignore[return-value]


def simplify_grid(doc: UiDocument, ctx: PlanContext, layout_id: NodeId) -> None:
    layout = _require_layout(doc, layout_id)
    items = list(layout.items)
    if not items:
        ctx.select((layout_id,))
        return
    used_rows = set()
    used_columns = set()
    for item in items:
        row = item.row or 0
        column = item.column or 0
        for value in range(row, row + (item.rowspan or 1)):
            used_rows.add(value)
        for value in range(column, column + (item.colspan or 1)):
            used_columns.add(value)
    empty_rows = [value for value in range(max(used_rows) + 1) if value not in used_rows]
    empty_columns = [value for value in range(max(used_columns) + 1) if value not in used_columns]
    for item in items:
        row = item.row or 0
        column = item.column or 0
        new_row = row - sum(1 for gap in empty_rows if gap < row)
        new_column = column - sum(1 for gap in empty_columns if gap < column)
        if item.row != new_row:
            ctx.do(SetFieldOp(item.id, "row", new_row))
        if item.column != new_column:
            ctx.do(SetFieldOp(item.id, "column", new_column))
    ctx.select((layout_id,))


def adjust_size(doc: UiDocument, ctx: PlanContext, node_id: NodeId, size: SizeValue) -> None:
    node = _require(doc, node_id)
    current = node.prop("geometry")
    if current is not None and isinstance(current.value, RectValue):
        rect = RectValue(current.value.x, current.value.y, size.width, size.height)
    else:
        rect = RectValue(0, 0, size.width, size.height)
    set_property(doc, ctx, node_id, "geometry", rect)


def set_zorder(doc: UiDocument, ctx: PlanContext, parent: NodeId, order: Tuple[str, ...]) -> None:
    widget = _require(doc, parent)
    if not isinstance(widget, WidgetNode):
        raise CommandRejected("That object is not a widget.")
    document_order = tuple(child.object_name for child in widget.child_widgets)
    if tuple(order) == document_order:
        if widget.field("zorder") is not None:
            set_field(doc, ctx, parent, "zorder", None)
        return
    if tuple(order) != tuple(widget.zorder):
        set_field(doc, ctx, parent, "zorder", tuple(order))


def set_property(
    doc: UiDocument,
    ctx: PlanContext,
    owner: NodeId,
    name: str,
    value: Optional[Value],
    kind: str = "property",
    stdset: Optional[str] = None,
) -> None:
    node = _require(doc, owner)
    _ensure(value)
    existing = node.prop(name) if kind == "property" else node.attr(name)
    if value is None:
        if existing is not None:
            ctx.do(SetPropertyOp(owner, kind, name, None, None))
        return
    new_stdset = existing.stdset if existing is not None and stdset is None else stdset
    extra = existing.extra_attrs if existing is not None else ()
    if (
        existing is not None
        and semantic_equal(existing.value, value)
        and existing.stdset == new_stdset
        and existing.extra_attrs == extra
    ):
        return
    entry = PropertyEntry(kind, name, value, new_stdset, extra)
    if existing is not None:
        ctx.do(SetPropertyOp(owner, kind, name, entry, None))
        return
    entries = node.properties() if kind == "property" else node.attributes()
    index = _rank_index(ctx, node, entries, name, new_stdset == "0", doc)
    ctx.do(SetPropertyOp(owner, kind, name, entry, index))


def set_property_many(
    doc: UiDocument,
    ctx: PlanContext,
    owners: Tuple[NodeId, ...],
    name: str,
    value: Optional[Value],
    kind: str,
    stdset: Optional[str],
) -> Tuple[NodeId, ...]:
    skipped = []
    for owner in owners:
        node = _require(doc, owner)
        if not _accepts_property(ctx, doc, node, name, kind, stdset):
            skipped.append(owner)
            continue
        set_property(doc, ctx, owner, name, value, kind, stdset)
    return tuple(skipped)


def rename_node(doc: UiDocument, ctx: PlanContext, node_id: NodeId, new_name: str) -> Tuple[str, ...]:
    node = _require(doc, node_id)
    old = identity_name(node)
    if old is None:
        raise CommandRejected("That object has no name.")
    if new_name == old:
        return ()
    _check_name(doc, new_name, current=old, base_methods=_base_methods(ctx))
    if len(doc.by_name(old)) <= 1 and _newer_logic_uses(doc, old):
        raise CommandRejected(
            "%s is used by behavior from a newer version of Code Studio, so it can't be renamed here." % (old,),
            code="FB402",
        )
    set_field(doc, ctx, node_id, NAME_FIELD[node.kind], new_name)
    if node.id == doc.root.id and doc.ui.field("class_name") == old:
        set_field(doc, ctx, doc.ui.id, "class_name", new_name)
    if len(doc.by_name(old)) > 0:
        # The renamed node no longer carries ``old``. Survivors mean it was shared.
        return ("FB010",)
    for op in native_rename_ops(doc, ((old, new_name),), None):
        ctx.do(op)
    _participant_renames(ctx, doc, ((old, new_name),), None)
    return ()


def set_layout_cell(
    doc: UiDocument,
    ctx: PlanContext,
    item: NodeId,
    row: Optional[int],
    column: Optional[int],
    rowspan: Optional[int],
    colspan: Optional[int],
    alignment: Optional[str],
) -> None:
    node = _require(doc, item)
    if node.kind != "layoutitem":
        raise CommandRejected("That object is not a layout cell.")
    parent = doc.parent(item)
    proposed = {
        "row": row,
        "column": column,
        "rowspan": rowspan,
        "colspan": colspan,
        "alignment": alignment,
    }
    if isinstance(parent, LayoutNode) and parent.class_name == _FORM:
        if (
            (rowspan is not None and rowspan > 1)
            or (column is not None and column > 1)
            or (column == 1 and colspan is not None and colspan > 1)
        ):
            raise CommandRejected("A form row has only a label and a field cell.")
        if _form_conflict(doc, parent.id, form_occupied_cells(row, column, colspan), (item,)):
            raise CommandRejected("That cell overlaps another item.")
    elif isinstance(parent, LayoutNode) and parent.class_name == _GRID and _would_overlap(parent, item, proposed):
        raise CommandRejected("That cell overlaps another item.")
    for field_name, value in proposed.items():
        set_field(doc, ctx, item, field_name, value)


def set_field(doc: UiDocument, ctx: PlanContext, node_id: NodeId, field: str, value: object) -> None:
    node = _require(doc, node_id)
    _ensure(value)
    if node.field(field) != value:
        ctx.do(SetFieldOp(node_id, field, value))


def move_page(doc: UiDocument, ctx: PlanContext, container: NodeId, from_index: int, to_index: int) -> None:
    widget = _require(doc, container)
    pages = list(widget.children("children"))
    if from_index < 0 or from_index >= len(pages) or to_index < 0 or to_index >= len(pages):
        raise CommandRejected("That page position is outside the container.")
    page = pages[from_index]
    stored = _number_prop(widget, "currentIndex")
    current = _effective_start(doc, container, stored, len(pages))
    order = list(range(len(pages)))
    moved = order.pop(from_index)
    order.insert(to_index, moved)
    if page.slot_index != to_index:
        ctx.do(MoveNodeOp(page.id, container, "children", to_index))
    if current is not None:
        new_current = order.index(current)
        if new_current != current or (stored is not None and stored != current):
            set_property(doc, ctx, container, "currentIndex", NumberValue(new_current))
    ctx.select((page.id,))


def _effective_start(doc: UiDocument, container: NodeId, stored: Optional[int], count: int) -> Optional[int]:
    """The page index Qt starts on, or None when the container keeps no start page.

    A tab widget, toolbox or stacked widget without ``currentIndex`` starts on its
    first page; a saved index outside the pages clamps, as Qt does (UX-CONT-006).
    """
    if count <= 0:
        return None
    if stored is None:
        kind = page_kind(doc, container)
        if kind is None or not kind.has_start_page:
            return None
        return 0
    return min(max(stored, 0), count - 1)


def set_items(
    doc: UiDocument,
    ctx: PlanContext,
    widget: NodeId,
    items: Optional[Tuple[NodeSpec, ...]],
    rows: Optional[Tuple[NodeSpec, ...]],
    columns: Optional[Tuple[NodeSpec, ...]],
) -> None:
    _require(doc, widget)
    if items is not None:
        _sync_item_slot(doc, ctx, widget, "items", items)
    if rows is not None:
        _sync_item_slot(doc, ctx, widget, "rows", rows)
    if columns is not None:
        _sync_item_slot(doc, ctx, widget, "columns", columns)


def _sync_item_slot(
    doc: UiDocument,
    ctx: PlanContext,
    parent: NodeId,
    slot: str,
    specs: Tuple[NodeSpec, ...],
) -> None:
    """Patch items in place when the tree of ids is unchanged.

    A keystroke in a long list then writes one property. A structural edit
    (add, delete, move, nest) still replaces the slot.
    """
    current = tuple(doc.node(parent).children(slot))
    if _item_patchable(current, specs):
        for node, spec in zip(current, specs):
            _patch_item(doc, ctx, node, spec)
        return
    _replace_slot(doc, ctx, parent, slot, specs)


def _item_patchable(nodes: Tuple[object, ...], specs: Tuple[NodeSpec, ...]) -> bool:
    if len(nodes) != len(specs):
        return False
    for node, spec in zip(nodes, specs):
        if spec.id != node.id or spec.kind != node.kind:  # type: ignore[attr-defined]
            return False
        if _repeated(spec.properties) or _repeated(spec.attributes):
            return False
        if dict(node.to_spec().fields) != dict(spec.fields):  # type: ignore[attr-defined]
            return False
        if _opaque_signature(node) != _opaque_signature_spec(spec):
            return False
        if not _entries_keep_extras(node, spec):
            return False
        if node.kind == "item" and not _item_patchable(  # type: ignore[attr-defined]
            node.children("subitems"), spec.children("subitems")  # type: ignore[attr-defined]
        ):
            return False
    return True


def _repeated(entries: Tuple[PropertyEntry, ...]) -> bool:
    names = [entry.name for entry in entries]
    return len(names) != len(set(names))


def _opaque_signature(node: object) -> Tuple[object, ...]:
    return tuple((child.anchor, child.element) for child in node.opaque())  # type: ignore[attr-defined]


def _opaque_signature_spec(spec: NodeSpec) -> Tuple[object, ...]:
    return tuple((child.field("anchor"), child.field("element")) for child in spec.children("opaque"))


def _entries_keep_extras(node: object, spec: NodeSpec) -> bool:
    for entry in spec.properties:
        existing = node.prop(entry.name)  # type: ignore[attr-defined]
        if existing is not None and existing.extra_attrs != entry.extra_attrs:
            return False
    for entry in spec.attributes:
        existing = node.attr(entry.name)  # type: ignore[attr-defined]
        if existing is not None and existing.extra_attrs != entry.extra_attrs:
            return False
    return True


def _patch_item(doc: UiDocument, ctx: PlanContext, node: object, spec: NodeSpec) -> None:
    _patch_entries(doc, ctx, node, spec.properties, "property")
    _patch_entries(doc, ctx, node, spec.attributes, "attribute")
    for key, value in spec.fields:
        if node.field(key) != value:  # type: ignore[attr-defined]
            set_field(doc, ctx, node.id, key, value)  # type: ignore[attr-defined]
    if node.kind == "item":  # type: ignore[attr-defined]
        for child, child_spec in zip(node.children("subitems"), spec.children("subitems")):  # type: ignore[attr-defined]
            _patch_item(doc, ctx, child, child_spec)


def _patch_entries(doc: UiDocument, ctx: PlanContext, node: object, wanted: Tuple[PropertyEntry, ...], kind: str) -> None:
    by_name = {entry.name: entry for entry in wanted}
    existing = node.properties() if kind == "property" else node.attributes()  # type: ignore[attr-defined]
    for entry in existing:
        if entry.name not in by_name:
            set_property(doc, ctx, node.id, entry.name, None, kind)  # type: ignore[attr-defined]
    for entry in wanted:
        set_property(doc, ctx, node.id, entry.name, entry.value, kind, entry.stdset)  # type: ignore[attr-defined]


def create_action(
    doc: UiDocument,
    ctx: PlanContext,
    spec: NodeSpec,
    group: Optional[NodeId],
    ref_at: Optional[Placement],
) -> NodeId:
    if spec.kind != "action":
        raise CommandRejected("That is not an action.")
    if group is None:
        parent = doc.root.id
    else:
        parent_node = _require(doc, group)
        if parent_node.kind != "actiongroup":
            raise CommandRejected("That is not an action group.")
        parent = group
    prepared = _assign_names(spec, doc, set(), _name_counts((spec,)), {})
    allocated = allocate_spec(ctx, prepared)
    count = len(doc.node(parent).children("actions"))
    ctx.do(InsertNodeOp(parent, "actions", count, allocated))
    if isinstance(ref_at, InActionList):
        add_action_ref(doc, ctx, ref_at, str(allocated.field("name")))
    ctx.select((allocated.id,))  # type: ignore[arg-type]
    return allocated.id  # type: ignore[return-value]


def add_action_ref(doc: UiDocument, ctx: PlanContext, placement: Placement, name: str) -> NodeId:
    if not isinstance(placement, InActionList):
        raise CommandRejected("An action reference goes on a menu or a toolbar.")
    _require(doc, placement.widget)
    spec = allocate_spec(ctx, NodeSpec("actionref", None, (("name", name),)))
    ctx.do(InsertNodeOp(placement.widget, "add_actions", placement.index, spec))
    ctx.select((spec.id,))  # type: ignore[arg-type]
    return spec.id  # type: ignore[return-value]


def create_menu(doc: UiDocument, ctx: PlanContext, placement: Placement, title: str) -> NodeId:
    if not isinstance(placement, InActionList):
        raise CommandRejected("A menu is added to a menu bar or a menu.")
    host = _require(doc, placement.widget)
    name = _take_name("menu", doc, set())
    allocated = allocate_spec(ctx, _widget_spec("QMenu", name))
    count = len(host.children("children"))
    ctx.do(InsertNodeOp(host.id, "children", count, allocated))
    set_property(doc, ctx, allocated.id, "title", StringValue(title))  # type: ignore[arg-type]
    add_action_ref(doc, ctx, placement, name)
    ctx.select((allocated.id,))  # type: ignore[arg-type]
    return allocated.id  # type: ignore[return-value]


def add_connection(
    doc: UiDocument,
    ctx: PlanContext,
    sender: str,
    signal: str,
    receiver: str,
    slot: str,
    index: Optional[int],
) -> NodeId:
    require_logic_writable(doc)
    spec = allocate_spec(ctx, _connection_spec(sender, signal, receiver, slot))
    count = len(doc.ui.children("connections"))
    at = count if index is None else index
    ctx.do(InsertNodeOp(doc.ui.id, "connections", at, spec))
    ctx.select((spec.id,))  # type: ignore[arg-type]
    return spec.id  # type: ignore[return-value]


def edit_connection(
    doc: UiDocument,
    ctx: PlanContext,
    node_id: NodeId,
    sender: Optional[str],
    signal: Optional[str],
    receiver: Optional[str],
    slot: Optional[str],
) -> None:
    require_logic_writable(doc)
    node = _require(doc, node_id)
    if node.kind != "connection":
        raise CommandRejected("That object is not a connection.")
    if sender is not None:
        set_field(doc, ctx, node_id, "sender", sender)
    if signal is not None:
        set_field(doc, ctx, node_id, "signal", _signature(signal))
    if receiver is not None:
        set_field(doc, ctx, node_id, "receiver", receiver)
    if slot is not None:
        set_field(doc, ctx, node_id, "slot", _signature(slot))


def move_connection(doc: UiDocument, ctx: PlanContext, node_id: NodeId, to_index: int) -> None:
    require_logic_writable(doc)
    node = _require(doc, node_id)
    if node.kind != "connection":
        raise CommandRejected("That object is not a connection.")
    if node.slot_index != to_index:
        ctx.do(MoveNodeOp(node_id, doc.ui.id, "connections", to_index))
    ctx.select((node_id,))


def set_tabstops(doc: UiDocument, ctx: PlanContext, names: Optional[Tuple[str, ...]]) -> None:
    set_field(doc, ctx, doc.ui.id, "tabstops", None if names is None else tuple(names))


def set_buddy(doc: UiDocument, ctx: PlanContext, label_widget: NodeId, target: Optional[str]) -> None:
    _require(doc, label_widget)
    if target is None:
        set_property(doc, ctx, label_widget, "buddy", None)
    else:
        set_property(doc, ctx, label_widget, "buddy", CStringValue(target))


def set_button_group(
    doc: UiDocument,
    ctx: PlanContext,
    buttons: Tuple[NodeId, ...],
    group: Optional[str],
) -> None:
    for button in buttons:
        _require(doc, button)
    if group is not None:
        _ensure_group(doc, ctx, group)
        for button in buttons:
            set_property(doc, ctx, button, "buttonGroup", StringValue(group), kind="attribute")
    else:
        for button in buttons:
            if doc.node(button).attr("buttonGroup") is not None:
                set_property(doc, ctx, button, "buttonGroup", None, kind="attribute")
    _drop_empty_groups(doc, ctx)


def set_form_slots(
    doc: UiDocument,
    ctx: PlanContext,
    signals: Optional[Tuple[str, ...]],
    slots: Optional[Tuple[str, ...]],
) -> None:
    require_logic_writable(doc)
    if signals is None and slots is None:
        set_field(doc, ctx, doc.ui.id, "form_slots", None)
        return
    set_field(
        doc,
        ctx,
        doc.ui.id,
        "form_slots",
        SlotsDecl(signals=tuple(signals or ()), slots=tuple(slots or ())),
    )


def promote(
    doc: UiDocument,
    ctx: PlanContext,
    ids: Tuple[NodeId, ...],
    class_name: Optional[str],
    declaration: Optional[NodeSpec],
) -> None:
    for node_id in ids:
        _require(doc, node_id)
    if class_name is not None:
        if declaration is not None:
            _merge_one_declaration(doc, ctx, declaration)
        for node_id in ids:
            set_field(doc, ctx, node_id, "class_name", class_name)
        return
    for node_id in ids:
        current = doc.node(node_id).field("class_name")
        custom = doc.custom_widget(current) if isinstance(current, str) else None
        if custom is None:
            raise CommandRejected("That widget is not promoted.")
        extends = custom.field("extends")
        if not isinstance(extends, str):
            raise CommandRejected("The promotion has no base class.")
        set_field(doc, ctx, node_id, "class_name", extends)
    _drop_unused_declarations(doc, ctx)


def set_custom_widget(doc: UiDocument, ctx: PlanContext, class_name: str, spec: Optional[NodeSpec]) -> None:
    existing = doc.custom_widget(class_name)
    if spec is None:
        if existing is not None:
            ctx.do(RemoveNodeOp(existing.id))
        return
    if existing is not None:
        ctx.do(RemoveNodeOp(existing.id))
    allocated = allocate_spec(ctx, spec)
    count = len(doc.ui.children("customwidgets"))
    ctx.do(InsertNodeOp(doc.ui.id, "customwidgets", count, allocated))


def set_resource_includes(doc: UiDocument, ctx: PlanContext, locations: Tuple[str, ...]) -> None:
    by_location: Dict[str, NodeId] = {}
    for node in doc.ui.children("resources"):
        location = node.field("location")
        if isinstance(location, str) and location not in by_location:
            by_location[location] = node.id
    keep: List[NodeId] = []
    for location in locations:
        found = by_location.get(location)
        if found is not None:
            keep.append(found)
            continue
        spec = allocate_spec(ctx, NodeSpec("resource", None, (("location", location),)))
        count = len(doc.ui.children("resources"))
        ctx.do(InsertNodeOp(doc.ui.id, "resources", count, spec))
        keep.append(spec.id)  # type: ignore[arg-type]
    for node in list(doc.ui.children("resources")):
        if node.id not in keep:
            ctx.do(RemoveNodeOp(node.id))
    if keep:
        place_nodes(doc, ctx, keep, doc.ui.id, "resources", 0)


def replace_document_text(
    doc: UiDocument,
    ctx: PlanContext,
    text: str,
    *,
    reason: str = "xml_edit",
) -> None:
    """Parse ``text`` with ids from ``ctx`` and replace the document.

    View XML and history restore arrive as editor text, which has no carriage
    returns. Those reasons keep the document newline when ``text`` has none.
    """

    class _Bridge(IdAllocator):
        def alloc(self) -> NodeId:  # type: ignore[override]
            return ctx.alloc()

    try:
        loaded = read_ui(text, allocator=_Bridge())
    except UiReadError as exc:
        raise CommandRejected(str(exc), code=exc.code, error=exc) from exc
    names = []
    chosen = getattr(ctx, "selection_before", None)
    for node_id in getattr(chosen, "ids", ()):
        node = doc.get(node_id)
        if node is None:
            continue
        name = identity_name(node)
        if name:
            names.append(name)
    newline = loaded.document.newline
    if reason in ("xml_edit", "history") and "\r" not in text:
        newline = None
    ctx.do(ReplaceRootOp(loaded.document.to_spec(), newline))
    matched = []
    for name in names:
        found = doc.by_name(name)
        if found:
            matched.append(found[0])
    if matched:
        ctx.select(tuple(matched), matched[0])
    else:
        ctx.select((doc.root.id,), doc.root.id)


LOGIC_READ_ONLY_MESSAGE = "This form's behavior was saved by a newer version of Code Studio, so it can't be changed here."


def require_logic_writable(doc: UiDocument) -> None:
    """Refuse with FB402 while the form's logic is newer than this build or its marker can't be read."""
    if marker_read_only(doc.root.prop("cbcsLogic")):
        raise CommandRejected(LOGIC_READ_ONLY_MESSAGE, code="FB402")


def set_logic(doc: UiDocument, ctx: PlanContext, owner: NodeId, key: str, text: Optional[str]) -> None:
    if key in CBCS_LAYOUT_KEYS or key == "cbcsLogic" or not is_logic_key(key):
        raise CommandRejected("That key is not a logic property.")
    require_logic_writable(doc)
    node = _require(doc, owner)
    if text is not None:
        canonical = canonical_logic_text(key, text)
        if canonical.error is not None:
            line, message = canonical.error
            raise CommandRejected(
                "%s can't be read (line %d): %s." % (key, line, message),
                code="FB401",
            )
        text = canonical.text
    if text is None:
        set_property(doc, ctx, owner, key, None, stdset="0")
    else:
        existing = node.prop(key)
        if existing is not None and isinstance(existing.value, StringValue) and same_logic(key, existing.value.text, text):
            # Same meaning as what is stored: keep the stored bytes (CONTRACTS 15.4 rule 7).
            pass
        else:
            set_property(doc, ctx, owner, key, StringValue(text, notr=True), stdset="0")
    _sync_logic_marker(doc, ctx)


def allocate_spec(ctx: PlanContext, spec: NodeSpec) -> NodeSpec:
    node_id = spec.id if spec.id is not None else ctx.alloc()
    slots = tuple(
        (name, tuple(allocate_spec(ctx, child) for child in kids))
        for name, kids in spec.slots
    )
    return NodeSpec(spec.kind, node_id, spec.fields, spec.properties, spec.attributes, slots, spec.extra_attrs)


def place_nodes(
    doc: UiDocument,
    ctx: PlanContext,
    ids: Sequence[NodeId],
    parent: NodeId,
    slot: str,
    start_index: int,
    keep_order: bool = False,
) -> None:
    """Put ``ids`` at ``start_index``. Document order, unless ``keep_order`` is set."""
    if not ids:
        return
    if keep_order:
        ordered = []
        for node_id in ids:
            if node_id not in ordered:
                ordered.append(node_id)
    else:
        ordered = _sort_ids(doc, ids)
    kids = [child.id for child in doc.node(parent).children(slot)]
    kid_set = set(kids)
    selected = [node_id for node_id in ordered if node_id in kid_set]
    outside = [node_id for node_id in ordered if node_id not in kid_set]
    index_of = {node_id: index for index, node_id in enumerate(kids)}
    shift = sum(1 for node_id in selected if index_of[node_id] < start_index)
    selected_set = set(selected)
    unselected = [node_id for node_id in kids if node_id not in selected_set]
    adjusted = start_index - shift
    if adjusted < 0:
        adjusted = 0
    if adjusted > len(unselected):
        adjusted = len(unselected)
    positions = list(kids)
    front = set(unselected[:adjusted])
    for node_id in selected + outside:
        removed = [item for item in positions if item != node_id]
        last = -1
        for index, item in enumerate(removed):
            if item in front:
                last = index
        index = last + 1
        if node_id in positions and positions.index(node_id) == index:
            front.add(node_id)
            continue
        ctx.do(MoveNodeOp(node_id, parent, slot, index))
        positions = removed[:index] + [node_id] + removed[index:]
        front.add(node_id)


class _Dest:
    def __init__(
        self,
        parent: NodeId,
        slot: str,
        index: int,
        wrap: bool,
        geometry: Optional[RectValue] = None,
        row: Optional[int] = None,
        column: Optional[int] = None,
        rowspan: int = 1,
        colspan: int = 1,
    ) -> None:
        self.parent = parent
        self.slot = slot
        self.index = index
        self.wrap = wrap
        self.geometry = geometry
        self.row = row
        self.column = column
        self.rowspan = rowspan
        self.colspan = colspan


def _class_name(spec: NodeSpec) -> str:
    value = spec.field("class_name")
    return value if isinstance(value, str) else ""


def _form_pair_indexes(nodes: Sequence[NodeSpec]) -> Optional[Tuple[int, int]]:
    """Indexes of the label and the field when the fragment is one of each."""
    if len(nodes) != 2 or any(node.kind != "widget" for node in nodes):
        return None
    labels = [index for index, node in enumerate(nodes) if _class_name(node) == "QLabel"]
    if len(labels) != 1:
        return None
    label = labels[0]
    return label, 1 - label


def _lone_form_role(nodes: Sequence[NodeSpec]) -> Optional[str]:
    """A single pasted widget takes its own form column."""
    if len(nodes) != 1 or nodes[0].kind != "widget":
        return None
    if _class_name(nodes[0]) == "QLabel":
        return "label"
    return "field"


def _form_pair_dest(doc: UiDocument, ctx: PlanContext, placement: InFormRow) -> _Dest:
    """One new form row. The label and the field share it."""
    _require_cell_layout(doc, placement)
    if placement.insert_row:
        _shift_axis(doc, ctx, placement.layout, "row", placement.row, (), delta=1)
    cells: Set[Tuple[int, str]] = set()
    cells |= form_occupied_cells(placement.row, 0, 1)
    cells |= form_occupied_cells(placement.row, 1, 1)
    if _form_conflict(doc, placement.layout, cells, ()):
        raise CommandRejected("That cell is already occupied.")
    count = len(doc.node(placement.layout).children("layout_items"))
    return _Dest(placement.layout, "layout_items", count, True, row=placement.row, column=0)


def _hold_free(spec: NodeSpec, doc: UiDocument, chosen: set) -> NodeSpec:
    """A layout or spacer cannot sit at a coordinate. A holder widget can.

    The container already has free children, so it has no layout item list.
    """
    if spec.kind not in ("layout", "spacer"):
        return spec
    inner = _take_name("verticalLayout", doc, chosen) if spec.kind == "spacer" else ""
    return free_holder(spec, _take_name("widget", doc, chosen), inner)


def _destination(
    doc: UiDocument,
    ctx: PlanContext,
    placement: Placement,
    auto_layout: bool,
    moving: Sequence[NodeId],
    incoming: int = 1,
) -> _Dest:
    if isinstance(placement, InBoxLayout):
        layout = _require_layout(doc, placement.layout)
        if layout.class_name == _FORM and incoming > 0:
            start = _form_row_for_index(doc, placement.layout, placement.index)
            _shift_axis(doc, ctx, placement.layout, "row", start, moving, delta=incoming)
            if _form_conflict(doc, placement.layout, _stacked_cells(start, 0, 1, incoming), moving):
                raise CommandRejected("That cell is already occupied.")
            return _Dest(placement.layout, "layout_items", placement.index, True, row=start, column=0)
        return _Dest(placement.layout, "layout_items", placement.index, True)
    if isinstance(placement, InGridCell):
        _require_cell_layout(doc, placement)
        _shift_for_mode(doc, ctx, placement, moving)
        count = len(doc.node(placement.layout).children("layout_items"))
        return _Dest(
            placement.layout,
            "layout_items",
            count,
            True,
            row=placement.row,
            column=placement.column,
            rowspan=placement.rowspan,
            colspan=placement.colspan,
        )
    if isinstance(placement, InFormRow):
        _require_cell_layout(doc, placement)
        column, colspan = _form_role(placement.role)
        if placement.insert_row and incoming:
            _shift_axis(doc, ctx, placement.layout, "row", placement.row, moving, delta=incoming)
        cells = _stacked_cells(placement.row, column, colspan, incoming)
        if _form_conflict(doc, placement.layout, cells, moving):
            raise CommandRejected("That cell is already occupied.")
        count = len(doc.node(placement.layout).children("layout_items"))
        return _Dest(
            placement.layout,
            "layout_items",
            count,
            True,
            row=placement.row,
            column=column,
            rowspan=1,
            colspan=colspan,
        )
    if isinstance(placement, InContainer):
        return _container_dest(doc, ctx, placement, auto_layout)
    if isinstance(placement, InActionList):
        _require(doc, placement.widget)
        return _Dest(placement.widget, "add_actions", placement.index, False)
    if isinstance(placement, AsMainWindowPart):
        _require(doc, placement.main_window)
        count = len(doc.node(placement.main_window).children("children"))
        index = 0 if placement.part == "central" else count
        return _Dest(placement.main_window, "children", index, False)
    raise CommandRejected("That destination is not supported.")


def _container_dest(doc: UiDocument, ctx: PlanContext, placement: InContainer, auto_layout: bool) -> _Dest:
    widget = _require(doc, placement.widget)
    if not isinstance(widget, WidgetNode):
        raise CommandRejected("That object cannot hold widgets.")
    if is_page_container(doc, widget.id):
        return _Dest(widget.id, "children", placement.index, False)
    if widget.layout is not None:
        raise CommandRejected("That container already has a layout.")
    if auto_layout:
        layout_id = _ensure_vbox(doc, ctx, widget.id)
        count = len(doc.node(layout_id).children("layout_items"))
        index = placement.index if placement.index <= count else count
        return _Dest(layout_id, "layout_items", index, True)
    return _Dest(widget.id, "children", placement.index, False, geometry=placement.geometry)


def _move_grid(doc: UiDocument, ctx: PlanContext, ids: Sequence[NodeId], placement: Placement) -> None:
    if isinstance(placement, InGridCell):
        _require_cell_layout(doc, placement)
        layout_id = placement.layout
        row, column, rowspan, colspan = placement.row, placement.column, placement.rowspan, placement.colspan
        _shift_for_mode(doc, ctx, placement, ids)
    elif isinstance(placement, InFormRow):
        _require_cell_layout(doc, placement)
        layout_id = placement.layout
        column, colspan = _form_role(placement.role)
        row, rowspan = placement.row, 1
        if placement.insert_row:
            _shift_axis(doc, ctx, layout_id, "row", row, ids, delta=len(ids))
        if _form_conflict(doc, layout_id, _stacked_cells(row, column, colspan, len(ids)), ids):
            raise CommandRejected("That cell is already occupied.")
    else:
        return
    carriers = [_ensure_item(doc, ctx, node_id, layout_id) for node_id in ids]
    _reject_into_self(doc, carriers, layout_id)
    if isinstance(placement, InGridCell) and placement.mode == "cell":
        _reject_overlap(doc, layout_id, carriers, row, column, rowspan, colspan)
    for offset, carrier in enumerate(carriers):
        parent = doc.parent(carrier)
        if parent is None or parent.id != layout_id:
            count = len(doc.node(layout_id).children("layout_items"))
            ctx.do(MoveNodeOp(carrier, layout_id, "layout_items", count))
        item_row = row + offset
        _set_cell(doc, ctx, carrier, item_row, column, rowspan, colspan)


def _move_container(doc: UiDocument, ctx: PlanContext, ids: Sequence[NodeId], placement: InContainer) -> None:
    widget = _require(doc, placement.widget)
    if not isinstance(widget, WidgetNode):
        raise CommandRejected("That object cannot hold widgets.")
    if widget.layout is not None and not is_page_container(doc, widget.id):
        raise CommandRejected("That container already has a layout.")
    _reject_into_self(doc, ids, widget.id)
    place_nodes(doc, ctx, ids, widget.id, "children", placement.index)
    if placement.geometry is not None:
        for node_id in ids:
            set_property(doc, ctx, node_id, "geometry", placement.geometry)


def _move_part(doc: UiDocument, ctx: PlanContext, ids: Sequence[NodeId], placement: AsMainWindowPart) -> None:
    _require(doc, placement.main_window)
    _reject_into_self(doc, ids, placement.main_window)
    count = len(doc.node(placement.main_window).children("children"))
    index = 0 if placement.part == "central" else count
    place_nodes(doc, ctx, ids, placement.main_window, "children", index)
    if placement.area and placement.part == "dock":
        number = dock_area_number(placement.area)
        for node_id in ids:
            set_property(doc, ctx, node_id, "dockWidgetArea", NumberValue(number), kind="attribute")
    elif placement.area and placement.part == "toolbar":
        for node_id in ids:
            set_property(doc, ctx, node_id, "toolBarArea", EnumValue(placement.area))
    if placement.break_before:
        for node_id in ids:
            set_property(doc, ctx, node_id, "toolBarBreak", BoolValue(True))


#: Qt::DockWidgetArea as the number a .ui file stores in ``dockWidgetArea`` (UX-CONT-012).
_DOCK_AREA_NUMBERS = {
    "Left": 1,
    "Right": 2,
    "Top": 4,
    "Bottom": 8,
    "LeftDockWidgetArea": 1,
    "RightDockWidgetArea": 2,
    "TopDockWidgetArea": 4,
    "BottomDockWidgetArea": 8,
}


def dock_area_number(area: str) -> int:
    """The ``dockWidgetArea`` number for a side name. CommandRejected for any other text."""
    number = _DOCK_AREA_NUMBERS.get(area.strip())
    if number is None:
        raise CommandRejected("That is not a dock side.")
    return number


def _shift_for_mode(doc: UiDocument, ctx: PlanContext, placement: InGridCell, moving: Sequence[NodeId]) -> None:
    if placement.mode == "insert_row":
        _shift_axis(doc, ctx, placement.layout, "row", placement.row, moving)
    elif placement.mode == "insert_column":
        _shift_axis(doc, ctx, placement.layout, "column", placement.column, moving)


def _shift_axis(
    doc: UiDocument,
    ctx: PlanContext,
    layout_id: NodeId,
    field: str,
    start: int,
    moving: Sequence[NodeId],
    delta: int = 1,
) -> None:
    ignore = set()
    for node_id in moving:
        carrier = _item_carrier(doc, node_id)
        if carrier is not None:
            ignore.add(carrier)
    updates = []
    for item in list(doc.node(layout_id).children("layout_items")):
        if item.id in ignore or not isinstance(item, LayoutItemNode):
            continue
        current = item.row if field == "row" else item.column
        current = 0 if current is None else current
        if current >= start:
            updates.append((item.id, field, current + delta))
    batch = getattr(ctx, "apply_field_batch", None)
    if batch is not None:
        batch(updates)
        return
    for node_id, field_name, value in updates:
        ctx.do(SetFieldOp(node_id, field_name, value))


def _ensure_vbox(doc: UiDocument, ctx: PlanContext, widget_id: NodeId) -> NodeId:
    widget = doc.node(widget_id)
    if isinstance(widget, WidgetNode) and widget.layout is not None:
        return widget.layout.id
    layout = _alloc_layout(doc, ctx, "QVBoxLayout")
    ctx.do(InsertNodeOp(widget_id, "layout", 0, layout))
    children = list(doc.node(widget_id).children("children"))
    for index, child in enumerate(children):
        item = allocate_spec(ctx, _item_spec(None))
        ctx.do(InsertNodeOp(layout.id, "layout_items", index, item))  # type: ignore[arg-type]
        ctx.do(MoveNodeOp(child.id, item.id, "content", 0))  # type: ignore[arg-type]
    return layout.id  # type: ignore[return-value]


def _ensure_item(doc: UiDocument, ctx: PlanContext, node_id: NodeId, layout_id: NodeId) -> NodeId:
    carrier = _item_carrier(doc, node_id)
    if carrier is not None:
        return carrier
    item = allocate_spec(ctx, _item_spec(None))
    count = len(doc.node(layout_id).children("layout_items"))
    ctx.do(InsertNodeOp(layout_id, "layout_items", count, item))
    ctx.do(MoveNodeOp(node_id, item.id, "content", 0))  # type: ignore[arg-type]
    return item.id  # type: ignore[return-value]


def _item_carrier(doc: UiDocument, node_id: NodeId) -> Optional[NodeId]:
    node = doc.node(node_id)
    if node.kind == "layoutitem":
        return node_id
    if node.parent_slot == "content" and node.parent_id is not None:
        parent = doc.node(node.parent_id)
        if parent.kind == "layoutitem":
            return parent.id
    return None


def _removal_target(doc: UiDocument, node_id: NodeId) -> NodeId:
    node = doc.node(node_id)
    if node.parent_slot != "content" or node.parent_id is None:
        return node_id
    item = doc.node(node.parent_id)
    if item.kind != "layoutitem" or item.parent_id is None:
        return node_id
    layout = doc.node(item.parent_id)
    if isinstance(layout, LayoutNode) and layout.class_name not in (_GRID, _FORM):
        return item.id
    return node_id


def _lift_layout(doc: UiDocument, ctx: PlanContext, layout: LayoutNode) -> None:
    parent = doc.parent(layout.id)
    if parent is None or parent.kind != "layoutitem":
        raise CommandRejected("That layout cannot be lifted.")
    grand = doc.parent(parent.id)
    if grand is None or grand.kind != "layout":
        raise CommandRejected("That layout cannot be lifted.")
    index = parent.slot_index
    children = [item.id for item in layout.items]
    for offset, child in enumerate(children):
        ctx.do(MoveNodeOp(child, grand.id, "layout_items", index + offset))
    ctx.do(RemoveNodeOp(parent.id))
    _reseat_form_items(doc, ctx, grand.id, children)
    ctx.select(tuple(_content_id(doc, child) for child in children))


def _set_cell(
    doc: UiDocument,
    ctx: PlanContext,
    item_id: NodeId,
    row: int,
    column: int,
    rowspan: int,
    colspan: int,
) -> None:
    node = doc.node(item_id)
    _assign(doc, ctx, node, "row", row)
    _assign(doc, ctx, node, "column", column)
    _assign(doc, ctx, node, "rowspan", None if rowspan == 1 else rowspan)
    _assign(doc, ctx, node, "colspan", None if colspan == 1 else colspan)


def _assign(doc: UiDocument, ctx: PlanContext, node: Node, field: str, value: object) -> None:
    if node.field(field) != value:
        ctx.do(SetFieldOp(node.id, field, value))


def splice_grid_reading(
    doc: UiDocument,
    ctx: PlanContext,
    layout_id: NodeId,
    index: int,
    moving: Sequence[NodeId],
    fragment: Optional[Fragment],
) -> None:
    """Place ``moving`` and ``fragment`` at ``index`` in a uniform grid's reading order.

    Cells before the splice keep their coordinates when those already match.
    Later cells shift so the new order is row-major. A spanned grid is refused.
    """
    layout = doc.node(layout_id)
    if not isinstance(layout, LayoutNode) or layout.class_name != _GRID:
        raise CommandRejected("That layout is not a grid.")
    if any((item.rowspan or 1) != 1 or (item.colspan or 1) != 1 for item in layout.items):
        raise CommandRejected("That grid has a cell that spans.")
    if not moving and fragment is None:
        raise CommandRejected("There is nothing to place.")
    cols = 1
    for item in layout.items:
        cols = max(cols, (item.column or 0) + (item.colspan or 1))
    ordered = sorted(layout.items, key=lambda item: (item.row or 0, item.column or 0, item.slot_index))
    contents = [item.content.id for item in ordered if item.content is not None]
    moving_ids = [node_id for node_id in moving if doc.contains(node_id)]
    moving_set = set(moving_ids)
    at = index - sum(1 for node_id in contents[:index] if node_id in moving_set)
    rest = [node_id for node_id in contents if node_id not in moving_set]
    at = max(0, min(at, len(rest)))
    fresh: List[NodeId] = []
    if fragment is not None:
        parked = 0
        if layout.items:
            parked = max((item.row or 0) + (item.rowspan or 1) for item in layout.items)
        fresh_ids, _, _, _ = insert_fragment(doc, ctx, InGridCell(layout_id, parked, 0), fragment, False)
        fresh.extend(fresh_ids)
    incoming = moving_ids + fresh
    spliced = rest[:at] + incoming + rest[at:]
    prefix_ok = True
    for position, node_id in enumerate(spliced[:at]):
        row, column = divmod(position, cols)
        carrier = _item_carrier(doc, node_id)
        item = doc.get(carrier) if carrier is not None else None
        if not isinstance(item, LayoutItemNode) or (item.row or 0) != row or (item.column or 0) != column:
            prefix_ok = False
            break
    start_at = at if prefix_ok else 0
    occupied = set()
    for position, node_id in enumerate(spliced):
        row, column = divmod(position, cols)
        occupied.add((row, column))
        if position < start_at:
            continue
        carrier = _carry_into(doc, ctx, node_id, layout_id)
        _set_cell(doc, ctx, carrier, row, column, 1, 1)
    next_pos = len(spliced)
    for item in list(doc.node(layout_id).children("layout_items")):
        if not isinstance(item, LayoutItemNode) or item.content is not None:
            continue
        while True:
            row, column = divmod(next_pos, cols)
            next_pos += 1
            if (row, column) not in occupied:
                break
        occupied.add((row, column))
        _set_cell(doc, ctx, item.id, row, column, 1, 1)
    if incoming:
        ctx.select(tuple(incoming), incoming[0])


def _carry_into(doc: UiDocument, ctx: PlanContext, node_id: NodeId, layout_id: NodeId) -> NodeId:
    carrier = _ensure_item(doc, ctx, node_id, layout_id)
    parent = doc.parent(carrier)
    if parent is None or parent.id != layout_id:
        count = len(doc.node(layout_id).children("layout_items"))
        ctx.do(MoveNodeOp(carrier, layout_id, "layout_items", count))
    return carrier


def _reorder_reading(doc: UiDocument, ctx: PlanContext, layout_id: NodeId) -> None:
    layout = doc.node(layout_id)
    if not isinstance(layout, LayoutNode):
        return
    ordered = sorted(layout.items, key=lambda item: (item.row or 0, item.column or 0, item.slot_index))
    place_nodes(doc, ctx, [item.id for item in ordered], layout_id, "layout_items", 0)


def _clear_cells(doc: UiDocument, ctx: PlanContext, layout_id: NodeId) -> None:
    layout = doc.node(layout_id)
    if not isinstance(layout, LayoutNode):
        return
    for item in layout.items:
        for field_name in ("row", "column", "rowspan", "colspan"):
            if item.field(field_name) is not None:
                ctx.do(SetFieldOp(item.id, field_name, None))


def _apply_named_cells(
    doc: UiDocument,
    ctx: PlanContext,
    layout_id: NodeId,
    cells: Optional[Tuple[Tuple[NodeId, int, int], ...]],
) -> None:
    if not cells:
        return
    for node_id, row, column in cells:
        carrier = _item_carrier(doc, node_id)
        if carrier is None:
            continue
        parent = doc.parent(carrier)
        if parent is not None and parent.id == layout_id:
            _set_cell(doc, ctx, carrier, row, column, 1, 1)


def _drop_properties(
    doc: UiDocument,
    ctx: PlanContext,
    node_id: NodeId,
    class_name: str,
    accepted: Optional[Tuple[str, ...]] = None,
) -> Tuple[str, ...]:
    if accepted is not None:
        known = set(accepted)
    elif ctx.classes.class_info(class_name) is None:
        return ()
    else:
        known = {item.name for item in ctx.classes.properties(class_name)}
    dropped = []
    for entry in list(doc.node(node_id).properties()):
        if entry.stdset == "0" or entry.name in known:
            continue
        ctx.do(SetPropertyOp(node_id, "property", entry.name, None, None))
        dropped.append(entry.name)
    return tuple(dropped)


def _class_holds(ctx: PlanContext, doc: UiDocument, class_name: str) -> Optional[bool]:
    info = ctx.classes.class_info(class_name)
    if info is not None:
        return "container" in info.flags or "page_container" in info.flags
    custom = doc.custom_widget(class_name)
    if custom is None:
        return None
    extends = custom.field("extends")
    if isinstance(extends, str) and ctx.classes.class_info(extends) is not None:
        return _class_holds(ctx, doc, extends)
    if custom.field("container") in (1, "1", True):
        return True
    return None


def _holds_content(node: Node) -> bool:
    if node.children("layout") or node.children("children"):
        return True
    return False


#: Attributes a tab or toolbox page carries for its parent.
_PAGE_ATTRIBUTES = frozenset({"title", "label", "icon", "toolTip", "whatsThis"})


def _accepts_property(
    ctx: PlanContext,
    doc: UiDocument,
    node: Node,
    name: str,
    kind: str,
    stdset: Optional[str] = None,
) -> bool:
    """Whether a multi-select edit applies to ``node``.

    A class that has no such Qt property skips the edit. A custom property
    (``stdset="0"``) goes anywhere, unless the name is a real Qt property of the
    node (or of the base of a promoted widget), which it must not overwrite. A page
    attribute only goes on a page of a tab widget or toolbox."""
    if kind != "property":
        if name in _PAGE_ATTRIBUTES and node.attr(name) is None:
            parent = doc.parent(node.id)
            return isinstance(parent, WidgetNode) and parent.class_name in ("QTabWidget", "QToolBox")
        return True
    existing = node.prop(name)
    class_name = _table_class(ctx, node, doc)
    known = ctx.classes.class_info(class_name) is not None
    if stdset == "0":
        if existing is not None:
            return existing.stdset == "0"
        return not (known and ctx.classes.property_info(class_name, name) is not None)
    if existing is not None:
        return True
    if not known:
        return True
    return ctx.classes.property_info(class_name, name) is not None


def _sync_logic_marker(doc: UiDocument, ctx: PlanContext) -> None:
    """The marker follows the logic properties (CONTRACTS 15.2): added with the first, removed with
    the last. A marker of a newer build, or one that can't be read, is never touched."""
    existing = doc.root.prop("cbcsLogic")
    if marker_read_only(existing):
        return
    if doc.logic_property_count() > 0:
        if existing is None:
            set_property(
                doc,
                ctx,
                doc.root.id,
                "cbcsLogic",
                StringValue(logic_version_text(), notr=True),
                stdset="0",
            )
        return
    if existing is not None:
        set_property(doc, ctx, doc.root.id, "cbcsLogic", None)


def _raise_logic_marker(doc: UiDocument, ctx: PlanContext, version: int) -> None:
    """Make the marker say ``version`` when pasted behavior is newer (UX D20). Never lowers a marker."""
    existing = doc.root.prop("cbcsLogic")
    current = read_marker(existing)
    if existing is not None and (not current.readable or (current.version or 0) >= version):
        return
    set_property(doc, ctx, doc.root.id, "cbcsLogic", StringValue(logic_version_text(version), notr=True), stdset="0")


def _newer_logic_uses(doc: UiDocument, name: str) -> bool:
    """While logic is read-only: does any ``cbcs*`` text or connection mention ``name``?"""
    if not marker_read_only(doc.root.prop("cbcsLogic")):
        return False
    for node in doc.iter_preorder():
        if node.kind == "connection" and name in (node.field("sender"), node.field("receiver")):
            return True
        for entry in node.properties():
            if is_user_logic_key(entry.name) and isinstance(entry.value, StringValue):
                if opaque_mentions(entry.value.text, name):
                    return True
    return False


def _participant_renames(
    ctx: PlanContext,
    doc: UiDocument,
    renames: Tuple[Tuple[str, str], ...],
    scope: Optional[Sequence[NodeId]],
) -> None:
    limit = None if scope is None else frozenset(scope)
    for participant in ctx.participants():
        rename_ops = getattr(participant, "rename_ops", None)
        if rename_ops is None:
            continue
        for op in rename_ops(doc, renames, limit):
            ctx.do(op)


def _merge_declarations(doc: UiDocument, ctx: PlanContext, fragment: Fragment) -> Tuple[str, ...]:
    conflicts = []
    for spec in fragment.customwidgets:
        class_name = spec.field("class_name")
        if not isinstance(class_name, str):
            continue
        existing = doc.custom_widget(class_name)
        if existing is None:
            _insert_spec(doc, ctx, doc.ui.id, "customwidgets", spec)
        elif existing.field("extends") != spec.field("extends"):
            conflicts.append(class_name)
    return tuple(conflicts)


def _merge_one_declaration(doc: UiDocument, ctx: PlanContext, spec: NodeSpec) -> None:
    class_name = spec.field("class_name")
    if isinstance(class_name, str) and doc.custom_widget(class_name) is None:
        _insert_spec(doc, ctx, doc.ui.id, "customwidgets", spec)


def _merge_resources(doc: UiDocument, ctx: PlanContext, fragment: Fragment) -> None:
    locations = {node.field("location") for node in doc.ui.children("resources")}
    for spec in fragment.resources:
        location = spec.field("location")
        if location not in locations:
            _insert_spec(doc, ctx, doc.ui.id, "resources", spec)
            locations.add(location)


def _drop_unused_declarations(doc: UiDocument, ctx: PlanContext) -> None:
    used = set()
    for node in doc.iter_widgets():
        if node.class_name:
            used.add(node.class_name)
    for node in list(doc.ui.children("customwidgets")):
        if node.field("class_name") not in used:
            ctx.do(RemoveNodeOp(node.id))


def _ensure_group(doc: UiDocument, ctx: PlanContext, name: str) -> None:
    for node in doc.ui.children("buttongroups"):
        if node.field("name") == name:
            return
    _check_name(doc, name, base_methods=_base_methods(ctx))
    spec = allocate_spec(ctx, NodeSpec("buttongroup", None, (("name", name),)))
    count = len(doc.ui.children("buttongroups"))
    ctx.do(InsertNodeOp(doc.ui.id, "buttongroups", count, spec))


def _drop_empty_groups(doc: UiDocument, ctx: PlanContext) -> None:
    used = set()
    for node in doc.iter_preorder():
        if node.kind != "widget":
            continue
        attr = node.attr("buttonGroup")
        if attr is None:
            continue
        text = attr.value.text if isinstance(attr.value, (StringValue, CStringValue)) else None
        if text:
            used.add(text)
    for node in list(doc.ui.children("buttongroups")):
        if node.field("name") not in used:
            ctx.do(RemoveNodeOp(node.id))


def _replace_slot(
    doc: UiDocument,
    ctx: PlanContext,
    parent: NodeId,
    slot: str,
    specs: Tuple[NodeSpec, ...],
) -> None:
    for child in list(doc.node(parent).children(slot)):
        ctx.do(RemoveNodeOp(child.id))
    for index, spec in enumerate(specs):
        ctx.do(InsertNodeOp(parent, slot, index, allocate_spec(ctx, _without_ids(spec))))


def _without_ids(spec: NodeSpec) -> NodeSpec:
    slots = tuple((name, tuple(_without_ids(child) for child in kids)) for name, kids in spec.slots)
    return NodeSpec(spec.kind, None, spec.fields, spec.properties, spec.attributes, slots, spec.extra_attrs)


def _insert_spec(doc: UiDocument, ctx: PlanContext, parent: NodeId, slot: str, spec: NodeSpec) -> NodeSpec:
    allocated = allocate_spec(ctx, spec)
    count = len(doc.node(parent).children(slot))
    ctx.do(InsertNodeOp(parent, slot, count, allocated))
    return allocated


def _wrap_for_dest(spec: NodeSpec, dest: _Dest, offset: int) -> NodeSpec:
    if not dest.wrap or spec.kind == "layoutitem":
        return spec
    row = None if dest.row is None else dest.row + offset
    return _item_spec(
        spec,
        row=row,
        column=dest.column,
        rowspan=None if dest.rowspan == 1 else dest.rowspan,
        colspan=None if dest.colspan == 1 else dest.colspan,
    )


def _alloc_layout(doc: UiDocument, ctx: PlanContext, class_name: str) -> NodeSpec:
    name = _take_name(_default_name(class_name), doc, set())
    return allocate_spec(ctx, _layout_spec(class_name, name))


def _alloc_container(
    doc: UiDocument,
    ctx: PlanContext,
    container_class: str,
    layout_class: str,
) -> Tuple[NodeSpec, NodeSpec]:
    chosen: set = set()
    widget_name = _take_name(_default_name(container_class), doc, chosen)
    layout_name = _take_name(_default_name(layout_class), doc, chosen)
    layout = allocate_spec(ctx, _layout_spec(layout_class, layout_name))
    widget = allocate_spec(ctx, _widget_spec(container_class, widget_name, (("layout", (layout,)),)))
    return widget, layout


def _alloc_item_holding(ctx: PlanContext, content: NodeSpec) -> NodeSpec:
    return NodeSpec("layoutitem", ctx.alloc(), (), (), (), (("content", (content,)),))


def _widget_spec(class_name: str, object_name: str, slots: Tuple[Tuple[str, Tuple[NodeSpec, ...]], ...] = ()) -> NodeSpec:
    return NodeSpec(
        "widget",
        None,
        _ordered("widget", {"class_name": class_name, "object_name": object_name}),
        (),
        (),
        slots,
    )


def _layout_spec(class_name: str, object_name: str) -> NodeSpec:
    return NodeSpec(
        "layout",
        None,
        _ordered("layout", {"class_name": class_name, "object_name": object_name}),
    )


def _item_spec(
    content: Optional[NodeSpec],
    row: Optional[int] = None,
    column: Optional[int] = None,
    rowspan: Optional[int] = None,
    colspan: Optional[int] = None,
    alignment: Optional[str] = None,
) -> NodeSpec:
    slots = (("content", (content,)),) if content is not None else ()
    return NodeSpec(
        "layoutitem",
        None,
        _ordered(
            "layoutitem",
            {"row": row, "column": column, "rowspan": rowspan, "colspan": colspan, "alignment": alignment},
        ),
        (),
        (),
        slots,
    )


def _connection_spec(sender: str, signal: str, receiver: str, slot: str) -> NodeSpec:
    return NodeSpec(
        "connection",
        None,
        _ordered(
            "connection",
            {
                "sender": sender,
                "signal": _signature(signal),
                "receiver": receiver,
                "slot": _signature(slot),
            },
        ),
    )


def _ordered(kind: str, values: Dict[str, object]) -> Tuple[Tuple[str, object], ...]:
    found = []
    for spec in SCHEMA[kind].fields:
        value = values.get(spec.name)
        if spec.name in values and value is not None:
            found.append((spec.name, value))
    return tuple(found)


def _assign_names(
    spec: NodeSpec,
    doc: UiDocument,
    chosen: set,
    counts: Dict[str, int],
    mapping: Dict[str, str],
) -> NodeSpec:
    field_name = NAME_FIELD.get(spec.kind)
    fields_out = list(spec.fields)
    if field_name is not None:
        old = spec.field(field_name)
        if isinstance(old, str) and old:
            new = _take_name(old, doc, chosen)
            fields_out = [(key, new if key == field_name else value) for key, value in fields_out]
            if counts.get(old, 0) == 1 and new != old:
                mapping[old] = new
    slots = tuple(
        (slot, tuple(_assign_names(child, doc, chosen, counts, mapping) for child in kids))
        for slot, kids in spec.slots
    )
    return NodeSpec(spec.kind, spec.id, tuple(fields_out), spec.properties, spec.attributes, slots, spec.extra_attrs)


def _name_counts(specs: Sequence[NodeSpec]) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    def walk(spec: NodeSpec) -> None:
        field_name = NAME_FIELD.get(spec.kind)
        if field_name is not None:
            value = spec.field(field_name)
            if isinstance(value, str) and value:
                counts[value] = counts.get(value, 0) + 1
        for _slot, kids in spec.slots:
            for child in kids:
                walk(child)

    for spec in specs:
        walk(spec)
    return counts


def _take_name(base: str, doc: UiDocument, chosen: set) -> str:
    taken: object = doc.names()
    if chosen:
        taken = _ChosenNames(doc.names(), chosen)
    name = next_object_name(base, taken)  # type: ignore[arg-type]
    chosen.add(name)
    return name


class _ChosenNames:
    """Names already on the form plus names picked earlier in this command."""

    def __init__(self, existing: object, chosen: set) -> None:
        self._existing = existing
        self._chosen = chosen

    def __contains__(self, item: object) -> bool:
        return item in self._existing or item in self._chosen  # type: ignore[operator]


def _check_name(
    doc: UiDocument,
    new_name: str,
    current: str = "",
    base_methods: FrozenSet[str] = frozenset(),
) -> None:
    taken = doc.names()
    if current:
        taken = frozenset(name for name in taken if name != current)
    refusal = explain_name(new_name, taken, base_methods, current)
    if refusal is not None:
        raise CommandRejected(refusal.prose, code=refusal.code)


def _base_methods(ctx: PlanContext) -> FrozenSet[str]:
    # Contexts that never saw the window snapshot keep an empty set: today's
    # refusals, and no FB204, until the session installs the logic-design set.
    found = getattr(ctx, "base_methods", None)
    if found is None:
        return frozenset()
    if callable(found):
        found = found()
    return frozenset(found)


def _rank_index(
    ctx: PlanContext,
    node: Node,
    entries: Tuple[PropertyEntry, ...],
    name: str,
    dynamic: bool,
    doc: Optional[UiDocument] = None,
) -> int:
    class_name = _table_class(ctx, node, doc)
    key = ctx.classes.property_rank(class_name, name, dynamic=dynamic)
    for index, entry in enumerate(entries):
        other = ctx.classes.property_rank(class_name, entry.name, dynamic=entry.stdset == "0")
        if key < other:
            return index
    return len(entries)


def _owner_class(node: Node) -> str:
    if node.kind in ("widget", "layout"):
        value = node.field("class_name")
        if isinstance(value, str):
            return value
    if node.kind == "action":
        return "QAction"
    if node.kind == "actiongroup":
        return "QActionGroup"
    return ""


def _table_class(ctx: PlanContext, node: Node, doc: Optional[UiDocument]) -> str:
    """The class whose property sheet applies: a promoted widget uses its base."""
    class_name = _owner_class(node)
    if doc is None or not class_name or ctx.classes.class_info(class_name) is not None:
        return class_name
    custom = doc.custom_widget(class_name)
    extends = custom.field("extends") if custom is not None else None
    if isinstance(extends, str) and ctx.classes.class_info(extends) is not None:
        return extends
    return class_name


def _form_role(role: str) -> Tuple[int, int]:
    if role == "field":
        return 1, 1
    if role == "spanning":
        return 0, 2
    return 0, 1


def _form_rect(item: LayoutItemNode) -> Tuple[int, str]:
    return (item.row or 0, form_item_role(item.column, item.colspan))


def _stacked_cells(row: int, column: int, colspan: int, count: int) -> Set[Tuple[int, str]]:
    cells: Set[Tuple[int, str]] = set()
    for offset in range(count):
        cells |= form_occupied_cells(row + offset, column, colspan)
    return cells


def _require_cell_layout(doc: UiDocument, placement: Union[InGridCell, InFormRow]) -> LayoutNode:
    layout = _require_layout(doc, placement.layout)
    if (layout.class_name == _FORM) != isinstance(placement, InFormRow):
        raise CommandRejected("That layout does not have cells like that.")
    return layout


def _taken_form_cells(doc: UiDocument, layout_id: NodeId, ignore: Sequence[NodeId]) -> Set[Tuple[int, str]]:
    skipped = set(ignore)
    for node_id in list(skipped):
        carrier = _item_carrier(doc, node_id)
        if carrier is not None:
            skipped.add(carrier)
    taken: Set[Tuple[int, str]] = set()
    for item in doc.node(layout_id).children("layout_items"):
        if item.id in skipped or not isinstance(item, LayoutItemNode):
            continue
        taken |= form_occupied_cells(item.row, item.column, item.colspan)
    return taken


def _form_conflict(
    doc: UiDocument,
    layout_id: NodeId,
    cells: Iterable[Tuple[int, str]],
    ignore: Sequence[NodeId],
) -> bool:
    return not _taken_form_cells(doc, layout_id, ignore).isdisjoint(cells)


def _form_has_overlap(doc: UiDocument, layout_id: NodeId) -> bool:
    layout = doc.node(layout_id)
    if not isinstance(layout, LayoutNode):
        return False
    covered: Set[Tuple[int, str]] = set()
    for item in layout.items:
        cells = form_occupied_cells(item.row, item.column, item.colspan)
        if not covered.isdisjoint(cells):
            return True
        covered |= cells
    return False


def _form_row_for_index(doc: UiDocument, layout_id: NodeId, index: int) -> int:
    items = [item for item in doc.node(layout_id).children("layout_items") if isinstance(item, LayoutItemNode)]
    if not items:
        return 0
    if index < 0:
        index = 0
    if index >= len(items):
        return max(item.row or 0 for item in items) + 1
    return items[index].row or 0


def _free_form_slots(
    doc: UiDocument, layout_id: NodeId, count: int, ignore: Sequence[NodeId]
) -> List[Tuple[int, int]]:
    return _free_form_cells(_taken_form_cells(doc, layout_id, ignore), count)


def _free_form_cells(taken: Set[Tuple[int, str]], count: int) -> List[Tuple[int, int]]:
    slots: List[Tuple[int, int]] = []
    row = 0
    while len(slots) < count:
        for column, role in ((0, "label"), (1, "field")):
            if len(slots) < count and (row, role) not in taken:
                slots.append((row, column))
        row += 1
    return slots


def _normalize_form_items(doc: UiDocument, ctx: PlanContext, layout_id: NodeId) -> None:
    layout = doc.node(layout_id)
    if not isinstance(layout, LayoutNode):
        return
    ordered = sorted(layout.items, key=lambda item: (item.row or 0, item.column or 0, item.slot_index))
    claimed: Set[Tuple[int, str]] = set()
    plan: List[Tuple[NodeId, int, int, int]] = []
    displaced: List[NodeId] = []
    for item in ordered:
        row, role = _form_rect(item)
        column, colspan = _form_role(role)
        cells = form_occupied_cells(row, column, colspan)
        if not claimed.isdisjoint(cells):
            displaced.append(item.id)
            continue
        claimed |= cells
        plan.append((item.id, row, column, colspan))
    for item_id, (row, column) in zip(displaced, _free_form_cells(claimed, len(displaced))):
        plan.append((item_id, row, column, 1))
    for item_id, row, column, colspan in plan:
        _set_cell(doc, ctx, item_id, row, column, 1, colspan)


def widgets_in_box_wrap(
    doc: UiDocument, ids: Tuple[NodeId, ...], layout_class: str
) -> Tuple[NodeId, ...]:
    """The widgets a box wrap will contain, including form-row labels it carries."""
    if layout_class not in _BOX:
        return ids
    return _with_form_labels(doc, ids)


def _with_form_labels(doc: UiDocument, ids: Tuple[NodeId, ...]) -> Tuple[NodeId, ...]:
    """Two or more form fields keep the first row's label and carry the later ones.

    Reading order is row, then column. The first label stays in the label
    column. Each later label is placed just before its field. A mix of
    fields and other roles is left as the user selected it.
    """
    found: List[Tuple[int, int, NodeId, Optional[NodeId]]] = []
    parent_id: Optional[NodeId] = None
    for node_id in ids:
        item = doc.parent(node_id)
        if not isinstance(item, LayoutItemNode):
            return ids
        parent = doc.parent(item.id)
        if not isinstance(parent, LayoutNode) or parent.class_name != _FORM:
            return ids
        if form_item_role(item.column, item.colspan) != "field":
            return ids
        if parent_id is None:
            parent_id = parent.id
        elif parent.id != parent_id:
            return ids
        label_content: Optional[NodeId] = None
        for label_id, field_id, _spanning in form_rows(doc, parent.id):
            if field_id != item.id or label_id is None:
                continue
            label_item = doc.node(label_id)
            content = label_item.content if isinstance(label_item, LayoutItemNode) else None
            if content is not None:
                label_content = content.id
        found.append((item.row or 0, item.column or 0, node_id, label_content))
    if len({row for row, _column, _field, _label in found}) < 2:
        return ids
    found.sort()
    ordered: List[NodeId] = [found[0][2]]
    moved = False
    for _row, _column, field_id, label_id in found[1:]:
        if label_id is not None and label_id not in ordered:
            ordered.append(label_id)
            moved = True
        if field_id not in ordered:
            ordered.append(field_id)
    if not moved:
        return ids
    return tuple(ordered)


def _clear_box_cells(doc: UiDocument, ctx: PlanContext, layout_id: NodeId, layout_class: str) -> None:
    """A box item is a sequence. It never keeps a grid or form cell."""
    if layout_class not in _BOX:
        return
    _clear_cells(doc, ctx, layout_id)


def _place_wrapped_form_row(
    doc: UiDocument,
    ctx: PlanContext,
    layout_id: NodeId,
    item_id: NodeId,
    anchor: Tuple[int, str],
    layout_class: str,
) -> None:
    row, role = anchor
    if layout_class in _BOX:
        # The first label keeps column 0. The box sits in the field cell.
        column = 1 if role == "field" else 0
        _set_cell(doc, ctx, item_id, row, column, 1, 1)
    else:
        _place_form_anchor(doc, ctx, layout_id, item_id, anchor)
    _compact_form_rows(doc, ctx, layout_id)


def _form_anchor(
    doc: UiDocument, parent: Node, carriers: Sequence[NodeId]
) -> Optional[Tuple[int, str]]:
    if not isinstance(parent, LayoutNode) or parent.class_name != _FORM or not carriers:
        return None
    first_id = min(carriers, key=lambda carrier: _cell_key(doc, carrier))
    first = doc.node(first_id)
    if not isinstance(first, LayoutItemNode):
        return None
    return _form_rect(first)


def _compact_form_rows(doc: UiDocument, ctx: PlanContext, layout_id: NodeId) -> None:
    """Renumber form rows so a wrap does not leave 0, 2, 3."""
    layout = doc.node(layout_id)
    if not isinstance(layout, LayoutNode):
        return
    used = sorted({item.row or 0 for item in layout.items})
    mapping = {old: new for new, old in enumerate(used)}
    for item in list(layout.items):
        old = item.row or 0
        new = mapping[old]
        if new == old:
            continue
        _set_cell(doc, ctx, item.id, new, item.column or 0, item.rowspan or 1, item.colspan or 1)


def _cell_key(doc: UiDocument, node_id: NodeId) -> Tuple[int, int, int]:
    node = doc.get(node_id)
    item = node if isinstance(node, LayoutItemNode) else None
    if item is None:
        parent = doc.parent(node_id)
        item = parent if isinstance(parent, LayoutItemNode) else None
    if isinstance(item, LayoutItemNode):
        return (item.row or 0, item.column or 0, item.slot_index)
    slot = node.slot_index if node is not None else 0
    return (1 << 20, 1 << 20, slot)


def _sort_by_cell(doc: UiDocument, ids: Sequence[NodeId]) -> List[NodeId]:
    """Reading order for a form or a grid: row, then column (UX-WRAP-004)."""
    unique: List[NodeId] = []
    for node_id in ids:
        if node_id not in unique:
            unique.append(node_id)
    unique.sort(key=lambda node_id: _cell_key(doc, node_id))
    return unique


def _place_form_anchor(
    doc: UiDocument,
    ctx: PlanContext,
    layout_id: NodeId,
    item_id: NodeId,
    anchor: Tuple[int, str],
) -> None:
    row, role = anchor
    column, colspan = _form_role(role)
    if not _form_conflict(doc, layout_id, form_occupied_cells(row, column, colspan), (item_id,)):
        _set_cell(doc, ctx, item_id, row, column, 1, colspan)
        return
    row, column = _free_form_slots(doc, layout_id, 1, (item_id,))[0]
    _set_cell(doc, ctx, item_id, row, column, 1, 1)


def _finish_form_layout(doc: UiDocument, ctx: PlanContext, layout_id: NodeId, cells_given: bool) -> None:
    layout = doc.node(layout_id)
    if not isinstance(layout, LayoutNode) or layout.class_name != _FORM:
        return
    if cells_given:
        if _form_has_overlap(doc, layout_id):
            raise CommandRejected("That cell is already occupied.")
        return
    _normalize_form_items(doc, ctx, layout_id)


def _reseat_form_items(
    doc: UiDocument, ctx: PlanContext, layout_id: NodeId, item_ids: Sequence[NodeId]
) -> None:
    layout = doc.node(layout_id)
    if not isinstance(layout, LayoutNode) or layout.class_name != _FORM or not item_ids:
        return
    wanted: Set[Tuple[int, str]] = set()
    shared = False
    for item_id in item_ids:
        node = doc.node(item_id)
        if isinstance(node, LayoutItemNode):
            cells = form_occupied_cells(node.row, node.column, node.colspan)
            shared = shared or not wanted.isdisjoint(cells)
            wanted |= cells
    if not shared and not _form_conflict(doc, layout_id, wanted, item_ids):
        return
    slots = _free_form_slots(doc, layout_id, len(item_ids), item_ids)
    for item_id, (row, column) in zip(item_ids, slots):
        _set_cell(doc, ctx, item_id, row, column, 1, 1)


def _move_box_into_form(
    doc: UiDocument, ctx: PlanContext, ids: Sequence[NodeId], placement: InBoxLayout
) -> None:
    fresh = []
    for node_id in ids:
        carrier = _item_carrier(doc, node_id)
        parent = doc.parent(carrier) if carrier is not None else None
        if parent is None or parent.id != placement.layout:
            fresh.append(node_id)
    start = _form_row_for_index(doc, placement.layout, placement.index) if fresh else 0
    carriers = [_ensure_item(doc, ctx, node_id, placement.layout) for node_id in ids]
    _reject_into_self(doc, carriers, placement.layout)
    fresh_set = set(fresh)
    newcomers = [carrier for node_id, carrier in zip(ids, carriers) if node_id in fresh_set]
    if newcomers:
        _shift_axis(doc, ctx, placement.layout, "row", start, newcomers, delta=len(newcomers))
        if _form_conflict(doc, placement.layout, _stacked_cells(start, 0, 1, len(newcomers)), newcomers):
            raise CommandRejected("That cell is already occupied.")
    place_nodes(doc, ctx, carriers, placement.layout, "layout_items", placement.index)
    for offset, carrier in enumerate(newcomers):
        _set_cell(doc, ctx, carrier, start + offset, 0, 1, 1)


def _reject_overlap(
    doc: UiDocument,
    layout_id: NodeId,
    carriers: Sequence[NodeId],
    row: int,
    column: int,
    rowspan: int,
    colspan: int,
) -> None:
    ignore = set(carriers)
    for item in doc.node(layout_id).children("layout_items"):
        if item.id in ignore or not isinstance(item, LayoutItemNode):
            continue
        if _rects_overlap(item.row or 0, item.column or 0, item.rowspan or 1, item.colspan or 1, row, column, rowspan, colspan):
            raise CommandRejected("That cell is already occupied.")


def _would_overlap(layout: LayoutNode, item_id: NodeId, proposed: Dict[str, object]) -> bool:
    row = _or_zero(proposed.get("row"))
    column = _or_zero(proposed.get("column"))
    rowspan = _or_one(proposed.get("rowspan"))
    colspan = _or_one(proposed.get("colspan"))
    for item in layout.items:
        if item.id == item_id:
            continue
        if _rects_overlap(item.row or 0, item.column or 0, item.rowspan or 1, item.colspan or 1, row, column, rowspan, colspan):
            return True
    return False


def _rects_overlap(
    row: int,
    column: int,
    rowspan: int,
    colspan: int,
    other_row: int,
    other_column: int,
    other_rowspan: int,
    other_colspan: int,
) -> bool:
    return not (
        row + rowspan <= other_row
        or other_row + other_rowspan <= row
        or column + colspan <= other_column
        or other_column + other_colspan <= column
    )


def _or_zero(value: object) -> int:
    return 0 if value is None else int(value)  # type: ignore[arg-type]


def _or_one(value: object) -> int:
    return 1 if value is None else int(value)  # type: ignore[arg-type]


def _survivor(
    doc: UiDocument,
    siblings: Sequence[Node],
    index: int,
    removed: set,
    parent: Optional[Node],
) -> Tuple[NodeId, ...]:
    for delta in range(1, len(siblings) + 1):
        for pos in (index - delta, index + delta):
            if pos < 0 or pos >= len(siblings):
                continue
            cand = siblings[pos]
            if cand.id in removed or any(doc.is_ancestor(gone, cand.id) for gone in removed):
                continue
            chosen = _selectable(cand)
            if chosen not in removed:
                return (chosen,)
    if isinstance(parent, LayoutItemNode):
        neighbor = _neighbor_cell(doc, parent, removed)
        if neighbor is not None:
            return (neighbor,)
    if parent is not None and parent.id not in removed and not isinstance(parent, LayoutItemNode):
        return (parent.id,)
    if parent is not None and isinstance(parent, LayoutItemNode):
        layout = doc.parent(parent.id)
        if layout is not None and layout.id not in removed:
            return (layout.id,)
    return (doc.root.id,)


def _neighbor_cell(doc: UiDocument, item: LayoutItemNode, removed: set) -> Optional[NodeId]:
    layout = doc.parent(item.id)
    if not isinstance(layout, LayoutNode):
        return None
    ordered = sorted(layout.items, key=lambda entry: (entry.row or 0, entry.column or 0, entry.slot_index))
    position = 0
    for index, entry in enumerate(ordered):
        if entry.id == item.id:
            position = index
            break
    for entry in ordered[position + 1 :]:
        content = entry.content
        if content is not None and content.id not in removed:
            return content.id
    for entry in reversed(ordered[:position]):
        content = entry.content
        if content is not None and content.id not in removed:
            return content.id
    return None


def _selectable(node: Node) -> NodeId:
    if isinstance(node, LayoutItemNode) and node.content is not None:
        return node.content.id
    return node.id


def _content_id(doc: UiDocument, item_id: NodeId) -> NodeId:
    node = doc.get(item_id)
    if isinstance(node, LayoutItemNode) and node.content is not None:
        return node.content.id
    return item_id


def _content_spec_id(spec: NodeSpec) -> NodeId:
    if spec.kind == "layoutitem":
        content = spec.children("content")
        if content and content[0].id is not None:
            return content[0].id
    if spec.id is None:
        raise CommandRejected("The inserted object has no id.")
    return spec.id


def _number_prop(node: Node, name: str) -> Optional[int]:
    entry = node.prop(name)
    if entry is None or not isinstance(entry.value, NumberValue):
        return None
    return entry.value.value


def _signature(text: str) -> str:
    if "(" in text:
        return text
    return text + "()"


def _default_name(class_name: str) -> str:
    if class_name == "QVBoxLayout":
        return "verticalLayout"
    if class_name == "QHBoxLayout":
        return "horizontalLayout"
    text = class_name[1:] if class_name.startswith("Q") and len(class_name) > 1 else class_name
    if not text:
        return "widget"
    return text[:1].lower() + text[1:]


def _reject_into_self(doc: UiDocument, ids: Sequence[NodeId], parent: NodeId) -> None:
    for node_id in ids:
        if node_id == parent or doc.is_ancestor(node_id, parent):
            raise CommandRejected("An object cannot be moved into itself.")


def _sort_ids(doc: UiDocument, ids: Sequence[NodeId]) -> List[NodeId]:
    unique: List[NodeId] = []
    for node_id in ids:
        if node_id not in unique:
            unique.append(node_id)

    def order(left: NodeId, right: NodeId) -> int:
        if left == right:
            return 0
        if doc._comes_before(left, right):  # noqa: SLF001 — document order is O(depth)
            return -1
        return 1

    unique.sort(key=cmp_to_key(order))
    return unique


def _require(doc: UiDocument, node_id: NodeId) -> Node:
    node = doc.get(node_id)
    if node is None:
        raise CommandRejected("That object is no longer in the form.")
    return node


def _require_layout(doc: UiDocument, node_id: NodeId) -> LayoutNode:
    node = _require(doc, node_id)
    if not isinstance(node, LayoutNode):
        raise CommandRejected("That object is not a layout.")
    return node


def _ensure(value: object) -> None:
    if value is None or isinstance(value, (int, float, bool)):
        return
    if isinstance(value, str):
        try:
            require_xml_text(value)
        except ValueError as exc:
            raise CommandRejected(str(exc)) from exc
        return
    if isinstance(value, tuple):
        for item in value:
            _ensure(item)
        return
    if is_dataclass(value) and not isinstance(value, type):
        for item in fields(value):
            _ensure(getattr(value, item.name))
