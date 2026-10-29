"""Action, action group and button group commands (UX-MAIN-011, 012, 017, 019).

``SetButtonGroup`` in ``catalog.py`` stays for pasted groups; the commands here
carry the undo names of UX_SPEC 13.2.10.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional, Tuple

from app.features.form_builder.engine.commands import planning
from app.features.form_builder.engine.commands.base import CommandRejected, PlanContext
from app.features.form_builder.engine.commands.catalog import _CommandBase
from app.features.form_builder.engine.commands.ops import InsertNodeOp, MoveNodeOp, RemoveNodeOp
from app.features.form_builder.engine.commands.placement import InActionList
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query import actions as q
from app.features.form_builder.engine.ui4.document import UiDocument, next_object_name
from app.features.form_builder.engine.ui4.nodes import ActionNode, WidgetNode
from app.features.form_builder.engine.ui4.spec import NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import StringValue

_BUTTON_BASE = "QAbstractButton"
_BUTTONS = frozenset({"QPushButton", "QToolButton", "QRadioButton", "QCheckBox", "QCommandLinkButton"})


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if add is None:
        return
    for command in (
        NewAction,
        DeleteActions,
        PasteActions,
        GroupActions,
        UngroupActions,
        SetActionGroup,
        SetWidgetAction,
        MakeButtonGroup,
        UngroupButtons,
        ChangeButtonGroup,
    ):
        add(command)


@dataclass(frozen=True)
class NewAction(_CommandBase):
    """A new action in the Actions list, on no menu yet (UX-MAIN-010)."""

    command_type: ClassVar[str] = "new_action"
    _label_text: ClassVar[str] = "New action"
    text: str
    group: Optional[NodeId] = None
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        return "New action %s" % q.plain_text(self.text)

    def apply(self, doc: UiDocument, ctx: PlanContext) -> NodeId:
        if not self.text.strip():
            raise CommandRejected("Type the text of the action first.")
        spec = NodeSpec(
            "action",
            None,
            (("name", q.name_from_text("action", self.text)),),
            (PropertyEntry("property", "text", StringValue(self.text)),),
        )
        return planning.create_action(doc, ctx, spec, self.group, None)


@dataclass(frozen=True)
class DeleteActions(_CommandBase):
    """Delete actions with all their references and connections."""

    command_type: ClassVar[str] = "delete_actions"
    _label_text: ClassVar[str] = "Delete action"
    actions: Tuple[NodeId, ...]
    text: str = ""
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        if len(self.actions) > 1:
            return "Delete %d actions" % len(self.actions)
        return "Delete action %s" % q.plain_text(self.text)

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        for node_id in self.actions:
            if not isinstance(doc.get(node_id), ActionNode):
                raise CommandRejected("That action is no longer in the form.")
        planning.delete_nodes(doc, ctx, self.actions)


@dataclass(frozen=True)
class PasteActions(_CommandBase):
    """Paste copied actions (also from another form). Names follow the suffix rule."""

    command_type: ClassVar[str] = "paste_actions"
    _label_text: ClassVar[str] = "Paste actions"
    specs: Tuple[NodeSpec, ...]
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        return "Paste %d actions" % len(self.specs) if len(self.specs) != 1 else "Paste 1 action"

    def apply(self, doc: UiDocument, ctx: PlanContext) -> Tuple[NodeId, ...]:
        made = []
        for spec in self.specs:
            if spec.kind != "action":
                raise CommandRejected("Only actions can be pasted here.")
            clean = NodeSpec(
                "action",
                None,
                tuple(item for item in spec.fields if item[0] == "name"),
                spec.properties,
                spec.attributes,
            )
            made.append(planning.create_action(doc, ctx, clean, None, None))
        if made:
            ctx.select(tuple(made), made[-1])
        return tuple(made)


@dataclass(frozen=True)
class GroupActions(_CommandBase):
    """Make a choice group of two or more actions (exclusive by default)."""

    command_type: ClassVar[str] = "group_actions"
    _label_text: ClassVar[str] = "Group actions"
    actions: Tuple[NodeId, ...]
    merge_token: Optional[str] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> NodeId:
        if len(self.actions) < 2:
            raise CommandRejected("Pick two or more actions to group.")
        for node_id in self.actions:
            if not isinstance(doc.get(node_id), ActionNode):
                raise CommandRejected("That action is no longer in the form.")
        name = next_object_name("actionGroup", doc.names())
        spec = planning.allocate_spec(ctx, NodeSpec("actiongroup", None, (("name", name),)))
        ctx.do(InsertNodeOp(doc.root.id, "action_groups", len(doc.root.children("action_groups")), spec))
        for index, node_id in enumerate(self.actions):
            ctx.do(MoveNodeOp(node_id, spec.id, "actions", index))  # type: ignore[arg-type]
        ctx.select(self.actions, self.actions[0])
        return spec.id  # type: ignore[return-value]


@dataclass(frozen=True)
class UngroupActions(_CommandBase):
    command_type: ClassVar[str] = "ungroup_actions"
    _label_text: ClassVar[str] = "Ungroup actions"
    group: NodeId
    merge_token: Optional[str] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        node = doc.get(self.group)
        if node is None or node.kind != "actiongroup":
            raise CommandRejected("That action group is no longer in the form.")
        members = tuple(child.id for child in node.children("actions"))
        parent = doc.parent(node.id)
        if parent is None:
            raise CommandRejected("That action group is no longer in the form.")
        slot = parent.children("actions")
        for offset, member in enumerate(members):
            ctx.do(MoveNodeOp(member, parent.id, "actions", len(slot) + offset))
        planning.delete_nodes(doc, ctx, (node.id,))
        if members:
            ctx.select(members, members[0])


@dataclass(frozen=True)
class SetActionGroup(_CommandBase):
    """The inspector's Group drop-down: move an action into a group, or out of it."""

    command_type: ClassVar[str] = "set_action_group"
    _label_text: ClassVar[str] = "Change action group"
    action: NodeId
    group: Optional[str]
    merge_token: Optional[str] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        node = doc.get(self.action)
        if not isinstance(node, ActionNode):
            raise CommandRejected("That action is no longer in the form.")
        if self.group is None:
            parent = doc.root
            slot = "actions"
        else:
            found = doc.by_name(self.group)
            target = doc.get(found[0]) if found else None
            if target is None or target.kind != "actiongroup":
                raise CommandRejected("That action group is no longer in the form.")
            parent, slot = target, "actions"
        if doc.parent(node.id) is not None and doc.parent(node.id).id == parent.id:  # type: ignore[union-attr]
            return
        ctx.do(MoveNodeOp(node.id, parent.id, slot, len(parent.children(slot))))
        ctx.select((node.id,), node.id)


