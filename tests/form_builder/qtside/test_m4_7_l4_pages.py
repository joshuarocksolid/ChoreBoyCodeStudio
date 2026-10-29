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
