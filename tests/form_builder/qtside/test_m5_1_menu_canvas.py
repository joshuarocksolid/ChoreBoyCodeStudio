# pyright: reportAttributeAccessIssue=false
"""The canvas draws "Type here" and the open menu, and keys reach the editor (UX-MAIN-003, 004, 015)."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.project.templates import build_template_ui
from app.features.form_builder.engine.query import actions as q
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.qtside.actions.glue import MenuEditGlue
from app.features.form_builder.qtside.actions.paint_model import PaintState
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QWidget
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


def test_enter_on_the_menu_bar_types_a_menu_and_the_layer_shows_it_open() -> None:
    said = []
    with opened(build_template_ui("main_window", "shop_window")) as (session, realizer):
        parent = QWidget()
        parent.resize(900, 700)
        canvas = FormCanvas(session, realizer, _Host(), parent)
        canvas.resize(900, 700)
        parent.show()
        _pump()
        glue = MenuEditGlue(session, realizer, canvas, said.append, said.append, lambda s, o: True, parent)
        _pump()
        state = canvas.layer_state("menu_edit")
        assert isinstance(state, PaintState) and [i.text for i in state.items] == ["Type here", "Type here"][:len(state.items)]
        assert any(i.kind == "hint" for i in state.items)
        doc = session.document
        canvas.setFocus()
        session.selection.set((doc.by_name("menubar")[0],), source=SelectionSource.PROGRAM)
        target = canvas.viewport()
        QTest.keyClick(target, Qt.Key.Key_Return)
        assert glue.editor.active
        QTest.keyClicks(target, "File")
        state = canvas.layer_state("menu_edit")
        assert any(i.kind == "edit" and i.text == "File" for i in state.items)
        QTest.keyClick(target, Qt.Key.Key_Return)
        QTest.keyClick(target, Qt.Key.Key_Down)
        QTest.keyClicks(target, "Quit")
        QTest.keyClick(target, Qt.Key.Key_Return)
        _pump()
        assert "menuFile" in doc.names() and "actionQuit" in doc.names()
        state = canvas.layer_state("menu_edit")
        kinds = [i.kind for i in state.items]
        assert "box" in kinds and any(i.kind == "row" and i.text == "Quit" for i in state.items)
        QTest.keyClick(target, Qt.Key.Key_Escape)
        QTest.keyClick(target, Qt.Key.Key_Escape)
        assert not glue.editor.active
        assert [d.code for d in session.diagnostics.all() if d.code == "FB036"] == []
        glue.dispose()
        canvas.dispose()
        parent.deleteLater()
