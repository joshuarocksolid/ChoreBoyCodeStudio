"""The command catalog (CONTRACTS.md section 3.5).

Each class is the parameter record of one command. ``apply`` plans ops through
``planning`` and does not touch the document itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Hashable, Literal, Optional, Tuple

from app.features.form_builder.engine.commands import planning
from app.features.form_builder.engine.commands.base import PlanContext
from app.features.form_builder.engine.commands.placement import Placement
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec
from app.features.form_builder.engine.ui4.values import RectValue, SizePolicyValue, SizeValue, Value


class _CommandBase:
    """Default protocol members. Subclasses override what the contract names."""

    command_type: ClassVar[str] = ""
    _label_text: ClassVar[str] = ""
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        return self._label_text

    def merge_key(self) -> Optional[Hashable]:
        return None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> Any:
        raise NotImplementedError


@dataclass(frozen=True)
class InsertFragment(_CommandBase):
    """Insert a fragment. Names collide with the suffix rule. Selects the new tops."""

    command_type: ClassVar[str] = "insert_fragment"
    _label_text: ClassVar[str] = "Insert"
    placement: Placement
    fragment: Fragment
    auto_layout: bool = True
    undo_label: str = ""

    @property
    def label(self) -> str:
        return self.undo_label or self._label_text

    def apply(self, doc: UiDocument, ctx: PlanContext) -> "InsertResult":
        ids, renames, conflicts, dangling = planning.insert_fragment(
            doc, ctx, self.placement, self.fragment, self.auto_layout
        )
        return InsertResult(ids, renames, conflicts, dangling)


@dataclass(frozen=True)
class InsertResult:
    ids: Tuple[NodeId, ...]
    renames: Tuple[Tuple[str, str], ...]
    conflicts: Tuple[str, ...] = ()
    dangling: Tuple[str, ...] = ()


@dataclass(frozen=True)
class DeleteNodes(_CommandBase):
    """Delete nodes. Grid and form cells stay empty. Logic references stay."""

    command_type: ClassVar[str] = "delete_nodes"
    _label_text: ClassVar[str] = "Delete"
    ids: Tuple[NodeId, ...]
    undo_label: str = ""

    @property
    def label(self) -> str:
        return self.undo_label or self._label_text

    def apply(self, doc: UiDocument, ctx: PlanContext) -> Tuple[str, ...]:
        return planning.delete_nodes(doc, ctx, self.ids)


@dataclass(frozen=True)
class MoveNodes(_CommandBase):
    """Move existing nodes, keeping ids. A grid move changes only those cells."""

    command_type: ClassVar[str] = "move_nodes"
    _label_text: ClassVar[str] = "Move"
    ids: Tuple[NodeId, ...]
    placement: Placement
    merge_token: Optional[str] = None

    def merge_key(self) -> Optional[Hashable]:
        return ("move", self.ids)

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.move_nodes(doc, ctx, self.ids, self.placement)


@dataclass(frozen=True)
class Wrap(_CommandBase):
    """Wrap sibling items. ``container_class`` None wraps them in a nested layout."""

    command_type: ClassVar[str] = "wrap"
    _label_text: ClassVar[str] = "Wrap"
    ids: Tuple[NodeId, ...]
    container_class: Optional[str]
    layout_class: str = "QVBoxLayout"
    cells: Optional[Tuple[Tuple[NodeId, int, int], ...]] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> NodeId:
        return planning.wrap_nodes(
            doc, ctx, self.ids, self.container_class, self.layout_class, self.cells
        )


@dataclass(frozen=True)
class Unwrap(_CommandBase):
    """Lift a container's children into the parent layout."""

    command_type: ClassVar[str] = "unwrap"
    _label_text: ClassVar[str] = "Unwrap"
    id: NodeId

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.unwrap_node(doc, ctx, self.id)


