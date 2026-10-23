"""Turn catalog commands into primitive ops.

This module does not import ``mutate``. It only calls ``ctx.do``.
"""

from __future__ import annotations

import keyword
from dataclasses import fields, is_dataclass
from functools import cmp_to_key
from typing import Dict, List, Optional, Sequence, Tuple

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
    FORMULA_NAMES,
    NAME_FIELD,
    RESERVED_NAMES,
    identity_name,
    native_delete_ops,
    native_rename_ops,
    rewrite_spec_refs,
)
from app.features.form_builder.engine.ids import IdAllocator, NodeId
from app.features.form_builder.engine.logic.storage import (
    CBCS_LAYOUT_KEYS,
    SUPPORTED_LOGIC_VERSION,
    is_logic_key,
    logic_version_text,
)
from app.features.form_builder.engine.query.tree import is_page_container
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, Node, WidgetNode
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui
from app.features.form_builder.engine.ui4.schema import SCHEMA, SlotsDecl
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import (
    BoolValue,
    CStringValue,
    EnumValue,
    NumberValue,
    RectValue,
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
) -> Tuple[Tuple[NodeId, ...], Tuple[Tuple[str, str], ...], Tuple[str, ...]]:
    dest = _destination(doc, ctx, placement, auto_layout, moving=(), incoming=len(fragment.nodes))
    chosen: set = set()
    counts = _name_counts(fragment.nodes)
    mapping: Dict[str, str] = {}
    prepared = tuple(_assign_names(spec, doc, chosen, counts, mapping) for spec in fragment.nodes)
    prepared = tuple(rewrite_spec_refs(spec, mapping) for spec in prepared)
    conflicts = _merge_declarations(doc, ctx, fragment)
    _merge_resources(doc, ctx, fragment)
    top_ids: List[NodeId] = []
    scope: List[NodeId] = []
    for offset, spec in enumerate(prepared):
        spec = _wrap_for_dest(spec, dest, offset)
        allocated = allocate_spec(ctx, spec)
        ctx.do(InsertNodeOp(dest.parent, dest.slot, dest.index + offset, allocated))
        if dest.geometry is not None:
            target = _content_spec_id(allocated)
            set_property(doc, ctx, target, "geometry", dest.geometry)
        top_ids.append(_content_spec_id(allocated))
        scope.extend(allocated.ids())
    alive = doc.names()
    for spec in fragment.connections:
        rewritten = rewrite_spec_refs(spec, mapping)
        sender = rewritten.field("sender")
        receiver = rewritten.field("receiver")
        if sender in alive and receiver in alive:
            allocated = allocate_spec(ctx, rewritten)
            count = len(doc.ui.children("connections"))
            ctx.do(InsertNodeOp(doc.ui.id, "connections", count, allocated))
            scope.extend(allocated.ids())
    renames = tuple(mapping.items())
    if renames:
        _participant_renames(ctx, doc, renames, scope)
    ctx.select(tuple(top_ids))
    return tuple(top_ids), renames, conflicts


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
    anchor = _form_anchor(doc, parent, carriers)
    first = min(doc.node(carrier).slot_index for carrier in carriers)
    if container_class is None:
        if parent.kind != "layout":
            raise CommandRejected("A layout-only wrap needs a parent layout.")
        layout = _alloc_layout(doc, ctx, layout_class)
        item = _alloc_item_holding(ctx, layout)
        ctx.do(InsertNodeOp(parent_id, slot, first, item))
        place_nodes(doc, ctx, carriers, layout.id, "layout_items", 0)  # type: ignore[arg-type]
        _apply_named_cells(doc, ctx, layout.id, cells)  # type: ignore[arg-type]
        _finish_form_layout(doc, ctx, layout.id, bool(cells))  # type: ignore[arg-type]
        if anchor is not None:
            _place_form_anchor(doc, ctx, parent_id, item.id, anchor)  # type: ignore[arg-type]
        ctx.select((layout.id,))  # type: ignore[arg-type]
        return layout.id  # type: ignore[return-value]
    widget, layout = _alloc_container(doc, ctx, container_class, layout_class)
    held: Optional[NodeSpec] = None
    if parent.kind == "layout":
        held = _alloc_item_holding(ctx, widget)
        ctx.do(InsertNodeOp(parent_id, slot, first, held))
    else:
        ctx.do(InsertNodeOp(parent_id, slot, first, widget))
    place_nodes(doc, ctx, carriers, layout.id, "layout_items", 0)  # type: ignore[arg-type]
    _apply_named_cells(doc, ctx, layout.id, cells)  # type: ignore[arg-type]
    _finish_form_layout(doc, ctx, layout.id, bool(cells))  # type: ignore[arg-type]
    if anchor is not None and held is not None:
        _place_form_anchor(doc, ctx, parent_id, held.id, anchor)  # type: ignore[arg-type]
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
    pair_cells = layout_class == _FORM and not cell_map
    for index, child_id in enumerate(child_ids):
        _require(doc, child_id)
        row = column = None
        rowspan = colspan = 1
        if child_id in cell_map:
            row, column, rowspan, colspan = cell_map[child_id]
        elif pair_cells:
            row, column = divmod(index, 2)
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
    if layout_class == _FORM and _form_has_overlap(doc, layout.id):  # type: ignore[arg-type]
        raise CommandRejected("That cell is already occupied.")
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
        _assign_form_pairs(doc, ctx, layout_id)
    elif old in (_GRID, _FORM) and new_class in _BOX:
        _reorder_reading(doc, ctx, layout_id)
        _clear_cells(doc, ctx, layout_id)
    ctx.select((layout_id,))


