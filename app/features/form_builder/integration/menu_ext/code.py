"""Canvas and outline: Write code for the widget's default event."""

from __future__ import annotations

from app.features.form_builder.integration.activate_ext.handlers import claims, menu_title, write_for
from app.features.form_builder.integration.menu_ext import MenuContext


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if add is None:
        return
    add("first", build)


def build(ctx: MenuContext) -> None:
    if ctx.current is None or len(ctx.ids) != 1:
        return
    title = menu_title(ctx.session.document, ctx.current)
    if not title or claims(ctx.session.document, ctx.current) is None:
        return
    surface = _surface(ctx.menu)
    if surface is None:
        return
    ctx.menu.addAction(title, lambda: write_for(surface, ctx.current))


def _surface(menu: object) -> object:
    widget = getattr(menu, "parentWidget", lambda: None)()
    while widget is not None:
        if hasattr(widget, "session") and hasattr(widget, "code_bridge"):
            return widget
        widget = widget.parentWidget()
    window = getattr(menu, "window", lambda: None)()
    return window if hasattr(window, "session") else None