@dataclass(frozen=True)
class ApplyLayout(_CommandBase):
    """Give a layout-less container a layout and clear child geometry."""

    command_type: ClassVar[str] = "apply_layout"
    _label_text: ClassVar[str] = "Lay out"
    widget: NodeId
    layout_class: str
    order: Tuple[NodeId, ...] = ()
    cells: Optional[Tuple[Tuple[NodeId, int, int, int, int], ...]] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> NodeId:
        return planning.apply_layout_command(
            doc, ctx, self.widget, self.layout_class, self.order, self.cells
        )


@dataclass(frozen=True)
class BreakLayout(_CommandBase):
    """Remove a layout. Top-level children keep the measured geometries."""

    command_type: ClassVar[str] = "break_layout"
    _label_text: ClassVar[str] = "Break layout"
    layout: NodeId
    geometries: Tuple[Tuple[NodeId, RectValue], ...] = ()

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.break_layout(doc, ctx, self.layout, self.geometries)


@dataclass(frozen=True)
class HoldLayout(_CommandBase):
    """Replace a nested layout with a plain widget in the same cell.

    Children keep ``geometries`` relative to that widget. ``minimum`` is the
    layout's measured box, written as minimumSize only, so the parent cell
    does not collapse on reload and still takes its share of spare room.
    The widget is named after the layout (``firstRow`` -> ``firstRowWidget``).
    """

    command_type: ClassVar[str] = "hold_layout"
    _label_text: ClassVar[str] = "Remove layout"
    layout: NodeId
    minimum: SizeValue
    geometries: Tuple[Tuple[NodeId, RectValue], ...] = ()
    #: Fixed on each axis the layout could not grow along, so the widget
    #: grows only where the layout did. None leaves the class default.
    policy: Optional[SizePolicyValue] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> NodeId:
        return planning.hold_layout(doc, ctx, self.layout, self.minimum, self.geometries, self.policy)


@dataclass(frozen=True)
class MorphLayout(_CommandBase):
    """Change a layout class using the Designer morph rules."""

    command_type: ClassVar[str] = "morph_layout"
    _label_text: ClassVar[str] = "Change layout"
    layout: NodeId
    new_class: str

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.morph_layout(doc, ctx, self.layout, self.new_class)


@dataclass(frozen=True)
class MorphWidget(_CommandBase):
    """Change a widget class. Returns the property names that were dropped.

    ``accepted`` is the target class's property names. None falls back to the
    class table, and drops nothing when that table has no row for the class.
    """

    command_type: ClassVar[str] = "morph_widget"
    _label_text: ClassVar[str] = "Change widget"
    id: NodeId
    new_class: str
    accepted: Optional[Tuple[str, ...]] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> Tuple[str, ...]:
        return planning.morph_widget(doc, ctx, self.id, self.new_class, self.accepted)


@dataclass(frozen=True)
class SimplifyGrid(_CommandBase):
    """Remove empty rows and columns of a grid."""

    command_type: ClassVar[str] = "simplify_grid"
    _label_text: ClassVar[str] = "Simplify grid"
    layout: NodeId

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.simplify_grid(doc, ctx, self.layout)


@dataclass(frozen=True)
class AdjustSize(_CommandBase):
    """Set geometry width and height from a measured size hint."""

    command_type: ClassVar[str] = "adjust_size"
    _label_text: ClassVar[str] = "Adjust size"
    id: NodeId
    size: SizeValue

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.adjust_size(doc, ctx, self.id, self.size)


@dataclass(frozen=True)
class SetZOrder(_CommandBase):
    """Write stacking order. Document order clears the field."""

    command_type: ClassVar[str] = "set_zorder"
    _label_text: ClassVar[str] = "Reorder"
    parent: NodeId
    order: Tuple[str, ...]

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.set_zorder(doc, ctx, self.parent, self.order)


