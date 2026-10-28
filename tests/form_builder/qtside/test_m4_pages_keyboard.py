# pyright: reportAttributeAccessIssue=false
"""K10 Pages (UX_SPEC 12.3), the steps that do not need the Pages menu.

The Shift+F10 Pages steps wait for M4.0s's menu registry and the outline
row keys; they are not here. Covered: Ctrl+PgUp shows page 2 with the
start-page sentence and no change to the file; "Start on this page" is a
single currentIndex change; deleting a page with widgets is one undo step
and undo returns the original bytes.
"""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.commands.catalog_ext.pages import DeletePage, InsertPage
from app.features.form_builder.engine.query.pages import page_widget_count, pages
from app.features.form_builder.engine.ui4.values import NumberValue
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.integration.canvas import FormCanvas
from app.qt.QtWidgets import QWidget
from tests.form_builder.engine.commands._support import open_log, saved
from tests.form_builder.qtside.support import opened
from tests.form_builder.qtside.test_m4_pages_canvas import TABS, _Host, _click, _press_key, _shown_index

pytestmark = pytest.mark.usefixtures("qapp")


def test_k10_ctrl_page_up_then_start_on_this_page_then_delete_and_undo() -> None:
    host = _Host()
    log = open_log(TABS)
    doc = log.document
    tabs = doc.by_name("tabs")[0]
    original = saved(doc)
    log.execute(InsertPage(tabs))  # the "Insert page after" of the last page (UX-CONT-003)
    assert len(pages(doc, tabs)) == 3
    with opened(saved(doc)) as (session, realizer):
        parent = QWidget()
        parent.resize(640, 480)
        canvas = FormCanvas(session, realizer, host, parent)
        canvas.resize(640, 480)
        parent.show()
        canvas.setFocus()
        _click(canvas, "inside_a")
        before = saved(session.document)
        dirty = session.log.is_dirty()
        _press_key(canvas, "Key_PageUp", "ControlModifier")
        assert _shown_index(canvas, "tabs") == 2
        assert host.sentences[-1].startswith("Showing page 3 of 3")
        assert "the file still starts on page 1" in host.sentences[-1]
        assert saved(session.document) == before and session.log.is_dirty() == dirty
        canvas.dispose()
        parent.deleteLater()
    log.execute(SetProperty(tabs, "currentIndex", NumberValue(2)))  # "Start on this page"
    assert 'name="currentIndex"' in saved(doc)
    assert page_widget_count(doc, pages(doc, tabs)[1].id) == 1  # the Beta page holds inside_b: the confirm would ask
    log.execute(DeletePage(tabs, 1))
    assert [page.object_name for page in pages(doc, tabs)] == ["tab_a", "tab_3"]
    assert 'name="currentIndex"' in saved(doc) and "<number>1</number>" in saved(doc)  # still on the new page
    for _ in range(5):
        if log.can_undo():
            assert log.undo()
    assert saved(doc) == original