def morph_widget(doc: UiDocument, ctx: PlanContext, node_id: NodeId, new_class: str) -> Tuple[str, ...]:
    node = _require(doc, node_id)
    if node.kind != "widget":
        raise CommandRejected("That object is not a widget.")
    if node.field("class_name") == new_class:
        return ()
    if _holds_content(node) and _class_holds(ctx, doc, new_class) is False:
        raise CommandRejected("The new class cannot hold the contents of this widget.")
    set_field(doc, ctx, node_id, "class_name", new_class)
    return _drop_properties(doc, ctx, node_id, new_class)


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
    index = _rank_index(ctx, node, entries, name, new_stdset == "0")
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
        if not _accepts_property(ctx, node, name, kind):
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
    _check_name(doc, new_name)
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
    if isinstance(parent, LayoutNode) and parent.class_name in (_GRID, _FORM) and _would_overlap(parent, item, proposed):
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
    current = _number_prop(widget, "currentIndex")
    order = list(range(len(pages)))
    moved = order.pop(from_index)
    order.insert(to_index, moved)
    if page.slot_index != to_index:
        ctx.do(MoveNodeOp(page.id, container, "children", to_index))
    if current is not None and 0 <= current < len(order):
        new_current = order.index(current)
        if new_current != current:
            set_property(doc, ctx, container, "currentIndex", NumberValue(new_current))
    ctx.select((page.id,))


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
        _replace_slot(doc, ctx, widget, "items", items)
    if rows is not None:
        _replace_slot(doc, ctx, widget, "rows", rows)
    if columns is not None:
        _replace_slot(doc, ctx, widget, "columns", columns)


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


def set_form_field(doc: UiDocument, ctx: PlanContext, field: str, value: object) -> None:
    if field == "includes":
        specs = value if isinstance(value, tuple) else ()
        _replace_slot(doc, ctx, doc.ui.id, "includes", specs)
        return
    set_field(doc, ctx, doc.ui.id, field, value)


def replace_document_text(doc: UiDocument, ctx: PlanContext, text: str) -> None:
    """Parse ``text`` with ids from ``ctx`` and replace the document."""

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
    ctx.do(ReplaceRootOp(loaded.document.to_spec()))
    matched = []
    for name in names:
        found = doc.by_name(name)
        if found:
            matched.append(found[0])
    if matched:
        ctx.select(tuple(matched), matched[0])
    else:
        ctx.select((doc.root.id,), doc.root.id)