@dataclass(frozen=True)
class SetProperty(_CommandBase):
    """Set one property, or reset it when ``value`` is None."""

    command_type: ClassVar[str] = "set_property"
    owner: NodeId
    name: str
    value: Optional[Value]
    kind: Literal["property", "attribute"] = "property"
    stdset: Optional[str] = None
    merge_token: Optional[str] = None
    #: A plain undo name for callers that know what the property means ("Change start page").
    undo_label: str = ""

    @property
    def label(self) -> str:
        if self.undo_label:
            return self.undo_label
        return "Reset" if self.value is None else "Edit"

    def merge_key(self) -> Optional[Hashable]:
        return ("set_property", self.owner, self.kind, self.name)

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.set_property(doc, ctx, self.owner, self.name, self.value, self.kind, self.stdset)


@dataclass(frozen=True)
class SetPropertyMany(_CommandBase):
    """The same property edit on every owner that accepts it. Returns the skipped ids."""

    command_type: ClassVar[str] = "set_property_many"
    owners: Tuple[NodeId, ...]
    name: str
    value: Optional[Value]
    kind: Literal["property", "attribute"] = "property"
    stdset: Optional[str] = None
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        return "Reset" if self.value is None else "Edit"

    def merge_key(self) -> Optional[Hashable]:
        return ("set_many", self.owners, self.kind, self.name)

    def apply(self, doc: UiDocument, ctx: PlanContext) -> Tuple[NodeId, ...]:
        return planning.set_property_many(
            doc, ctx, self.owners, self.name, self.value, self.kind, self.stdset
        )


@dataclass(frozen=True)
class Rename(_CommandBase):
    """Rename a node and its unique native references."""

    command_type: ClassVar[str] = "rename"
    _label_text: ClassVar[str] = "Rename"
    id: NodeId
    new_name: str

    def apply(self, doc: UiDocument, ctx: PlanContext) -> Tuple[str, ...]:
        return planning.rename_node(doc, ctx, self.id, self.new_name)


@dataclass(frozen=True)
class SetLayoutCell(_CommandBase):
    """Set a layout item's cell. None clears every cell field."""

    command_type: ClassVar[str] = "set_layout_cell"
    _label_text: ClassVar[str] = "Edit cell"
    item: NodeId
    row: Optional[int] = None
    column: Optional[int] = None
    rowspan: Optional[int] = None
    colspan: Optional[int] = None
    alignment: Optional[str] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.set_layout_cell(
            doc,
            ctx,
            self.item,
            self.row,
            self.column,
            self.rowspan,
            self.colspan,
            self.alignment,
        )


@dataclass(frozen=True)
class SetLayoutStretch(_CommandBase):
    """Set one layout stretch field. None clears it."""

    command_type: ClassVar[str] = "set_layout_stretch"
    _label_text: ClassVar[str] = "Edit stretch"
    layout: NodeId
    field: Literal[
        "stretch",
        "rowstretch",
        "columnstretch",
        "rowminimumheight",
        "columnminimumwidth",
    ]
    value: Optional[str]
    merge_token: Optional[str] = None

    def merge_key(self) -> Optional[Hashable]:
        return ("layout_stretch", self.layout, self.field)

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.set_field(doc, ctx, self.layout, self.field, self.value)


@dataclass(frozen=True)
class SetGeometry(_CommandBase):
    """Set a free widget's geometry."""

    command_type: ClassVar[str] = "set_geometry"
    _label_text: ClassVar[str] = "Edit geometry"
    id: NodeId
    rect: RectValue
    merge_token: Optional[str] = None

    def merge_key(self) -> Optional[Hashable]:
        return ("geometry", self.id)

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.set_property(doc, ctx, self.id, "geometry", self.rect)


@dataclass(frozen=True)
class MovePage(_CommandBase):
    """Reorder one page and keep ``currentIndex`` on the same page.

    Presses on the same container inside one second are one undo step (UX-CONT-005).
    """

    command_type: ClassVar[str] = "move_page"
    _label_text: ClassVar[str] = "Move page"
    container: NodeId
    from_index: int
    to_index: int

    def merge_key(self) -> Optional[Hashable]:
        return ("move_page", int(self.container))

    def merge_window_s(self) -> float:
        """Menu and outline presses inside this window are one undo step."""
        return 1.0

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.move_page(doc, ctx, self.container, self.from_index, self.to_index)


