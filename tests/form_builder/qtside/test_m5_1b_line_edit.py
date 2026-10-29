# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""The in-place menu editor is a real line edit (UX-MAIN-006, 007): caret and paste work, the keys reach the state machine."""

from __future__ import annotations

import time

import pytest

from app.features.form_builder.engine.project.templates import build_template_ui
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.qtside.actions.glue import MenuEditGlue
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLineEdit, QWidget
from tests.form_builder.qtside.support import opened

pytestmark = pytest.mark.usefixtures("qapp")


class _Host:
    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        return lambda *args, **kwargs: None


def _pump() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(4):
        app.processEvents()


def _line(canvas: FormCanvas) -> QLineEdit:
    found = canvas.viewport().findChild(QLineEdit, "formBuilder.menuEditLine")
    assert found is not None
    return found


@pytest.mark.pain("P-17")
def test_the_title_editor_is_a_line_edit_with_a_caret_and_the_reuse_list_names_its_row() -> None:
    said = []
    with opened(build_template_ui("main_window", "shop_window")) as (session, realizer):
        parent = QWidget()
        parent.resize(900, 700)
        canvas = FormCanvas(session, realizer, _Host(), parent)
        canvas.resize(900, 700)
        parent.show()
        _pump()
        glue = MenuEditGlue(session, realizer, canvas, said.append, said.append, lambda s, o: True, parent)
        doc = session.document
        canvas.setFocus()
        session.selection.set((doc.by_name("menubar")[0],), source=SelectionSource.PROGRAM)
        QTest.keyClick(canvas.viewport(), Qt.Key.Key_Return)  # menu editing, on Type here
        QTest.keyClick(canvas.viewport(), Qt.Key.Key_Return)  # an empty editor
        _pump()
        line = _line(canvas)
        assert line.hasFocus() and line.hasFrame() is False
        # The caret, Home and typing in the middle are the line edit's own.
        QTest.keyClicks(line, "Fle")
        QTest.keyClick(line, Qt.Key.Key_Left)
        QTest.keyClick(line, Qt.Key.Key_Left)
        QTest.keyClicks(line, "i")
        assert line.text() == "File" and glue.editor.editor.text == "File"
        QTest.keyClick(line, Qt.Key.Key_Home)
        QTest.keyClicks(line, "&")
        assert glue.editor.editor.text == "&File"
        started = time.perf_counter()
        QTest.keyClick(line, Qt.Key.Key_Return)
        _pump()
        assert "menuFile" in doc.names()
        assert time.perf_counter() - started < 0.5
        # Down opens File; a new editor opens on its Type here after Enter on it.
        QTest.keyClick(canvas.viewport(), Qt.Key.Key_Down)
        QTest.keyClick(canvas.viewport(), Qt.Key.Key_Return)
        _pump()
        line = _line(canvas)
        QTest.keyClicks(line, "Pri")
        _pump()
        assert glue.editor.reuse_phrase() == "New action “Pri”, 1 of 1"
        assert line.accessibleDescription() == "New action “Pri”, 1 of 1"
        assert "Type here" in canvas.accessibleDescription() or "entry" in canvas.accessibleDescription()
        QTest.keyClick(line, Qt.Key.Key_Tab)  # keeps "Pri" and opens the next editor
        _pump()
        assert "actionPri" in doc.names()
        assert _line(canvas).text() == ""
        QTest.keyClick(_line(canvas), Qt.Key.Key_Escape)
        _pump()
        assert canvas.viewport().findChild(QLineEdit, "formBuilder.menuEditLine") is None
        assert glue.editor.active
        glue.dispose()
        canvas.dispose()
        parent.deleteLater()
