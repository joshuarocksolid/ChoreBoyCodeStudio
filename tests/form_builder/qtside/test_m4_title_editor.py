# pyright: reportAttributeAccessIssue=false
"""Enter on a page opens the title editor on the storage the container reads (UX-CONT-008)."""

from __future__ import annotations

import pytest

from app.qt.QtTest import QTest
from app.qt.QtWidgets import QWidget
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.writer import write_ui
from tests.form_builder.qtside.support import form, opened
from tests.form_builder.qtside.test_canvas_text import _canvas, _flush, _open, _qt_key, _visible_edit

pytestmark = pytest.mark.usefixtures("qapp")

PAGES = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>600</width><height>400</height></rect></property>
  <widget class="QTabWidget" name="tabs">
   <property name="geometry"><rect><x>20</x><y>20</y><width>400</width><height>260</height></rect></property>
   <widget class="QWidget" name="tab_a"><attribute name="title"><string>Alpha</string></attribute></widget>
  </widget>
  <widget class="QToolBox" name="box">
   <property name="geometry"><rect><x>440</x><y>20</y><width>140</width><height>200</height></rect></property>
   <widget class="QWidget" name="page_a"><attribute name="label"><string>Basics</string></attribute></widget>
  </widget>
  <widget class="QWizard" name="wizard">
   <property name="geometry"><rect><x>20</x><y>300</y><width>500</width><height>80</height></rect></property>
   <widget class="QWizardPage" name="wizardPage_1"><property name="title"><string>Details</string></property></widget>
  </widget>
""",
)


def _stored(session, page_name: str, kind: str, prop: str) -> str:  # type: ignore[no-untyped-def]
    node = session.document.node(session.document.by_name(page_name)[0])
    entry = node.attr(prop) if kind == "attribute" else node.prop(prop)
    assert entry is not None
    return entry.value.text


@pytest.mark.parametrize(
    ("page", "kind", "prop"),
    [("tab_a", "attribute", "title"), ("page_a", "attribute", "label"), ("wizardPage_1", "property", "title")],
)
def test_enter_on_a_page_edits_its_title_and_one_undo_step_restores_it(page, kind, prop) -> None:  # type: ignore[no-untyped-def]
    with opened(PAGES) as (session, realizer):
        canvas, parent = _canvas(session, realizer)
        node = session.document.by_name(page)[0]
        session.selection.set((node,), current=node, source=SelectionSource.CANVAS)
        _flush()
        original = _stored(session, page, kind, prop)
        edit = _open(canvas)
        QTest.keyClicks(edit, "Printing")
        QTest.keyClick(edit, _qt_key("Key_Return"))
        _flush()
        assert _stored(session, page, kind, prop) == "Printing"
        assert session.log.undo_label() == "Change text"
        assert session.log.undo()
        assert _stored(session, page, kind, prop) == original
        assert _visible_edit(canvas) is None
        canvas.dispose()
        parent.deleteLater()
