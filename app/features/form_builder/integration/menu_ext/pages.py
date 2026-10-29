"""Pages submenu (UX-CONT-002).

Acts on the innermost page container of the clicked widget. Disabled rows
keep their reason as the tooltip. ``run`` sends an engine command. Show,
tile and cascade are canvas-only and go through the form canvas.
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from app.features.form_builder.engine.commands.catalog import MovePage, SetProperty
from app.features.form_builder.engine.commands.catalog_ext.pages import START_PAGE_LABEL, DeletePage, InsertPage
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.pages import (
    PageKind,
    innermost_container,
    page_kind,
    page_title,
    page_widget_count,
    pages,
    start_index,
)
from app.features.form_builder.engine.ui4.values import NumberValue
from app.features.form_builder.integration.menu_ext import MenuContext
from app.qt.QtCore import QRect
from app.qt.QtWidgets import QWidget

_NOUN = {"tab": "tab", "wizard": "step"}


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if add is None:
        return
    add("first", build)


def build(ctx: MenuContext) -> None:
    document = ctx.session.document
    current = ctx.current
    if current is None or not document.contains(current):
        return
    container = innermost_container(document, current)
    if container is None:
        return
    kind = page_kind(document, container)
    if kind is None:
        return
    found = pages(document, container)
    shown = _clamp(_shown(ctx, container, kind), len(found))
    page = found[shown] if found else None
    title = page_title(document, page.id) if page is not None else ""
    if not title and page is not None:
        title = page.object_name or "page"
    menu = ctx.menu.addMenu("Pages")
    menu.setToolTipsVisible(True)
    count = len(found)
    if kind.kind == "mdi":
        _item(menu, "Add window", True, "", lambda: ctx.run(InsertPage(container)))
    else:
        noun = _NOUN.get(kind.kind, "page")
        _item(
            menu,
            "Insert %s before \u201c%s\u201d" % (noun, title or "page"),
            count > 0,
            "" if count > 0 else "This container has no pages.",
            lambda: ctx.run(InsertPage(container, shown)),
        )
        _item(
            menu,
            "Insert %s after \u201c%s\u201d" % (noun, title or "page"),
            True,
            "",
            lambda: ctx.run(InsertPage(container, shown + 1 if count else 0)),
        )
    asking = page is not None and page_widget_count(document, page.id) > 0
    _item(
        menu,
        "Delete page \u201c%s\u201d%s" % (title or "page", "\u2026" if asking else ""),
        page is not None,
        "" if page is not None else "This container has no pages.",
        lambda: _delete(ctx, container, shown, asking),
    )
    earlier, later = ("Move tab left", "Move tab right") if kind.kind == "tab" else ("Move page up", "Move page down")
    if count == 0:
        first_reason = last_reason = "This container has no pages."
    else:
        first_reason = "" if shown > 0 else "This is already the first page."
        last_reason = "" if shown < count - 1 else "This is already the last page."
    _item(menu, earlier, shown > 0, first_reason, lambda: ctx.run(MovePage(container, shown, shown - 1)))
    _item(menu, later, shown < count - 1, last_reason, lambda: ctx.run(MovePage(container, shown, shown + 1)))
    only = "This is the only page." if count == 1 else "This container has no pages."
    _item(menu, "Show previous page\tCtrl+PgUp", count > 1, "" if count > 1 else only, lambda: _show(ctx, container, -1))
    _item(menu, "Show next page\tCtrl+PgDown", count > 1, "" if count > 1 else only, lambda: _show(ctx, container, 1))
    if kind.has_start_page:
        start = start_index(document, container)
        action = menu.addAction("Start on this page")
        action.setCheckable(True)
        action.setChecked(start == shown and page is not None)
        action.setEnabled(page is not None and start != shown)
        if page is None:
            action.setToolTip("This container has no pages.")
        elif start == shown:
            action.setToolTip("This page is already the start page.")
        else:
            action.triggered.connect(lambda _checked=False: ctx.run(SetProperty(container, "currentIndex", NumberValue(shown), undo_label=START_PAGE_LABEL)))
    if kind.kind == "mdi":
        _item(menu, "Tile windows", count > 1, "" if count > 1 else only, lambda: _arrange(ctx, container, "tile"))
        _item(menu, "Cascade windows", count > 1, "" if count > 1 else only, lambda: _arrange(ctx, container, "cascade"))


def _item(menu: object, label: str, enabled: bool, reason: str, run: Callable[[], None]) -> None:
    action = menu.addAction(label)  # type: ignore[attr-defined]
    action.setEnabled(enabled)
    if not enabled and reason:
        action.setToolTip(reason)
    if enabled:
        action.triggered.connect(lambda _checked=False: run())


def _delete(ctx: MenuContext, container: NodeId, index: int, asking: bool) -> None:
    command = DeletePage(container, index)
    if not asking:
        ctx.run(command)
        return
    surface = _surface(ctx)
    if surface is None:
        return
    outline = getattr(getattr(surface, "_workbench", None), "outline", None)
    page = pages(ctx.session.document, container)[index]
    title = page_title(ctx.session.document, page.id) or page.object_name or "page"
    count = page_widget_count(ctx.session.document, page.id)
    noun = "widget" if count == 1 else "widgets"
    prose = "Delete page \u201c%s\u201d and the %d %s on it?" % (title, count, noun)
    anchor = None if ctx.source == "outline" else _tab_anchor(ctx, page.id)
    if anchor is None or outline is None:
        surface.ask_delete(prose, (page.id,))
        return
    outline.show_delete(
        prose,
        (page.id,),
        anchor,
        getattr(surface, "_focus_canvas", None),
        _chip_blocks(ctx),
    )


def _chip_blocks(ctx: MenuContext) -> Tuple[QRect, ...]:
    """Selection chips in global coordinates, so the confirm can sit clear of them."""
    canvas = _canvas(ctx)
    blocks = getattr(canvas, "overlay_block_rects", None)
    if canvas is None or blocks is None:
        return ()
    viewport = canvas.viewport()
    return tuple(QRect(viewport.mapToGlobal(rect.topLeft()), rect.size()) for rect in blocks())


def _tab_anchor(ctx: MenuContext, page_id: NodeId) -> Optional[QRect]:
    """The page tab in global coordinates, when the canvas has drawn one."""
    canvas = _canvas(ctx)
    locate = getattr(canvas, "tab_viewport_rect", None)
    if canvas is None or locate is None:
        return None
    local = locate(page_id)
    if local is None:
        return None
    viewport = canvas.viewport()
    return QRect(viewport.mapToGlobal(local.topLeft()), local.size())


def _show(ctx: MenuContext, container: NodeId, delta: int) -> None:
    canvas = _canvas(ctx)
    if canvas is not None:
        canvas.show_container_page(container, delta)


def _arrange(ctx: MenuContext, container: NodeId, how: str) -> None:
    canvas = _canvas(ctx)
    if canvas is not None:
        canvas.arrange_windows(container, how)


def _shown(ctx: MenuContext, container: NodeId, kind: PageKind) -> int:
    found = pages(ctx.session.document, container)
    widget = ctx.live(container)
    if widget is None or not found:
        start = start_index(ctx.session.document, container)
        return 0 if start is None else start
    if kind.kind == "wizard" and hasattr(widget, "pageIds"):
        ids = list(widget.pageIds())
        current = widget.currentId() if hasattr(widget, "currentId") else -1
        return ids.index(current) if current in ids else 0
    if kind.kind == "mdi" and hasattr(widget, "activeSubWindow"):
        active = widget.activeSubWindow()
        inner = None if active is None else active.widget()
        name = "" if inner is None else str(inner.objectName())
        for index, page in enumerate(found):
            if page.object_name == name:
                return index
        return 0
    if hasattr(widget, "currentIndex"):
        return int(widget.currentIndex())
    return 0


def _clamp(index: int, count: int) -> int:
    if count <= 0:
        return 0
    return max(0, min(count - 1, index))


def _surface(ctx: MenuContext) -> Optional[QWidget]:
    widget: Optional[QWidget] = ctx.menu
    while widget is not None:
        if callable(getattr(widget, "ask_delete", None)):
            return widget
        widget = widget.parentWidget()
    return None


def _canvas(ctx: MenuContext) -> Optional[QWidget]:
    surface = _surface(ctx)
    workbench = getattr(surface, "_workbench", None) if surface is not None else None
    canvas = getattr(workbench, "canvas", None) if workbench is not None else None
    if canvas is not None and hasattr(canvas, "show_container_page"):
        return canvas
    widget: Optional[QWidget] = ctx.menu
    while widget is not None:
        if hasattr(widget, "show_container_page"):
            return widget
        widget = widget.parentWidget()
    return None


__all__: Tuple[str, ...] = ("build", "register")
