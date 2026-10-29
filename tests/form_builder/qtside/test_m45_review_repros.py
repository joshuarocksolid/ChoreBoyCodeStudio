# pyright: reportAttributeAccessIssue=false
"""M4.5 review repros: bugs the M4 review found in the shop-owner walkthrough."""

from __future__ import annotations

import pytest

from app.features.form_builder.integration.insert_memory import InMemoryInsertMemory
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QWidget
from tests.form_builder.qtside.test_m4_insert_pane import _pane

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]


@pytest.mark.parametrize(("typed", "first"), [(("field",), "QLineEdit"), (("text", "number"), "QSpinBox")])
def test_enter_in_insert_search_takes_the_first_result_of_the_new_query(typed: tuple, first: str) -> None:
    """Typing kept the entry that matched an earlier prefix current, so Enter
    inserted the second result ("field" gave an input field, "number" an LCD)."""
    parent = QWidget()
    pane = _pane(parent, InMemoryInsertMemory())
    parent.show()
    for word in typed:
        pane.filter.setFocus()
        pane.filter.selectAll()
        QTest.keyClicks(pane.filter, word)
        QApplication.processEvents()
    assert pane.body.item(0).data(int(Qt.ItemDataRole.UserRole)) == first
    current = pane.current_row()
    assert current is not None and current.key == first


_COMBO = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QComboBox" name="currency">
     <item><property name="text"><string>USD</string></property></item>
     <item><property name="text"><string>CAD</string></property></item>
     <item><property name="text"><string>EUR</string></property></item>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def test_a_combo_starts_on_an_item_chosen_by_its_text(qapp: QApplication, tmp_path) -> None:
    """UX-ITEM-003: "Starts on" is an inspector row; before, only the raw 0-based currentIndex existed."""
    from app.qt.QtWidgets import QComboBox
    from tests.form_builder.inspector.test_m43c_pictures import _close, _pane, _select

    window, pane, session, realizer = _pane(qapp, _COMBO, str(tmp_path / "form.ui"))
    try:
        _select(session, "currency")
        pane.flush()
        row = pane.findChild(QWidget, "formBuilder.row.comboStartsOn")
        assert row is not None and row.isVisible()
        box = [item for item in row.findChildren(QComboBox) if item.isVisible()][0]
        texts = [box.itemText(index) for index in range(box.count())]
        assert [text for text in texts if text in ("USD", "CAD", "EUR")] == ["USD", "CAD", "EUR"]
        box.setCurrentIndex(texts.index("CAD"))
        qapp.processEvents()
        assert '<property name="currentIndex">' in session.text()
        assert "<number>1</number>" in session.text()
    finally:
        _close(window, pane, realizer, session, qapp)


def test_selecting_a_widget_on_a_hidden_page_from_the_outline_shows_that_page() -> None:
    """UX-CONT-006. The shop owner built a whole page while the canvas showed the other one."""
    from app.features.form_builder.engine.query.selection import SelectionSource
    from app.features.form_builder.engine.ui4.writer import write_ui
    from app.features.form_builder.integration.canvas import FormCanvas
    from tests.form_builder.qtside.support import opened
    from tests.form_builder.qtside.test_m4_pages_canvas import TABS, _Host, _shown_index

    with opened(TABS) as (session, realizer):
        parent = QWidget()
        parent.resize(640, 480)
        canvas = FormCanvas(session, realizer, _Host(), parent)
        canvas.resize(640, 480)
        parent.show()
        QApplication.processEvents()
        before = write_ui(session.document).text
        assert _shown_index(canvas, "tabs") == 0
        hidden = session.document.by_name("inside_b")[0]
        session.selection.set((hidden,), current=hidden, source=SelectionSource.OUTLINE)
        for _ in range(4):
            QApplication.processEvents()
        assert _shown_index(canvas, "tabs") == 1
        assert write_ui(session.document).text == before, "showing a page never writes the file"
        canvas.dispose()
        parent.deleteLater()