@dataclass(frozen=True)
class SetItems(_CommandBase):
    """Replace item or header slots. None leaves that slot alone.

    One item-editor session is one undo step (UX-ITEM-007). The merge key is
    the widget, and ``merge_token`` is the session, so two widgets or two
    sessions never fold together.
    """

    command_type: ClassVar[str] = "set_items"
    _label_text: ClassVar[str] = "Edit items"
    widget: NodeId
    items: Optional[Tuple[NodeSpec, ...]] = None
    rows: Optional[Tuple[NodeSpec, ...]] = None
    columns: Optional[Tuple[NodeSpec, ...]] = None
    merge_token: Optional[str] = None
    widget_name: str = ""

    @property
    def label(self) -> str:
        if self.widget_name:
            return "Edit items of %s" % self.widget_name
        return self._label_text

    def merge_key(self) -> Optional[Hashable]:
        return ("set_items", int(self.widget))

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.set_items(doc, ctx, self.widget, self.items, self.rows, self.columns)


@dataclass(frozen=True)
class CreateAction(_CommandBase):
    """Add an action, and an addaction ref when ``ref_at`` is set."""

    command_type: ClassVar[str] = "create_action"
    _label_text: ClassVar[str] = "Create action"
    spec: NodeSpec
    group: Optional[NodeId] = None
    ref_at: Optional[Placement] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> NodeId:
        return planning.create_action(doc, ctx, self.spec, self.group, self.ref_at)


@dataclass(frozen=True)
class AddActionRef(_CommandBase):
    """Insert an addaction reference."""

    command_type: ClassVar[str] = "add_action_ref"
    _label_text: ClassVar[str] = "Add action"
    placement: Placement
    name: str

    def apply(self, doc: UiDocument, ctx: PlanContext) -> NodeId:
        return planning.add_action_ref(doc, ctx, self.placement, self.name)


@dataclass(frozen=True)
class CreateMenu(_CommandBase):
    """Add a QMenu and its addaction ref. Returns the menu id."""

    command_type: ClassVar[str] = "create_menu"
    _label_text: ClassVar[str] = "Create menu"
    placement: Placement
    title: str

    def apply(self, doc: UiDocument, ctx: PlanContext) -> NodeId:
        return planning.create_menu(doc, ctx, self.placement, self.title)


@dataclass(frozen=True)
class AddConnection(_CommandBase):
    """Insert a connection. ``index`` None appends."""

    command_type: ClassVar[str] = "add_connection"
    _label_text: ClassVar[str] = "Add connection"
    sender: str
    signal: str
    receiver: str
    slot: str
    index: Optional[int] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> NodeId:
        return planning.add_connection(
            doc, ctx, self.sender, self.signal, self.receiver, self.slot, self.index
        )


@dataclass(frozen=True)
class EditConnection(_CommandBase):
    """Change the connection fields that are not None."""

    command_type: ClassVar[str] = "edit_connection"
    _label_text: ClassVar[str] = "Edit connection"
    id: NodeId
    sender: Optional[str] = None
    signal: Optional[str] = None
    receiver: Optional[str] = None
    slot: Optional[str] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.edit_connection(
            doc, ctx, self.id, self.sender, self.signal, self.receiver, self.slot
        )


@dataclass(frozen=True)
class MoveConnection(_CommandBase):
    """Move a connection to ``to_index`` in the connection list."""

    command_type: ClassVar[str] = "move_connection"
    _label_text: ClassVar[str] = "Move connection"
    id: NodeId
    to_index: int

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.move_connection(doc, ctx, self.id, self.to_index)


@dataclass(frozen=True)
class SetTabStops(_CommandBase):
    """Write tab stops. None removes the element."""

    command_type: ClassVar[str] = "set_tabstops"
    _label_text: ClassVar[str] = "Tab order"
    names: Optional[Tuple[str, ...]]

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.set_tabstops(doc, ctx, self.names)


