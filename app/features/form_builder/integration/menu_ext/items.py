"""Edit items… on the canvas and outline menus (UX-ITEM-001)."""

from __future__ import annotations

from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.integration.menu_ext import MenuContext
from app.features.form_builder.qtside.items.editor import open_editor
from app.features.form_builder.qtside.items.model import ITEM_CLASSES
from app.qt.QtCore import QRect


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if add is None:
        return
    # The widget's own main action leads the menu, above the clipboard rows.
    add("first", build)


def build(ctx: MenuContext) -> None:
    current = ctx.current
    if current is None:
        return
    node = ctx.session.document.get(current)
    if not isinstance(node, WidgetNode) or node.class_name not in ITEM_CLASSES:
        return
    action = ctx.menu.addAction("Edit items\u2026")
    action.triggered.connect(lambda _checked=False: _open(ctx))


def _open(ctx: MenuContext) -> None:
    current = ctx.current
    if current is None:
        return
    live = ctx.live(current)
    beside = None
    if live is not None:
        rect = live.rect()
        beside = QRect(live.mapToGlobal(rect.topLeft()), rect.size())
    parent = None if live is None else live.window()
    open_editor(ctx.session, current, parent, beside=beside)