def set_logic(doc: UiDocument, ctx: PlanContext, owner: NodeId, key: str, text: Optional[str]) -> None:
    if key in CBCS_LAYOUT_KEYS or key == "cbcsLogic" or not is_logic_key(key):
        raise CommandRejected("That key is not a logic property.")
    version = doc.logic_version()
    if version is not None and version > SUPPORTED_LOGIC_VERSION:
        raise CommandRejected("This form's logic is from a newer version.", code="FB402")
    _require(doc, owner)
    if text is None:
        set_property(doc, ctx, owner, key, None, stdset="0")
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
) -> None:
    """Put ``ids`` in document order at ``start_index`` of the list the user saw."""
    if not ids:
        return
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
            rects = [(start + offset, 0, 1, 1) for offset in range(incoming)]
            if _form_conflict(doc, placement.layout, rects, moving):
                raise CommandRejected("That cell is already occupied.")
            return _Dest(placement.layout, "layout_items", placement.index, True, row=start, column=0)
        return _Dest(placement.layout, "layout_items", placement.index, True)
    if isinstance(placement, InGridCell):
        _require_layout(doc, placement.layout)
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
        _require_layout(doc, placement.layout)
        column, colspan = _form_role(placement.role)
        rects = [(placement.row + offset, column, 1, colspan) for offset in range(incoming)]
        if placement.insert_row and incoming:
            _shift_axis(doc, ctx, placement.layout, "row", placement.row, moving, delta=incoming)
        if incoming and _form_conflict(doc, placement.layout, rects, moving):
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
        layout_id = placement.layout
        row, column, rowspan, colspan = placement.row, placement.column, placement.rowspan, placement.colspan
        _shift_for_mode(doc, ctx, placement, ids)
    elif isinstance(placement, InFormRow):
        layout_id = placement.layout
        column, colspan = _form_role(placement.role)
        row, rowspan = placement.row, 1
        rects = [(row + offset, column, 1, colspan) for offset in range(len(ids))]
        if placement.insert_row:
            _shift_axis(doc, ctx, layout_id, "row", row, ids, delta=len(ids))
        if _form_conflict(doc, layout_id, rects, ids):
            raise CommandRejected("That cell is already occupied.")
    else:
        return
    _require_layout(doc, layout_id)
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
    if placement.area and placement.part in ("toolbar", "dock"):
        prop = "toolBarArea" if placement.part == "toolbar" else "dockWidgetArea"
        for node_id in ids:
            set_property(doc, ctx, node_id, prop, EnumValue(placement.area))
    if placement.break_before:
        for node_id in ids:
            set_property(doc, ctx, node_id, "toolBarBreak", BoolValue(True))


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
    for item in list(doc.node(layout_id).children("layout_items")):
        if item.id in ignore or not isinstance(item, LayoutItemNode):
            continue
        current = item.row if field == "row" else item.column
        current = 0 if current is None else current
        if current >= start:
            ctx.do(SetFieldOp(item.id, field, current + delta))


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


def _drop_properties(doc: UiDocument, ctx: PlanContext, node_id: NodeId, class_name: str) -> Tuple[str, ...]:
    if ctx.classes.class_info(class_name) is None:
        return ()
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


def _accepts_property(ctx: PlanContext, node: Node, name: str, kind: str) -> bool:
    existing = node.prop(name) if kind == "property" else node.attr(name)
    if existing is not None:
        return True
    class_name = _owner_class(node)
    if ctx.classes.class_info(class_name) is None:
        return True
    return ctx.classes.property_info(class_name, name) is not None


def _sync_logic_marker(doc: UiDocument, ctx: PlanContext) -> None:
    existing = doc.root.prop("cbcsLogic")
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
    _check_name(doc, name)
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
        ctx.do(InsertNodeOp(parent, slot, index, allocate_spec(ctx, spec)))


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
    if base not in chosen and base not in doc.names():
        chosen.add(base)
        return base
    suffix = 2
    while True:
        candidate = "%s_%s" % (base, suffix)
        if candidate not in chosen and candidate not in doc.names():
            chosen.add(candidate)
            return candidate
        suffix += 1


def _check_name(doc: UiDocument, new_name: str) -> None:
    if new_name.startswith("cbcs") or new_name in RESERVED_NAMES or new_name in FORMULA_NAMES:
        raise CommandRejected("That name is reserved.", code="FB106")
    if not new_name.isidentifier() or keyword.iskeyword(new_name):
        raise CommandRejected("That name is not a Python identifier.", code="FB011")
    if new_name in doc.names():
        raise CommandRejected("That name is already used.", code="FB010")


def _rank_index(ctx: PlanContext, node: Node, entries: Tuple[PropertyEntry, ...], name: str, dynamic: bool) -> int:
    class_name = _owner_class(node)
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
    return ""


def _form_role(role: str) -> Tuple[int, int]:
    if role == "field":
        return 1, 1
    if role == "spanning":
        return 0, 2
    return 0, 1


