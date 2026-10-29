"""Main-window parts and menu, toolbar and entry editing (UX-MAIN-001 ... 009).

Each command is one undo step with the name of UX_SPEC 13.2.10. A menu is a
``QMenu`` child widget of its bar or parent menu plus an ``<addaction>`` that
names it, as Designer writes it. An entry is an ``<action>`` under the main
window plus an ``<addaction>`` in the menu or toolbar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional, Tuple

from app.features.form_builder.engine.commands import planning
from app.features.form_builder.engine.commands.base import CommandRejected, PlanContext
from app.features.form_builder.engine.commands.catalog import _CommandBase
from app.features.form_builder.engine.commands.ops import InsertNodeOp, MoveNodeOp
from app.features.form_builder.engine.commands.placement import InActionList
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query import actions as q
from app.features.form_builder.engine.ui4.document import UiDocument, next_object_name
from app.features.form_builder.engine.ui4.nodes import ActionNode, ActionRefNode, WidgetNode
from app.features.form_builder.engine.ui4.spec import NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import BoolValue, EnumValue, StringValue

#: UX-MAIN-016 and the Main window sentences. The surface adds the friendly class.
NOT_A_MAIN_WINDOW = "Menus, toolbars and status bars go on a main window."

_PART_LABELS = {"menubar": "menu bar", "toolbar": "toolbar", "statusbar": "status bar"}
_SIDES = {
    "Top": "Qt::TopToolBarArea",
    "Bottom": "Qt::BottomToolBarArea",
    "Left": "Qt::LeftToolBarArea",
    "Right": "Qt::RightToolBarArea",
}


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if add is None:
        return
    for command in (
        AddMainWindowPart,
        RemoveMainWindowPart,
        AddMenu,
        AddEntry,
        AddSeparator,
        RemoveEntry,
        MoveEntry,
        RenameEntry,
    ):
        add(command)


@dataclass(frozen=True)
class AddMainWindowPart(_CommandBase):
    """Add a menu bar, a toolbar (on ``side``) or a status bar to a main window."""

    command_type: ClassVar[str] = "add_main_window_part"
    _label_text: ClassVar[str] = "Add part"
    part: str
    side: str = "Top"
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        return "Add %s" % _PART_LABELS.get(self.part, "part")

    def apply(self, doc: UiDocument, ctx: PlanContext) -> NodeId:
        if not q.is_main_window(doc):
            raise CommandRejected(NOT_A_MAIN_WINDOW)
        found = q.parts(doc)
        root = doc.root
        count = len(root.children("children"))
        if self.part == "menubar":
            if found["menubar"]:
                raise CommandRejected("This window already has a menu bar.")
            spec = _widget("QMenuBar", next_object_name("menubar", doc.names()))
            index = 0
        elif self.part == "statusbar":
            if found["statusbar"]:
                raise CommandRejected("This window already has a status bar.")
            spec = _widget("QStatusBar", next_object_name("statusbar", doc.names()))
            index = count
        elif self.part == "toolbar":
            area = _SIDES.get(self.side)
            if area is None:
                raise CommandRejected("A toolbar goes on the top, bottom, left or right.")
            name = next_object_name("toolBar", doc.names())
            spec = NodeSpec(
                "widget",
                None,
                (("class_name", "QToolBar"), ("object_name", name)),
                (PropertyEntry("property", "windowTitle", StringValue(name)),),
                (
                    PropertyEntry("attribute", "toolBarArea", EnumValue(area)),
                    PropertyEntry("attribute", "toolBarBreak", BoolValue(False)),
                ),
            )
            index = count
        else:
            raise CommandRejected("That is not a main window part.")
        allocated = planning.allocate_spec(ctx, spec)
        ctx.do(InsertNodeOp(root.id, "children", index, allocated))
        ctx.select((allocated.id,), allocated.id)  # type: ignore[arg-type]
        return allocated.id  # type: ignore[return-value]


@dataclass(frozen=True)
class RemoveMainWindowPart(_CommandBase):
    """Remove a menu bar, toolbar or status bar. Actions stay in the Actions list."""

    command_type: ClassVar[str] = "remove_main_window_part"
    _label_text: ClassVar[str] = "Remove part"
    part_id: NodeId
    merge_token: Optional[str] = None
    #: Set by ``for_part`` so the undo name reads right without the document.
    kind: str = ""

    @property
    def label(self) -> str:
        return "Remove %s" % _PART_LABELS.get(self.kind, "part")

    @classmethod
    def for_part(cls, doc: UiDocument, part_id: NodeId) -> "RemoveMainWindowPart":
        node = doc.node(part_id)
        kind = {"QMenuBar": "menubar", "QToolBar": "toolbar", "QStatusBar": "statusbar"}.get(
            node.field("class_name") if isinstance(node.field("class_name"), str) else "", ""  # type: ignore[arg-type]
        )
        return cls(part_id, None, kind)

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        if not doc.contains(self.part_id):
            raise CommandRejected("That object is no longer in the form.")
        node = doc.node(self.part_id)
        if not isinstance(node, WidgetNode) or node.class_name not in ("QMenuBar", "QToolBar", "QStatusBar"):
            raise CommandRejected("That is not a menu bar, toolbar or status bar.")
        parent = doc.parent(node.id)
        planning.delete_nodes(doc, ctx, (node.id,))
        if parent is not None:
            ctx.select((parent.id,), parent.id)


@dataclass(frozen=True)
class AddMenu(_CommandBase):
    """Type a new menu on a menu bar, or a submenu in a menu (UX-MAIN-006)."""

    command_type: ClassVar[str] = "add_menu"
    _label_text: ClassVar[str] = "Add menu"
    host: NodeId
    index: int
    title: str
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        return "Add menu %s" % q.plain_text(self.title)

    def apply(self, doc: UiDocument, ctx: PlanContext) -> NodeId:
        host = _host(doc, self.host, ("QMenuBar", "QMenu"), "Menus go on a menu bar or in a menu.")
        _check_index(doc, host.id, self.index)
        name = next_object_name(q.name_from_text("menu", self.title), doc.names())
        spec = NodeSpec(
            "widget",
            None,
            (("class_name", "QMenu"), ("object_name", name)),
            (PropertyEntry("property", "title", StringValue(self.title)),),
        )
        allocated = planning.allocate_spec(ctx, spec)
        before = sum(1 for entry in q.entries(doc, host.id)[: self.index] if entry.kind == "menu")
        ctx.do(InsertNodeOp(host.id, "children", before, allocated))
        planning.add_action_ref(doc, ctx, InActionList(host.id, self.index), name)
        ctx.select((allocated.id,), allocated.id)  # type: ignore[arg-type]
        return allocated.id  # type: ignore[return-value]


@dataclass(frozen=True)
class AddEntry(_CommandBase):
    """Type a new entry, or reuse an action (``action``), in a menu or toolbar."""

    command_type: ClassVar[str] = "add_entry"
    _label_text: ClassVar[str] = "Add entry"
    host: NodeId
    index: int
    text: str = ""
    action: Optional[str] = None
    #: "the File menu" or "toolBar": the place in the undo name.
    where: str = ""
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        shown = q.plain_text(self.text)
        if self.where:
            return "Add %s to %s" % (shown, self.where)
        return "Add %s" % shown

    def apply(self, doc: UiDocument, ctx: PlanContext) -> NodeId:
        host = _host(doc, self.host, None, "Actions go on a menu or a toolbar.")
        _check_index(doc, host.id, self.index)
        placement = InActionList(host.id, self.index)
        if self.action is not None:
            found = doc.by_name(self.action)
            if not found or not isinstance(doc.node(found[0]), ActionNode):
                raise CommandRejected("That action is no longer in the form.")
            ref = planning.add_action_ref(doc, ctx, placement, self.action)
            ctx.select((found[0],), found[0])
            return ref
        if not self.text.strip():
            raise CommandRejected("Type the text of the entry first.")
        spec = NodeSpec(
            "action",
            None,
            (("name", q.name_from_text("action", self.text)),),
            (PropertyEntry("property", "text", StringValue(self.text)),),
        )
        return planning.create_action(doc, ctx, spec, None, placement)


@dataclass(frozen=True)
class AddSeparator(_CommandBase):
    command_type: ClassVar[str] = "add_separator"
    _label_text: ClassVar[str] = "Add separator"
    host: NodeId
    index: int
    merge_token: Optional[str] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> NodeId:
        host = _host(doc, self.host, None, "Separators go on a menu or a toolbar.")
        _check_index(doc, host.id, self.index)
        return planning.add_action_ref(doc, ctx, InActionList(host.id, self.index), q.SEPARATOR)


@dataclass(frozen=True)
class RemoveEntry(_CommandBase):
    """Remove an entry, a toolbar button or a separator (UX-MAIN-008).

    An action used nowhere else goes with its last reference. Removing a menu
    removes its submenus, and the actions left unused with them. Returns the
    names of the places that still use the action (empty when it is gone).
    """

    command_type: ClassVar[str] = "remove_entry"
    _label_text: ClassVar[str] = "Remove entry"
    ref: NodeId
    #: The entry's shown text, for the undo name.
    text: str = ""
    kind: str = "action"
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        if self.kind == "separator":
            return "Remove separator"
        if self.kind == "menu":
            return "Remove the %s menu" % q.plain_text(self.text)
        return "Remove %s" % q.plain_text(self.text)

    def apply(self, doc: UiDocument, ctx: PlanContext) -> Tuple[str, ...]:
        ref = doc.get(self.ref)
        if not isinstance(ref, ActionRefNode):
            raise CommandRejected("That entry is no longer in the form.")
        host = doc.parent(ref.id)
        host_id = host.id if host is not None else None
        name = ref.name
        still_on: Tuple[str, ...] = ()
        if name == q.SEPARATOR:
            planning.delete_nodes(doc, ctx, (ref.id,))
        else:
            found = doc.by_name(name)
            target = doc.get(found[0]) if found else None
            if isinstance(target, WidgetNode) and target.class_name == "QMenu":
                gone_actions = []
                for menu_id in q.menus_below(doc, target.id):
                    for entry in q.entries(doc, menu_id):
                        if entry.kind == "action" and entry.name not in gone_actions:
                            gone_actions.append(entry.name)
                planning.delete_nodes(doc, ctx, (target.id,))
                _drop_unused(doc, ctx, gone_actions)
            else:
                planning.delete_nodes(doc, ctx, (ref.id,))
                if found:
                    if q.is_used(doc, name):
                        still_on = tuple(sorted({q.host_phrase(doc, place.host) for place in q.places_of(doc, name)}))
                    else:
                        _drop_unused(doc, ctx, [name])
        if host_id is not None and doc.contains(host_id):
            ctx.select((host_id,), host_id)
        return still_on


@dataclass(frozen=True)
class MoveEntry(_CommandBase):
    """Move a reference to a place (UX-MAIN-009). ``copy`` adds a second reference instead."""

    command_type: ClassVar[str] = "move_entry"
    _label_text: ClassVar[str] = "Move entry"
    ref: NodeId
    host: NodeId
    #: Position in the target as the user saw it before the move.
    index: int
    copy: bool = False
    text: str = ""
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        shown = q.plain_text(self.text)
        return "Add %s" % shown if self.copy else "Move %s" % shown

    def apply(self, doc: UiDocument, ctx: PlanContext) -> NodeId:
        ref = doc.get(self.ref)
        if not isinstance(ref, ActionRefNode):
            raise CommandRejected("That entry is no longer in the form.")
        old_host = doc.parent(ref.id)
        host = _host(doc, self.host, None, "Actions go on a menu or a toolbar.")
        _check_index(doc, host.id, self.index)
        found = doc.by_name(ref.name) if ref.name != q.SEPARATOR else ()
        target = doc.get(found[0]) if found else None
        is_menu = isinstance(target, WidgetNode) and target.class_name == "QMenu"
        if is_menu:
            if host.class_name not in ("QMenuBar", "QMenu"):
                raise CommandRejected("Menus hold actions. Type a menu entry instead.")
            if self.copy:
                raise CommandRejected("A menu can only be in one place.")
            if doc.is_ancestor(target.id, host.id) or target.id == host.id:  # type: ignore[union-attr]
                raise CommandRejected("A menu can't go inside itself.")
        if self.copy:
            new_ref = planning.add_action_ref(doc, ctx, InActionList(host.id, self.index), ref.name)
            ctx.select((new_ref,), new_ref)
            return new_ref
        index = self.index
        if old_host is not None and old_host.id == host.id and ref.slot_index < index:
            index -= 1
        if old_host is not None and old_host.id == host.id and index == ref.slot_index:
            return ref.id
        ctx.do(MoveNodeOp(ref.id, host.id, "add_actions", index))
        if is_menu and old_host is not None and old_host.id != host.id:
            before = sum(1 for entry in q.entries(doc, host.id)[:index] if entry.kind == "menu")
            ctx.do(MoveNodeOp(target.id, host.id, "children", before))  # type: ignore[union-attr]
        ctx.select((ref.id,), ref.id)
        return ref.id


@dataclass(frozen=True)
class RenameEntry(_CommandBase):
    """Change the text of an entry (an action's ``text``) or a menu's ``title``."""

    command_type: ClassVar[str] = "rename_entry"
    _label_text: ClassVar[str] = "Change text"
    ref: NodeId
    text: str
    #: The old text and the action's name: the undo name.
    previous: str = ""
    kind: str = "action"
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        if self.kind == "menu":
            return "Rename menu %s to %s" % (q.plain_text(self.previous), q.plain_text(self.text))
        return "Change text of %s" % (self.previous or "the action")

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        ref = doc.get(self.ref)
        if not isinstance(ref, ActionRefNode) or ref.name == q.SEPARATOR:
            raise CommandRejected("That entry has no text.")
        found = doc.by_name(ref.name)
        if not found:
            raise CommandRejected("That entry is no longer in the form.")
        node = doc.node(found[0])
        if isinstance(node, WidgetNode):
            planning.set_property(doc, ctx, node.id, "title", StringValue(self.text))
        else:
            planning.set_property(doc, ctx, node.id, "text", StringValue(self.text))
        ctx.select((node.id,), node.id)


def _widget(class_name: str, name: str) -> NodeSpec:
    return NodeSpec("widget", None, (("class_name", class_name), ("object_name", name)))


def _host(doc: UiDocument, host_id: NodeId, classes: Optional[Tuple[str, ...]], refusal: str) -> WidgetNode:
    node = doc.get(host_id)
    if not isinstance(node, WidgetNode):
        raise CommandRejected("That object is no longer in the form.")
    if classes is not None and node.class_name not in classes:
        raise CommandRejected(refusal)
    return node


def _check_index(doc: UiDocument, host: NodeId, index: int) -> None:
    count = len(q.refs_of(doc, host))
    if index < 0 or index > count:
        raise CommandRejected("That position is outside the menu.")


def _drop_unused(doc: UiDocument, ctx: PlanContext, names: "list[str]") -> None:
    for name in names:
        found = doc.by_name(name)
        if not found:
            continue
        node = doc.node(found[0])
        if isinstance(node, ActionNode) and not q.is_used(doc, name):
            planning.delete_nodes(doc, ctx, (node.id,))


__all__ = [
    "NOT_A_MAIN_WINDOW",
    "AddEntry",
    "AddMainWindowPart",
    "AddMenu",
    "AddSeparator",
    "MoveEntry",
    "RemoveEntry",
    "RemoveMainWindowPart",
    "RenameEntry",
    "register",
]
