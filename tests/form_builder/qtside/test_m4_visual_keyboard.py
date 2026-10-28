# pyright: reportAttributeAccessIssue=false
"""K13. Font and palette popovers, one undo step, Esc reverts (UX_SPEC §12.3)."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.qtside.inspector import InspectorPane
from app.features.form_builder.qtside.inspector.api import GroupId
from app.features.form_builder.qtside.theme.chrome import chrome_from_values
from app.qt.QtCore import Qt
from app.qt.QtGui import QFontDatabase
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLineEdit, QPushButton, QVBoxLayout, QWidget
from tests.form_builder.qtside.support import realize

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]


@pytest.fixture(autouse=True)
def _private_recent_colours(tmp_path):
    """Recent colours go to a scratch settings root, never the user's."""
    from app.features.form_builder.integration.editor_memory import use_state_root

    use_state_root(str(tmp_path))
    yield
    use_state_root(None)

_CHROME = chrome_from_values(
    window="#f3f3f3",
    panel="#ffffff",
    text="#1f1f1f",
    muted="#5c5c5c",
    faint="#6b6b6b",
    border="#c8c8c8",
    accent="#0060c0",
    row_hover="#eef3fb",
    input_bg="#ffffff",
    error="#b00020",
    focus_width=1,
)

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QLabel" name="title"><property name="text"><string>Title</string></property></widget></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _visible(name: str) -> QWidget:
    found = [widget for widget in QApplication.allWidgets() if widget.objectName() == name and widget.isVisible()]
    assert found, name
    return found[-1]


def _tab_until(name: str, qapp: QApplication, limit: int = 12) -> QWidget:
    seen = []
    for _step in range(limit):
        focus = QApplication.focusWidget()
        seen.append(None if focus is None else focus.objectName() or type(focus).__name__)
        if focus is not None and focus.objectName() == name:
            return focus
        if focus is not None:
            QTest.keyClick(focus, Qt.Key.Key_Tab)
        qapp.processEvents()
    focus = QApplication.focusWidget()
    assert focus is not None and focus.objectName() == name, seen
    return focus


def test_k13_font_then_palette_escape_reverts_and_done_keeps(qapp: QApplication) -> None:
    families = [name for name in QFontDatabase.families() if "sans" in name.lower()]
    if not families:
        pytest.skip("no installed family contains Sans, so K13's family filter has no match")
    session, realizer = realize(_FORM)
    window = QWidget()
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    pane.apply_chrome(_CHROME)
    layout = QVBoxLayout(window)
    layout.addWidget(pane)
    window.resize(900, 700)
    window.show()
    qapp.processEvents()
    pane.set_group_expanded(GroupId.ALL, True)
    pane.set_group_expanded(GroupId.APPEARANCE, True)
    original = session.text()
    try:
        session.selection.set((session.document.by_name("title")[0],), source=SelectionSource.PROGRAM)
        pane.flush()
        font = pane.findChild(QWidget, "formBuilder.row.font")
        assert font is not None
        summary = font.findChild(QPushButton, "formBuilder.summary")
        assert summary is not None
        summary.click()
        qapp.processEvents()
        family = _visible("formBuilder.fontFamily")
        line = family.lineEdit()
        assert isinstance(line, QLineEdit)
        assert family.hasFocus() or line.hasFocus()
        QTest.keyClicks(line, "Sans")
        qapp.processEvents()
        QTest.keyClick(line, Qt.Key.Key_Return)
        qapp.processEvents()
        # The family popup closes on Enter and offscreen Qt drops focus. Put it back, then Tab.
        family = _visible("formBuilder.fontFamily")
        window.activateWindow()
        family.setFocus()
        qapp.processEvents()
        size = _tab_until("formBuilder.fontSize", qapp)
        QTest.keyClick(size, Qt.Key.Key_Up)
        QTest.keyClick(size, Qt.Key.Key_Up)
        qapp.processEvents()
        bold = _tab_until("formBuilder.fontBold", qapp)
        QTest.keyClick(bold, Qt.Key.Key_Space)
        qapp.processEvents()
        _visible("formBuilder.popoverDone").click()
        qapp.processEvents()
        assert len(session.log.entries()) == 1
        undo = session.log.undo_label()
        assert undo is not None and undo.startswith("Change font of ")
        shown = summary.toolTip() or summary.text()
        assert "Bold" in shown
        assert "pt" in shown
        assert "Sans" in shown
        after_font = session.text()

        palette = pane.findChild(QWidget, "formBuilder.row.palette")
        assert palette is not None
        palette.findChild(QPushButton, "formBuilder.summary").click()
        qapp.processEvents()
        roles = _visible("formBuilder.paletteRoles")
        roles.setFocus()
        QTest.keyClick(roles, Qt.Key.Key_Down)
        QTest.keyClick(roles, Qt.Key.Key_Return)
        qapp.processEvents()
        field = _tab_until("formBuilder.colorHex", qapp)
        QTest.keyClicks(field, "#1A7F37")
        QTest.keyClick(field, Qt.Key.Key_Return)
        qapp.processEvents()
        QTest.keyClick(field, Qt.Key.Key_Escape)
        qapp.processEvents()
        assert _visible("formBuilder.paletteRoles")
        QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Escape)
        qapp.processEvents()
        assert session.text() == after_font

        palette.findChild(QPushButton, "formBuilder.summary").click()
        qapp.processEvents()
        roles = _visible("formBuilder.paletteRoles")
        roles.setFocus()
        QTest.keyClick(roles, Qt.Key.Key_Down)
        QTest.keyClick(roles, Qt.Key.Key_Return)
        qapp.processEvents()
        field = _tab_until("formBuilder.colorHex", qapp)
        field.clear()
        QTest.keyClicks(field, "#1A7F37")
        QTest.keyClick(field, Qt.Key.Key_Return)
        qapp.processEvents()
        _visible("formBuilder.popoverDone").click()
        qapp.processEvents()
        kept = session.text()
        assert kept != original
        assert 'role="WindowText"' in kept
        while session.log.entries():
            assert session.log.undo() is True
        assert session.text() == original
    finally:
        pane.dispose()
        realizer.dispose()
        session.dispose()
        window.close()
        qapp.processEvents()