def _form_rect(item: LayoutItemNode) -> Tuple[int, int, int, int]:
    return (item.row or 0, item.column or 0, item.rowspan or 1, item.colspan or 1)


def _form_conflict(
    doc: UiDocument,
    layout_id: NodeId,
    rects: Sequence[Tuple[int, int, int, int]],
    ignore: Sequence[NodeId],
) -> bool:
    skipped = set(ignore)
    for node_id in list(skipped):
        carrier = _item_carrier(doc, node_id)
        if carrier is not None:
            skipped.add(carrier)
    for item in doc.node(layout_id).children("layout_items"):
        if item.id in skipped or not isinstance(item, LayoutItemNode):
            continue
        existing = _form_rect(item)
        for rect in rects:
            if _rects_overlap(*existing, *rect):
                return True
    return False


def _form_has_overlap(doc: UiDocument, layout_id: NodeId) -> bool:
    layout = doc.node(layout_id)
    if not isinstance(layout, LayoutNode):
        return False
    covered = set()
    for item in layout.items:
        row, column, rowspan, colspan = _form_rect(item)
        for r in range(row, row + rowspan):
            for c in range(column, column + colspan):
                if (r, c) in covered:
                    return True
                covered.add((r, c))
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
    skipped = set(ignore)
    occupied = set()
    for item in doc.node(layout_id).children("layout_items"):
        if item.id in skipped or not isinstance(item, LayoutItemNode):
            continue
        row, column, rowspan, colspan = _form_rect(item)
        for r in range(row, row + rowspan):
            for c in range(column, column + colspan):
                occupied.add((r, c))
    slots: List[Tuple[int, int]] = []
    row = 0
    while len(slots) < count:
        if (row, 0) not in occupied:
            slots.append((row, 0))
            occupied.add((row, 0))
        if len(slots) >= count:
            break
        if (row, 1) not in occupied:
            slots.append((row, 1))
            occupied.add((row, 1))
        row += 1
    return slots


def _assign_form_pairs(doc: UiDocument, ctx: PlanContext, layout_id: NodeId) -> None:
    layout = doc.node(layout_id)
    if not isinstance(layout, LayoutNode):
        return
    ordered = sorted(layout.items, key=lambda item: (item.row or 0, item.column or 0, item.slot_index))
    for index, item in enumerate(ordered):
        row, column = divmod(index, 2)
        _set_cell(doc, ctx, item.id, row, column, 1, 1)


def _form_anchor(
    doc: UiDocument, parent: Node, carriers: Sequence[NodeId]
) -> Optional[Tuple[int, int, int, int]]:
    if not isinstance(parent, LayoutNode) or parent.class_name != _FORM or not carriers:
        return None
    first_id = min(carriers, key=lambda carrier: doc.node(carrier).slot_index)
    first = doc.node(first_id)
    if not isinstance(first, LayoutItemNode):
        return None
    return _form_rect(first)


def _place_form_anchor(
    doc: UiDocument,
    ctx: PlanContext,
    layout_id: NodeId,
    item_id: NodeId,
    anchor: Tuple[int, int, int, int],
) -> None:
    if not _form_conflict(doc, layout_id, (anchor,), (item_id,)):
        _set_cell(doc, ctx, item_id, anchor[0], anchor[1], anchor[2], anchor[3])
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
    _assign_form_pairs(doc, ctx, layout_id)


def _reseat_form_items(
    doc: UiDocument, ctx: PlanContext, layout_id: NodeId, item_ids: Sequence[NodeId]
) -> None:
    layout = doc.node(layout_id)
    if not isinstance(layout, LayoutNode) or layout.class_name != _FORM or not item_ids:
        return
    rects = []
    for item_id in item_ids:
        node = doc.node(item_id)
        if isinstance(node, LayoutItemNode):
            rects.append(_form_rect(node))
    shared = False
    for index, left in enumerate(rects):
        for right in rects[index + 1 :]:
            if _rects_overlap(*left, *right):
                shared = True
                break
        if shared:
            break
    if not shared and not _form_conflict(doc, layout_id, rects, item_ids):
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
        rects = [(start + offset, 0, 1, 1) for offset in range(len(newcomers))]
        if _form_conflict(doc, placement.layout, rects, newcomers):
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
    if parent is not None and parent.id not in removed:
        return (parent.id,)
    return (doc.root.id,)


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