@dataclass(frozen=True)
class SetBuddy(_CommandBase):
    """Set or clear a label's buddy."""

    command_type: ClassVar[str] = "set_buddy"
    _label_text: ClassVar[str] = "Set buddy"
    label_widget: NodeId
    target: Optional[str]

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.set_buddy(doc, ctx, self.label_widget, self.target)


@dataclass(frozen=True)
class SetButtonGroup(_CommandBase):
    """Put buttons in a group, or take them out when ``group`` is None."""

    command_type: ClassVar[str] = "set_button_group"
    _label_text: ClassVar[str] = "Button group"
    buttons: Tuple[NodeId, ...]
    group: Optional[str]

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.set_button_group(doc, ctx, self.buttons, self.group)


@dataclass(frozen=True)
class SetFormSlots(_CommandBase):
    """Replace the form's slots declaration. None removes it."""

    command_type: ClassVar[str] = "set_form_slots"
    _label_text: ClassVar[str] = "Edit slots"
    signals: Optional[Tuple[str, ...]]
    slots: Optional[Tuple[str, ...]]

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.set_form_slots(doc, ctx, self.signals, self.slots)


@dataclass(frozen=True)
class Promote(_CommandBase):
    """Promote widgets, or demote them when ``class_name`` is None."""

    command_type: ClassVar[str] = "promote"
    ids: Tuple[NodeId, ...]
    class_name: Optional[str]
    declaration: Optional[NodeSpec] = None

    @property
    def label(self) -> str:
        return "Demote" if self.class_name is None else "Promote"

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.promote(doc, ctx, self.ids, self.class_name, self.declaration)


@dataclass(frozen=True)
class SetCustomWidget(_CommandBase):
    """Add, replace, or remove a custom-widget declaration."""

    command_type: ClassVar[str] = "set_custom_widget"
    _label_text: ClassVar[str] = "Custom widget"
    class_name: str
    spec: Optional[NodeSpec]

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.set_custom_widget(doc, ctx, self.class_name, self.spec)


@dataclass(frozen=True)
class SetResourceIncludes(_CommandBase):
    """Replace the resource include list."""

    command_type: ClassVar[str] = "set_resource_includes"
    _label_text: ClassVar[str] = "Resources"
    locations: Tuple[str, ...]

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.set_resource_includes(doc, ctx, self.locations)


@dataclass(frozen=True)
class SetFormField(_CommandBase):
    """Set one field of the ui node."""

    command_type: ClassVar[str] = "set_form_field"
    _label_text: ClassVar[str] = "Form settings"
    field: str
    value: object

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.set_form_field(doc, ctx, self.field, self.value)


_REPLACE_LABELS = {
    "xml_edit": "Edit XML",
    "draft": "Restore draft",
    "history": "Restore history",
    "reload": "Reload from disk",
}


@dataclass(frozen=True)
class ReplaceDocument(_CommandBase):
    """Replace the document with parsed ``text``. One ReplaceRootOp."""

    command_type: ClassVar[str] = "replace_document"
    text: str
    reason: Literal["xml_edit", "draft", "history", "reload"] = "xml_edit"

    @property
    def label(self) -> str:
        return _REPLACE_LABELS[self.reason]

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.replace_document_text(doc, ctx, self.text, reason=self.reason)


@dataclass(frozen=True)
class SetLogic(_CommandBase):
    """Set or clear one cbcs logic property and keep the root version marker."""

    command_type: ClassVar[str] = "set_logic"
    _label_text: ClassVar[str] = "Edit logic"
    owner: NodeId
    key: str
    text: Optional[str]
    merge_token: Optional[str] = None

    def merge_key(self) -> Optional[Hashable]:
        return ("logic", self.owner, self.key)

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.set_logic(doc, ctx, self.owner, self.key, self.text)
