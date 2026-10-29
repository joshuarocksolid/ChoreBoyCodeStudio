"""Curated rows for the main-window parts (UX-MAIN-013, R3 138, 143).

Menu: title, tear-off and tooltips. Menu bar: native menu bar. Toolbar: side,
new row, button style, can move, can float. Status bar: size grip and a caption.
Action rows (UX-MAIN-012): Content (text, picture, shortcut, tooltip, status tip, help
text) and Input (can be ticked, starts ticked, enabled, visible, where the shortcut works,
group). Action group rows (UX-MAIN-019): only one on at a time, enabled, visible.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from app.features.form_builder.engine.commands.catalog_ext.actions import SetActionGroup
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query import actions as q
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import ActionNode
from app.features.form_builder.engine.ui4.values import BoolValue, EnumValue
from app.features.form_builder.qtside.inspector.api import (
    Choice,
    EditorHost,
    EditorKey,
    GroupId,
    Note,
    Prop,
    Registrar,
    RowSpec,
    RowValue,
    Summary,
)
from app.qt.QtWidgets import QComboBox, QWidget

STATUS_BAR_CAPTION = (
    "Status tips of actions and widgets show here while the pointer is on them. "
    "Your code can show other messages."
)
_CONTENT = GroupId.CONTENT
_INPUT = GroupId.INPUT
STATUS_TIP_CAPTION = "Shows in the status bar while the pointer is on it."
GROUP_EDITOR = EditorKey("actionGroup")


def _sides(_document: UiDocument, _owners: Tuple[NodeId, ...]) -> Tuple[Choice, ...]:
    return tuple(
        Choice(label, EnumValue("Qt::%sToolBarArea" % label)) for label in ("Top", "Bottom", "Left", "Right")
    )


def _button_styles(_document: UiDocument, _owners: Tuple[NodeId, ...]) -> Tuple[Choice, ...]:
    return (
        Choice("Icon only", EnumValue("Qt::ToolButtonIconOnly")),
        Choice("Text only", EnumValue("Qt::ToolButtonTextOnly")),
        Choice("Text beside icon", EnumValue("Qt::ToolButtonTextBesideIcon")),
        Choice("Text under icon", EnumValue("Qt::ToolButtonTextUnderIcon")),
    )


def _contexts(_document: UiDocument, _owners: Tuple[NodeId, ...]) -> Tuple[Choice, ...]:
    return (
        Choice("In this window", EnumValue("Qt::WindowShortcut")),
        Choice("In the focused widget", EnumValue("Qt::WidgetShortcut")),
        Choice("Anywhere in the app", EnumValue("Qt::ApplicationShortcut")),
    )


def _ticked(document: UiDocument, owners: Tuple[NodeId, ...]) -> bool:
    """"Starts ticked" shows only while "Can be ticked" is on."""
    for owner in owners:
        node = document.get(owner)
        value = node.value("checkable") if node is not None else None
        if not (isinstance(value, BoolValue) and value.value):
            return False
    return True


def _action_rows() -> Tuple[RowSpec, ...]:
    on = ("QAction",)
    return (
        RowSpec("action.text", _CONTENT, "Text", "What the menu or button says. Put & before a letter to open it with Alt and that letter.", Prop("text"), classes=on),
        RowSpec("action.icon", _CONTENT, "Icon", "A small picture beside the text.", Prop("icon"), classes=on),
        RowSpec("action.shortcut", _CONTENT, "Shortcut", "A key that runs it.", Prop("shortcut"), classes=on),
        RowSpec("action.toolTip", _CONTENT, "Tooltip", "Shown when the pointer rests on it.", Prop("toolTip"), classes=on),
        RowSpec("action.statusTip", _CONTENT, "Status tip", STATUS_TIP_CAPTION, Prop("statusTip"), classes=on),
        RowSpec("action.statusTipNote", _CONTENT, "", STATUS_TIP_CAPTION, Note(STATUS_TIP_CAPTION), classes=on, after="action.statusTip"),
        RowSpec("action.whatsThis", _CONTENT, "Help text", "Help shown by the What's This tool.", Prop("whatsThis"), classes=on),
        RowSpec("action.checkable", _INPUT, "Can be ticked", "It shows a tick that the user switches on and off.", Prop("checkable"), classes=on),
        RowSpec("action.checked", _INPUT, "Starts ticked", "Whether the tick starts on.", Prop("checked"), classes=on, visible=_ticked),
        RowSpec("action.enabled", _INPUT, "Enabled", "Off greys it out.", Prop("enabled"), classes=on),
        RowSpec("action.visible", _INPUT, "Visible", "Off hides it.", Prop("visible"), classes=on),
        RowSpec("action.shortcutContext", _INPUT, "Shortcut works", "Where the key runs it.", Prop("shortcutContext"), classes=on, choices=_contexts),
        RowSpec("action.group", _INPUT, "Group", "A choice group makes the actions in it switch each other off.", Summary(), classes=on, editor=GROUP_EDITOR),
        RowSpec("actionGroup.exclusive", _INPUT, "Only one on at a time", "Ticking one switches the others off.", Prop("exclusive"), classes=("QActionGroup",)),
        RowSpec("actionGroup.enabled", _INPUT, "Enabled", "Off greys out every action in the group.", Prop("enabled"), classes=("QActionGroup",)),
        RowSpec("actionGroup.visible", _INPUT, "Visible", "Off hides every action in the group.", Prop("visible"), classes=("QActionGroup",)),
    )


class ActionGroupEditor:
    """The Group drop-down: the form's action groups and None (UX-MAIN-012, 019)."""

    def __init__(self, spec: object, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._box = QComboBox(parent)
        self._box.setObjectName("formBuilder.actionGroup")
        self._box.setAccessibleName("Group")
        self._names: List[Optional[str]] = []
        self._shown: Optional[str] = None
        self._loading = False
        self._box.activated.connect(self._picked)

    @property
    def widget(self) -> QWidget:
        return self._box

    def show(self, value: RowValue) -> None:
        del value
        doc = self._host.document()
        owners = self._host.owner_ids()
        node = doc.get(owners[0]) if len(owners) == 1 else None
        groups = [str(g.field("name")) for g in q.action_groups(doc)]
        self._names = [None] + groups
        self._shown = q.group_of(doc, node) if isinstance(node, ActionNode) else None
        self._loading = True
        try:
            self._box.clear()
            self._box.addItem("None")
            for name in groups:
                self._box.addItem(name)
            self._box.setCurrentIndex(self._names.index(self._shown) if self._shown in self._names else 0)
            self._box.setEnabled(node is not None)
        finally:
            self._loading = False

    def _picked(self, index: int) -> None:
        owners = self._host.owner_ids()
        if self._loading or len(owners) != 1 or not 0 <= index < len(self._names):
            return
        name = self._names[index]
        if name == self._shown:
            return
        doc = self._host.document()
        node = doc.get(owners[0])
        text = q.plain_text(q.text_of(node)) if node is not None else ""
        session = self._host.begin_session("Change group of %s" % (text or "action"))
        try:
            session.run([SetActionGroup(owners[0], name)])
        finally:
            session.close()


def register(registrar: Registrar) -> None:
    registrar.editor(GROUP_EDITOR, ActionGroupEditor)
    rows = _action_rows() + (
        RowSpec("menuTitle", _CONTENT, "Title", "The menu's title. Put & before a letter to open it with Alt and that letter.", Prop("title"), classes=("QMenu",)),
        RowSpec("menuIcon", _CONTENT, "Icon", "A picture beside the menu's title in a submenu.", Prop("icon"), classes=("QMenu",)),
        RowSpec("tearOff", _CONTENT, "Tear-off", "A dashed line at the top lets the user drag the menu out as a small window.", Prop("tearOffEnabled"), classes=("QMenu",)),
        RowSpec("menuTips", _CONTENT, "Shows tooltips", "Entries show their tooltip while the pointer rests on them.", Prop("toolTipsVisible"), classes=("QMenu",)),
        RowSpec("nativeMenuBar", _CONTENT, "Native menu bar", "Only matters on macOS.", Prop("nativeMenuBar"), classes=("QMenuBar",)),
        RowSpec(
            "toolbarSide",
            _CONTENT,
            "Toolbar side",
            "Which edge of the window the toolbar starts on.",
            Prop("toolBarArea", "attribute"),
            classes=("QToolBar",),
            choices=_sides,
        ),
        RowSpec("toolbarBreak", _CONTENT, "Starts on a new row", "The toolbar starts a new row on its side.", Prop("toolBarBreak", "attribute"), classes=("QToolBar",)),
        RowSpec(
            "toolbarStyle",
            _CONTENT,
            "Button style",
            "Whether the buttons show an icon, text, or both.",
            Prop("toolButtonStyle"),
            classes=("QToolBar",),
            choices=_button_styles,
        ),
        RowSpec("toolbarMovable", _CONTENT, "Can move", "The user can drag the toolbar to another place.", Prop("movable"), classes=("QToolBar",)),
        RowSpec("toolbarFloatable", _CONTENT, "Can float", "The user can drag the toolbar out of the window.", Prop("floatable"), classes=("QToolBar",)),
        RowSpec("sizeGrip", _CONTENT, "Size grip", "A small grip at the right end that resizes the window.", Prop("sizeGripEnabled"), classes=("QStatusBar",)),
        RowSpec("statusBarCaption", _CONTENT, "Messages", STATUS_BAR_CAPTION, Note(STATUS_BAR_CAPTION), classes=("QStatusBar",)),
    )
    for spec in rows:
        registrar.row(spec, baseline=True)
