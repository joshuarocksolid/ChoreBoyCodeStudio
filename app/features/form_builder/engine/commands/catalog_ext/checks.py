"""``SetChecks`` and ``AddErrorLabel``. One apply is one undo step."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Hashable, Optional, Tuple

from app.features.form_builder.engine.commands import planning
from app.features.form_builder.engine.commands.base import CommandRejected, PlanContext
from app.features.form_builder.engine.commands.placement import InBoxLayout, InFormRow, InGridCell
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.logic.checks import Check, kind_text, plan, read_checks, write_checks
from app.features.form_builder.engine.logic.codec import LogicWriteError
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import StringValue, semantic_equal

_BOX = frozenset({"QVBoxLayout", "QHBoxLayout"})


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if add is None:
        return
    add(SetChecks)
    add(AddErrorLabel)


@dataclass(frozen=True)
class SetChecks:
    """Replace ``cbcsValidate`` and the Qt properties ``plan`` names for those checks."""

    command_type: ClassVar[str] = "set_checks"
    owner: NodeId
    checks: Tuple[Check, ...]
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        return "Set checks"

    def merge_key(self) -> Optional[Hashable]:
        return None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.require_logic_writable(doc)
        node = doc.get(self.owner)
        if not isinstance(node, WidgetNode):
            raise CommandRejected("That object is not a widget.")
        kind = kind_text(node)
        old = _stored(node)
        old_plan = plan(node.class_name or "", old, kind)
        new_plan = plan(node.class_name or "", self.checks, kind)
        current = {}
        for item in old_plan.native:
            entry = node.prop(item.prop)
            if entry is not None:
                current[item.prop] = entry.value
        try:
            text = write_checks(self.checks)
        except LogicWriteError as exc:
            raise CommandRejected(str(exc), code="FB401") from exc
        planning.set_logic(doc, ctx, self.owner, "cbcsValidate", text)
        new_props = {item.prop for item in new_plan.native}
        for item in old_plan.native:
            if item.prop in new_props:
                continue
            if item.prop in current and semantic_equal(current[item.prop], item.value):
                planning.set_property(doc, ctx, self.owner, item.prop, None)
        for item in new_plan.native:
            planning.set_property(doc, ctx, self.owner, item.prop, item.value)


@dataclass(frozen=True)
class AddErrorLabel:
    """Insert ``{name}Error`` after the field and point ``cbcsErrorLabel`` at it."""

    command_type: ClassVar[str] = "add_error_label"
    owner: NodeId
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        return "Add error label"

    def merge_key(self) -> Optional[Hashable]:
        return None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.require_logic_writable(doc)
        node = doc.get(self.owner)
        if not isinstance(node, WidgetNode):
            raise CommandRejected("That object is not a widget.")
        name = node.object_name
        if not name:
            raise CommandRejected("That field has no name.")
        label_name = name + "Error"
        existing = doc.by_name(label_name)
        if existing:
            _set_label(doc, ctx, node, label_name)
            return
        item_id = doc.containing_layout_item(node.id)
        if item_id is None:
            raise CommandRejected("That field is not in a layout.")
        item = doc.node(item_id)
        layout = doc.parent(item.id)
        if not isinstance(item, LayoutItemNode) or not isinstance(layout, LayoutNode):
            raise CommandRejected("That field is not in a layout.")
        placement = _placement(layout, item)
        spec = NodeSpec(
            "widget",
            None,
            (("class_name", "QLabel"), ("object_name", label_name)),
            (PropertyEntry("property", "text", StringValue("")),),
        )
        ids, _, _, _ = planning.insert_fragment(doc, ctx, placement, Fragment((spec,)), False)
        inserted = doc.node(ids[0])
        actual = inserted.object_name if isinstance(inserted, WidgetNode) else label_name
        _set_label(doc, ctx, node, actual or label_name)


def _stored(node: WidgetNode) -> Tuple[Check, ...]:
    value = node.value("cbcsValidate")
    if not isinstance(value, StringValue) or not value.text.strip():
        return ()
    read = read_checks(value.text)
    if read.error is not None:
        return ()
    return read.checks


def _set_label(doc: UiDocument, ctx: PlanContext, node: WidgetNode, label_name: str) -> None:
    current = node.value("cbcsErrorLabel")
    if isinstance(current, StringValue) and current.text == label_name:
        return
    planning.set_logic(doc, ctx, node.id, "cbcsErrorLabel", label_name)


def _placement(layout: LayoutNode, item: LayoutItemNode) -> object:
    if layout.class_name in _BOX:
        return InBoxLayout(layout.id, item.slot_index + 1)
    if layout.class_name == "QFormLayout":
        row = item.row if item.row is not None else 0
        span = item.rowspan or 1
        return InFormRow(layout.id, row + span, "field", True)
    if layout.class_name == "QGridLayout":
        row = item.row if item.row is not None else 0
        span = item.rowspan or 1
        column = item.column if item.column is not None else 0
        return InGridCell(layout.id, row + span, column, mode="insert_row")
    raise CommandRejected("That layout can't take an error label.")
