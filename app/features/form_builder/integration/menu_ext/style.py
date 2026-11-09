"""Edit style sheet… on the canvas and outline menus (UX-STYLE-001)."""

from __future__ import annotations

from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.integration.menu_ext import MenuContext
from app.features.form_builder.qtside.style import gateway


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if add is None:
        return
    add("last", build)


def build(ctx: MenuContext) -> None:
    current = ctx.current
    if current is None or len(ctx.ids) > 1:
        return
    node = ctx.session.document.get(current)
    if not isinstance(node, WidgetNode):
        return
    action = ctx.menu.addAction("Edit style sheet…")
    action.triggered.connect(lambda _checked=False: gateway.open_drawer(ctx.session, current))
