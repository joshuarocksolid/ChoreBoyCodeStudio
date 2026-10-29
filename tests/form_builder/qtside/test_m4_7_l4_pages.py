# pyright: reportAttributeAccessIssue=false
"""L4: the "+" page chip follows the tab bar after a rename (UX-CONT-003)."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.qt.QtTest import QTest
from tests.form_builder.qtside.support import opened
from tests.form_builder.qtside.test_canvas_text import _canvas, _flush, _open, _qt_key
from tests.form_builder.qtside.test_m4_title_editor import PAGES

pytestmark = pytest.mark.usefixtures("qapp")


def test_plus_chip_clears_the_last_tab_after_a_longer_title() -> None:
    with opened(PAGES) as (session, realizer):
        canvas, parent = _canvas(session, realizer)
        tabs_id = session.document.by_name("tabs")[0]
        page = session.document.by_name("tab_a")[0]
        session.selection.set((page,), current=page, source=SelectionSource.CANVAS)
        _flush()
        edit = _open(canvas)
        QTest.keyClicks(edit, "A much longer title here")
        QTest.keyClick(edit, _qt_key("Key_Return"))
        _flush()
        bar = realizer.widget_for(tabs_id).tabBar()
        controller = canvas._controller
        controller._index.ensure_fresh()
        assert not controller._static_stale()
        mine = [rect for container, rect in controller._static.tabs if container == tabs_id]
        assert mine and max(rect.width for rect in mine) == bar.tabRect(0).width()
        canvas.dispose()
        parent.deleteLater()


def test_deleting_an_empty_page_from_the_menu_names_its_title(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.features.form_builder.engine.commands.catalog_ext.pages import InsertPage
    from app.features.form_builder.engine.query.pages import page_title, pages
    from app.features.form_builder.integration.menu_ext import MenuContext
    from app.features.form_builder.integration.menu_ext.pages import _delete
    from app.qt.QtWidgets import QLabel, QMenu
    from tests.form_builder.qtside.test_m4_pages_keyboard import _close, _surface

    parent, surface = _surface(tmp_path, "toast")
    try:
        document = surface.session.document
        tabs = document.by_name("tabs")[0]
        surface.session.log.execute(InsertPage(tabs))
        _flush()
        index = len(pages(document, tabs)) - 1
        page = pages(document, tabs)[index]
        title = page_title(document, page.id)
        assert title and title != page.object_name
        ctx = MenuContext(
            QMenu(surface), (), None, surface.session, lambda _name: None, run=surface.run_menu_request
        )
        _delete(ctx, tabs, index, False)
        _flush()
        texts = [label.text() for label in surface.findChildren(QLabel) if label.isVisible()]
        assert any("Deleted page “%s”" % title in text for text in texts), texts
        assert not any(page.object_name in text for text in texts), texts
    finally:
        _close(parent, surface)
