"""Wraps whose host is not a container with a layout, or whose siblings are free.

Each one selects the new host inside ``apply`` so redo restores the same
selection. Splitters and tab widgets never carry a layout element; a tab
gets one page and the layout lives on that page.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, List, Optional, Tuple

from app.features.form_builder.engine.commands import planning
from app.features.form_builder.engine.commands.base import CommandRejected, PlanContext
from app.features.form_builder.engine.commands.catalog import _CommandBase
from app.features.form_builder.engine.commands.ops import MoveNodeOp
from app.features.form_builder.engine.commands.placement import InContainer
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.tree import is_page_container
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, Node, WidgetNode
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import EnumValue, RectValue, StringValue


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if add is None:
        return
    add(WrapSplitter)
    add(WrapTab)
    add(WrapFree)


@dataclass(frozen=True)
class WrapSplitter(_CommandBase):
    """Put sibling widgets in a new splitter. ``geometry`` places it when they are free."""

    command_type: ClassVar[str] = "wrap_splitter"
    _label_text: ClassVar[str] = "Wrap"
    ids: Tuple[NodeId, ...]
    orientation: str
    geometry: Optional[RectValue] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> NodeId:
        holder, ordered = _siblings(doc, self.ids)
        if isinstance(holder, LayoutNode):
            splitter = planning.wrap_nodes(doc, ctx, ordered, "QSplitter", "QVBoxLayout", None)
            planning.break_layout(doc, ctx, _layout_id(doc, splitter), ())
        else:
            splitter = _insert_host(doc, ctx, holder, ordered, "QSplitter", self.geometry)
            planning.move_nodes(doc, ctx, ordered, InContainer(splitter, 0))
            _clear_geometry(doc, ctx, ordered)
        planning.set_property(doc, ctx, splitter, "orientation", EnumValue(self.orientation))
        ctx.select((splitter,))
        return splitter


@dataclass(frozen=True)
class WrapTab(_CommandBase):
    """Put sibling widgets on the first page of a new tab widget."""

    command_type: ClassVar[str] = "wrap_tab"
    _label_text: ClassVar[str] = "Wrap"
    ids: Tuple[NodeId, ...]
    title: str = "Tab 1"
    geometry: Optional[RectValue] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> NodeId:
        holder, ordered = _siblings(doc, self.ids)
        if isinstance(holder, LayoutNode):
            tabs = planning.wrap_nodes(doc, ctx, ordered, "QTabWidget", "QVBoxLayout", None)
            layout_id = _layout_id(doc, tabs)
            page = _insert_page(doc, ctx, tabs, self.title)
            ctx.do(MoveNodeOp(layout_id, page, "layout", 0))
        else:
            tabs = _insert_host(doc, ctx, holder, ordered, "QTabWidget", self.geometry)
            page = _insert_page(doc, ctx, tabs, self.title)
            planning.move_nodes(doc, ctx, ordered, InContainer(page, 0))
            planning.apply_layout_command(doc, ctx, page, "QVBoxLayout", ordered, None)
        ctx.select((tabs,))
        return tabs


@dataclass(frozen=True)
class WrapFree(_CommandBase):
    """Put free sibling widgets in a new container at ``geometry`` and lay them out.

    ``order`` and ``cells`` follow ``ApplyLayout``.
    """

    command_type: ClassVar[str] = "wrap_free"
    _label_text: ClassVar[str] = "Wrap"
    ids: Tuple[NodeId, ...]
    container_class: str
    layout_class: str
    geometry: RectValue
    order: Tuple[NodeId, ...] = ()
    cells: Optional[Tuple[Tuple[NodeId, int, int, int, int], ...]] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> NodeId:
        holder, ordered = _siblings(doc, self.ids)
        if isinstance(holder, LayoutNode):
            raise CommandRejected("Those widgets are already in a layout.")
        host = _insert_host(doc, ctx, holder, ordered, self.container_class, self.geometry)
        planning.move_nodes(doc, ctx, ordered, InContainer(host, 0))
        planning.apply_layout_command(doc, ctx, host, self.layout_class, self.order or ordered, self.cells)
        ctx.select((host,))
        return host


def _siblings(doc: UiDocument, ids: Tuple[NodeId, ...]) -> Tuple[Node, Tuple[NodeId, ...]]:
    """The shared holder (a layout or a widget) and the ids in their current order."""
    if not ids:
        raise CommandRejected("There is nothing to wrap.")
    holders = set()
    placed: List[Tuple[int, NodeId]] = []
    for node_id in ids:
        if not doc.contains(node_id):
            raise CommandRejected("That object is no longer in the form.")
        node = doc.node(node_id)
        if not isinstance(node, WidgetNode) or node.id == doc.root.id:
            raise CommandRejected("Only widgets can be wrapped.")
        parent = doc.parent(node_id)
        carrier = parent if isinstance(parent, LayoutItemNode) else node
        holder = doc.parent(carrier.id)
        if holder is None or carrier.parent_slot not in ("layout_items", "children"):
            raise CommandRejected("Those widgets cannot be wrapped.")
        holders.add(holder.id)
        placed.append((carrier.slot_index, node_id))
    if len(holders) != 1:
        raise CommandRejected("Wrap only works on siblings.")
    holder = doc.node(next(iter(holders)))
    if is_page_container(doc, holder.id):
        raise CommandRejected("Pages cannot be wrapped.")
    return holder, tuple(node_id for _index, node_id in sorted(placed))


def _insert_host(
    doc: UiDocument,
    ctx: PlanContext,
    holder: Node,
    ordered: Tuple[NodeId, ...],
    class_name: str,
    geometry: Optional[RectValue],
) -> NodeId:
    index = min(doc.node(node_id).slot_index for node_id in ordered)
    spec = NodeSpec("widget", None, (("class_name", class_name), ("object_name", _stem(class_name))))
    ids, _renames, _conflicts = planning.insert_fragment(
        doc, ctx, InContainer(holder.id, index, geometry), Fragment((spec,)), False
    )
    return ids[0]


def _insert_page(doc: UiDocument, ctx: PlanContext, tabs: NodeId, title: str) -> NodeId:
    page = NodeSpec(
        "widget",
        None,
        (("class_name", "QWidget"), ("object_name", "tab")),
        (),
        (PropertyEntry("attribute", "title", StringValue(title)),),
    )
    ids, _renames, _conflicts = planning.insert_fragment(doc, ctx, InContainer(tabs, 0), Fragment((page,)), False)
    return ids[0]


def _layout_id(doc: UiDocument, widget_id: NodeId) -> NodeId:
    layout = doc.layout_of(widget_id)
    if layout is None:
        raise CommandRejected("The new container has no layout.")
    return layout.id


def _clear_geometry(doc: UiDocument, ctx: PlanContext, ids: Tuple[NodeId, ...]) -> None:
    for node_id in ids:
        if doc.node(node_id).prop("geometry") is not None:
            planning.set_property(doc, ctx, node_id, "geometry", None)


def _stem(class_name: str) -> str:
    bare = class_name[1:] if class_name.startswith("Q") else class_name
    return bare[:1].lower() + bare[1:]
