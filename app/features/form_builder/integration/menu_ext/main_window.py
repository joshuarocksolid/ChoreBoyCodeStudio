"""Context menu rows for main windows, actions and button groups (UX-MAIN-002, 017, 019).

On the page of a main window: Add menu bar, Add toolbar, Add status bar. On a
bar or toolbar: its Remove row. On two or more buttons: Make a button group.
On any widget of a form that has actions: Actions ▸ with a check item each.
"""

from __future__ import annotations

from typing import Tuple

from app.features.form_builder.engine.commands.catalog_ext.actions import (
    MakeButtonGroup,
    SetWidgetAction,
    UngroupButtons,
)
from app.features.form_builder.engine.commands.catalog_ext.main_window import AddMainWindowPart, RemoveMainWindowPart
from app.features.form_builder.engine.query import actions as q
from app.features.form_builder.engine.layout_actions import NeedsConfirm
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.integration.menu_ext import MenuContext
from app.features.form_builder.qtside.layout_gestures import ask
from app.qt.QtCore import QPoint, QRect

_BUTTONS = frozenset({"QPushButton", "QToolButton", "QRadioButton", "QCheckBox", "QCommandLinkButton"})
_REMOVE = {"QMenuBar": "Remove menu bar…", "QToolBar": "Remove toolbar", "QStatusBar": "Remove status bar"}


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if add is None:
        return
    add("structure", build)


def build(ctx: MenuContext) -> None:
    doc = ctx.session.document
    current = ctx.current
    if current is None or not doc.contains(current):
        return
    node = doc.node(current)
    if not isinstance(node, WidgetNode):
        return
    if node.id == doc.root.id and q.is_main_window(doc):
        found = q.parts(doc)
        menu = ctx.menu.addMenu("Main window")
        if not found["menubar"]:
            menu.addAction("Add menu bar").triggered.connect(lambda: ctx.run(AddMainWindowPart("menubar")))
        menu.addAction("Add toolbar").triggered.connect(lambda: ctx.run(AddMainWindowPart("toolbar")))
        if not found["statusbar"]:
            menu.addAction("Add status bar").triggered.connect(lambda: ctx.run(AddMainWindowPart("statusbar")))
    if node.class_name in _REMOVE and q.is_main_window(doc):
        ctx.menu.addAction(_REMOVE[node.class_name]).triggered.connect(lambda: _remove(ctx, node))
    _button_groups(ctx, node)
    _widget_actions(ctx, node)


def _remove(ctx: MenuContext, node: WidgetNode) -> None:
    doc = ctx.session.document
    if node.class_name == "QMenuBar":
        count = len([e for e in q.entries(doc, node.id) if e.kind == "menu"])
        if count:
            parent = ctx.menu.window() or ctx.menu
            at = ctx.at
            if at is None:
                at = parent.mapToGlobal(QPoint(parent.width() // 2, 12))
            subject = QRect(at.x(), at.y(), 8, 8)
            bounds = parent.frameGeometry()
            question = ask(parent, None, lambda: (subject, bounds))
            if not question(
                NeedsConfirm(
                    "Remove the menu bar and its %d menus? Actions stay in the Actions list." % count,
                    "Remove menu bar",
                )
            ):
                return
    ctx.run(RemoveMainWindowPart.for_part(doc, node.id))


def _selected_buttons(ctx: MenuContext) -> Tuple:
    doc = ctx.session.document
    found = []
    for node_id in ctx.ids:
        node = doc.get(node_id)
        if isinstance(node, WidgetNode) and node.class_name in _BUTTONS:
            found.append(node_id)
    return tuple(found)


def _button_groups(ctx: MenuContext, node: WidgetNode) -> None:
    buttons = _selected_buttons(ctx)
    if len(buttons) >= 2:
        ctx.menu.addAction("Make a button group").triggered.connect(lambda: ctx.run(MakeButtonGroup(buttons)))
    attr = node.attr("buttonGroup")
    if attr is not None and isinstance(attr.value, StringValue):
        name = attr.value.text
        ctx.menu.addAction("Ungroup buttons").triggered.connect(lambda: ctx.run(UngroupButtons(name)))


def _widget_actions(ctx: MenuContext, node: WidgetNode) -> None:
    doc = ctx.session.document
    if node.class_name in ("QMenuBar", "QMenu", "QToolBar", "QStatusBar") or node.id == doc.root.id:
        return
    infos = q.list_actions(doc)
    if not infos:
        return
    menu = ctx.menu.addMenu("Actions")
    on = {ref.name for ref in q.refs_of(doc, node.id)}
    for info in infos:
        item = menu.addAction(q.plain_text(info.text) or info.name)
        item.setCheckable(True)
        item.setChecked(info.name in on)
        item.triggered.connect(
            lambda checked, name=info.name: ctx.run(SetWidgetAction(node.id, name, bool(checked), node.object_name))
        )