@dataclass(frozen=True)
class SetWidgetAction(_CommandBase):
    """Tick or untick an action in a widget's context menu (UX-MAIN-017)."""

    command_type: ClassVar[str] = "set_widget_action"
    _label_text: ClassVar[str] = "Change widget actions"
    widget: NodeId
    action: str
    on: bool
    #: The widget's name, for the undo name.
    widget_name: str = ""
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        if self.on:
            return "Add %s to %s" % (self.action, self.widget_name)
        return "Remove %s from %s" % (self.action, self.widget_name)

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        host = doc.get(self.widget)
        if not isinstance(host, WidgetNode):
            raise CommandRejected("That object is no longer in the form.")
        found = doc.by_name(self.action)
        if not found or not isinstance(doc.node(found[0]), ActionNode):
            raise CommandRejected("That action is no longer in the form.")
        refs = [ref for ref in q.refs_of(doc, host.id) if ref.name == self.action]
        if self.on:
            if not refs:
                planning.add_action_ref(doc, ctx, InActionList(host.id, len(q.refs_of(doc, host.id))), self.action)
        else:
            for ref in refs:
                ctx.do(RemoveNodeOp(ref.id))
        ctx.select((host.id,), host.id)


@dataclass(frozen=True)
class MakeButtonGroup(_CommandBase):
    """Put two or more buttons in a new group without moving them (UX-MAIN-019)."""

    command_type: ClassVar[str] = "make_button_group"
    _label_text: ClassVar[str] = "Make a button group"
    buttons: Tuple[NodeId, ...]
    merge_token: Optional[str] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> str:
        if len(self.buttons) < 2:
            raise CommandRejected("Pick two or more buttons to group.")
        _require_buttons(doc, ctx, self.buttons)
        name = next_object_name("buttonGroup", doc.names())
        planning.set_button_group(doc, ctx, self.buttons, name)
        ctx.select(self.buttons, self.buttons[0])
        return name


@dataclass(frozen=True)
class UngroupButtons(_CommandBase):
    command_type: ClassVar[str] = "ungroup_buttons"
    _label_text: ClassVar[str] = "Ungroup buttons"
    group: str
    merge_token: Optional[str] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        members = tuple(item[2] for item in q.button_groups(doc) if item[0] == self.group)
        if not members:
            raise CommandRejected("That button group is no longer in the form.")
        planning.set_button_group(doc, ctx, members[0], None)
        if members[0]:
            ctx.select(members[0], members[0][0])


@dataclass(frozen=True)
class ChangeButtonGroup(_CommandBase):
    """A button's Content group drop-down: None, a form group or a new one."""

    command_type: ClassVar[str] = "change_button_group"
    _label_text: ClassVar[str] = "Change button group"
    buttons: Tuple[NodeId, ...]
    group: Optional[str]
    name: str = ""
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        return "Change button group of %s" % self.name if self.name else "Change button group"

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        _require_buttons(doc, ctx, self.buttons)
        planning.set_button_group(doc, ctx, self.buttons, self.group)
        ctx.select(self.buttons, self.buttons[0])


def _require_buttons(doc: UiDocument, ctx: PlanContext, buttons: Tuple[NodeId, ...]) -> None:
    for node_id in buttons:
        node = doc.get(node_id)
        if not isinstance(node, WidgetNode):
            raise CommandRejected("That object is no longer in the form.")
        info = ctx.classes.class_info(node.class_name)
        if node.class_name not in _BUTTONS and (info is None or not info.is_a(_BUTTON_BASE)):
            raise CommandRejected("Only buttons can be in a button group.")


__all__ = [
    "ChangeButtonGroup",
    "DeleteActions",
    "GroupActions",
    "MakeButtonGroup",
    "NewAction",
    "PasteActions",
    "SetActionGroup",
    "SetWidgetAction",
    "UngroupActions",
    "UngroupButtons",
    "register",
]
