"""Drop commands whose new ids are only known inside one ``apply``.

Insert-row, insert-column and wrapping siblings that already exist stay on
the catalog placements. These four exist because a later step needs an id
allocated by an earlier step, and the drop is still one undo entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional, Tuple

from app.features.form_builder.engine.commands import planning
from app.features.form_builder.engine.commands.base import CommandRejected, PlanContext
from app.features.form_builder.engine.commands.catalog import _CommandBase
from app.features.form_builder.engine.commands.catalog_ext.pages import InsertPage  # re-export: the page commands moved (M4.2)
from app.features.form_builder.engine.commands.ops import MoveNodeOp, SetFieldOp
from app.features.form_builder.engine.commands.placement import InBoxLayout, InContainer, InFormRow
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.tree import form_rows
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import StringValue


# These widgets already show their own words, so a form row does not invent
# a "New field:" label beside them (UX-FORML-002). They sit in the field cell.
_SHOWS_OWN_TEXT = frozenset(
    {
        "QPushButton",
        "QToolButton",
        "QCheckBox",
        "QRadioButton",
        "QGroupBox",
        "QDialogButtonBox",
        "QCommandLinkButton",
    }
)


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if add is None:
        return
    add(InsertFormRow)
    add(WrapWithNew)
    add(AdoptIntoBox)
    add(SwapFormRows)
    add(SpliceReading)


@dataclass(frozen=True)
class InsertFormRow(_CommandBase):
    command_type: ClassVar[str] = "insert_form_row"
    _label_text: ClassVar[str] = "Insert row"
    layout: NodeId
    row: int
    fragment: Optional[Fragment] = None
    existing: Optional[NodeId] = None
    merge_token: Optional[str] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> Tuple[NodeId, NodeId]:
        if (self.fragment is None) == (self.existing is None):
            raise CommandRejected("A new form row needs a widget.")
        if self.existing is not None and not doc.contains(self.existing):
            raise CommandRejected("That object is no longer in the form.")
        if _shows_own_text(doc, self.fragment, self.existing):
            return _insert_unlabeled_field(doc, ctx, self.layout, self.row, self.fragment, self.existing)
        label = NodeSpec(
            "widget",
            None,
            (("class_name", "QLabel"), ("object_name", "label")),
            (PropertyEntry("property", "text", StringValue("New field:")),),
        )
        label_ids, _, _, _ = planning.insert_fragment(
            doc,
            ctx,
            InFormRow(self.layout, self.row, "label", True),
            Fragment((label,)),
            False,
        )
        label_id = label_ids[0]
        if self.existing is not None:
            planning.move_nodes(doc, ctx, (self.existing,), InFormRow(self.layout, self.row, "field", False))
            _clear_geometry(doc, ctx, self.existing)
            field_id = self.existing
        else:
            assert self.fragment is not None
            field_ids, _, _, _ = planning.insert_fragment(
                doc,
                ctx,
                InFormRow(self.layout, self.row, "field", False),
                self.fragment,
                False,
            )
            field_id = field_ids[0]
        field = doc.node(field_id)
        name = field.object_name if isinstance(field, WidgetNode) else ""
        if name:
            planning.set_buddy(doc, ctx, label_id, name)
        ctx.select((label_id, field_id), label_id)
        return (label_id, field_id)


@dataclass(frozen=True)
class WrapWithNew(_CommandBase):
    command_type: ClassVar[str] = "wrap_with_new"
    _label_text: ClassVar[str] = "Wrap"
    neighbour: NodeId
    side: str
    layout_class: str
    fragment: Optional[Fragment] = None
    existing: Optional[NodeId] = None
    merge_token: Optional[str] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> NodeId:
        if self.side not in ("before", "after"):
            raise CommandRejected("That side is not a wrap.")
        if (self.fragment is None) == (self.existing is None):
            raise CommandRejected("There is nothing to wrap.")
        if self.existing == self.neighbour:
            raise CommandRejected("A widget can't go inside itself.")
        if not doc.contains(self.neighbour) or (self.existing is not None and not doc.contains(self.existing)):
            raise CommandRejected("That object is no longer in the form.")
        item = doc.parent(self.neighbour)
        if not isinstance(item, LayoutItemNode):
            raise CommandRejected("That object is not in a layout.")
        layout = doc.parent(item.id)
        if not isinstance(layout, LayoutNode):
            raise CommandRejected("That object is not in a layout.")
        at = item.slot_index if self.side == "before" else item.slot_index + 1
        if self.existing is not None:
            planning.move_nodes(doc, ctx, (self.existing,), InBoxLayout(layout.id, at))
            _clear_geometry(doc, ctx, self.existing)
            new_id = self.existing
        else:
            assert self.fragment is not None
            ids, _, _, _ = planning.insert_fragment(
                doc, ctx, InBoxLayout(layout.id, at), self.fragment, False
            )
            new_id = ids[0]
        planning.wrap_nodes(doc, ctx, (self.neighbour, new_id), None, self.layout_class, None)
        ctx.select((new_id,), new_id)
        return new_id


@dataclass(frozen=True)
class AdoptIntoBox(_CommandBase):
    command_type: ClassVar[str] = "adopt_into_box"
    _label_text: ClassVar[str] = "Insert"
    container: NodeId
    fragment: Optional[Fragment] = None
    existing: Tuple[NodeId, ...] = ()
    merge_token: Optional[str] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> Tuple[NodeId, ...]:
        if (self.fragment is None) == (not self.existing):
            raise CommandRejected("There is nothing to place.")
        layout_id = planning.apply_layout_command(doc, ctx, self.container, "QVBoxLayout", (), None)
        if self.existing:
            planning.move_nodes(doc, ctx, self.existing, InBoxLayout(layout_id, 0))
            for node_id in self.existing:
                _clear_geometry(doc, ctx, node_id)
            ctx.select(self.existing, self.existing[0])
            return self.existing
        assert self.fragment is not None
        ids, _, _, _ = planning.insert_fragment(
            doc, ctx, InBoxLayout(layout_id, 0), self.fragment, False
        )
        return ids


@dataclass(frozen=True)
class SwapFormRows(_CommandBase):
    command_type: ClassVar[str] = "swap_form_rows"
    _label_text: ClassVar[str] = "Nudge"
    layout: NodeId
    row: int
    direction: int
    merge_token: Optional[str] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        if self.direction not in (-1, 1):
            raise CommandRejected("That row is the end of the form.")
        if not isinstance(doc.get(self.layout), LayoutNode):
            raise CommandRejected("That layout is no longer in the form.")
        other = self.row + self.direction
        rows = form_rows(doc, self.layout)
        if self.row < 0 or other < 0 or self.row >= len(rows) or other >= len(rows):
            raise CommandRejected("That row is the end of the form.")
        here = _row_items(doc, self.layout, self.row)
        there = _row_items(doc, self.layout, other)
        if not here or not there:
            raise CommandRejected("That row is the end of the form.")
        park = len(rows)
        for item_id in here:
            ctx.do(SetFieldOp(item_id, "row", park))
        for item_id in there:
            ctx.do(SetFieldOp(item_id, "row", self.row))
        for item_id in here:
            ctx.do(SetFieldOp(item_id, "row", other))
        _order_form_items(doc, ctx, self.layout)


@dataclass(frozen=True)
class SpliceReading(_CommandBase):
    """Insert into a uniform grid at a reading-order index."""

    command_type: ClassVar[str] = "splice_reading"
    _label_text: ClassVar[str] = "Move"
    layout: NodeId
    index: int
    existing: Tuple[NodeId, ...] = ()
    fragment: Optional[Fragment] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.splice_grid_reading(doc, ctx, self.layout, self.index, self.existing, self.fragment)


def _shows_own_text(doc: UiDocument, fragment: Optional[Fragment], existing: Optional[NodeId]) -> bool:
    if existing is not None:
        node = doc.node(existing)
        return isinstance(node, WidgetNode) and node.class_name in _SHOWS_OWN_TEXT
    if fragment is None or not fragment.nodes:
        return False
    class_name = fragment.nodes[0].field("class_name")
    return isinstance(class_name, str) and class_name in _SHOWS_OWN_TEXT


def _insert_unlabeled_field(
    doc: UiDocument,
    ctx: PlanContext,
    layout: NodeId,
    row: int,
    fragment: Optional[Fragment],
    existing: Optional[NodeId],
) -> Tuple[NodeId, NodeId]:
    """The field cell only. Both returned ids are the field, since there is no label."""
    placement = InFormRow(layout, row, "field", True)
    if existing is not None:
        planning.move_nodes(doc, ctx, (existing,), placement)
        _clear_geometry(doc, ctx, existing)
        field_id = existing
    else:
        assert fragment is not None
        field_ids, _, _, _ = planning.insert_fragment(doc, ctx, placement, fragment, False)
        field_id = field_ids[0]
    ctx.select((field_id,), field_id)
    return (field_id, field_id)


def _clear_geometry(doc: UiDocument, ctx: PlanContext, node_id: NodeId) -> None:
    if doc.contains(node_id) and doc.node(node_id).prop("geometry") is not None:
        planning.set_property(doc, ctx, node_id, "geometry", None)


def _order_form_items(doc: UiDocument, ctx: PlanContext, layout_id: NodeId) -> None:
    layout = doc.node(layout_id)
    if not isinstance(layout, LayoutNode):
        return
    ordered = sorted(
        layout.items,
        key=lambda item: (0 if item.row is None else item.row, 0 if item.column is None else item.column, item.slot_index),
    )
    for index, item in enumerate(ordered):
        current = doc.node(item.id)
        if not isinstance(current, LayoutItemNode) or current.slot_index == index:
            continue
        ctx.do(MoveNodeOp(item.id, layout_id, "layout_items", index))


def _row_items(doc: UiDocument, layout_id: NodeId, row: int) -> Tuple[NodeId, ...]:
    layout = doc.node(layout_id)
    if not isinstance(layout, LayoutNode):
        return ()
    found = []
    for item in layout.items:
        current = 0 if item.row is None else item.row
        if current == row:
            found.append(item.id)
    return tuple(found)
