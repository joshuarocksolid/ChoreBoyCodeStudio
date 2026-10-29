# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""The canvas draws "Type here" and the open menu, and keys reach the editor (UX-MAIN-003, 004, 015)."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.project.templates import build_template_ui
from app.features.form_builder.engine.query import actions as q
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.qtside.actions.glue import MenuEditGlue
from app.features.form_builder.qtside.actions.paint_model import PaintState
from app.features.form_builder.qtside.canvas.layers.menu_edit import build, menu_font
from app.qt.QtCore import Qt
from app.qt.QtGui import QFont
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


def test_painted_menus_use_the_form_font_scaled_by_zoom() -> None:
    with opened(build_template_ui("main_window", "shop_window")) as (session, realizer):
        parent = QWidget()
        parent.resize(900, 700)
        canvas = FormCanvas(session, realizer, _Host(), parent)
        canvas.resize(900, 700)
        parent.show()
        _pump()
        root = realizer.root_widget
        font = QFont(root.font())
        font.setPointSize(18)
        root.setFont(font)
        glue = MenuEditGlue(session, realizer, canvas, lambda _s: None, lambda _s: None, lambda s, o: True, parent)
        glue.refresh()
        _pump()
        state = canvas.layer_state("menu_edit")
        assert isinstance(state, PaintState)
        assert state.font_family == root.font().family()
        assert state.font_point_size == 18
        scaled = menu_font(QFont(), 2.0, state.font_family, state.font_point_size, state.font_pixel_size)
        assert scaled.family() == root.font().family()
        assert scaled.pointSizeF() == 36

        class _View:
            factor = 2.0

            def to_canvas(self, rect):  # type: ignore[no-untyped-def]
                return rect

        painted = build(type("Static", (), {"view": _View()})(), None, state)
        assert painted.items
        assert painted.items[0].data[2:] == (
            state.font_family,
            state.font_point_size,
            state.font_pixel_size,
        )
        glue.dispose()
        canvas.dispose()
        parent.deleteLater()


@pytest.mark.parity("R3-135", "R3-136")
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
        assert isinstance(state, PaintState)
        assert [i.text for i in state.items if i.kind == "hint"] == ["Type here"]
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


@pytest.mark.parity("R3-143")
def test_delete_on_the_central_area_refuses_with_a_sentence() -> None:
    said = []
    with opened(build_template_ui("main_window", "shop_window")) as (session, realizer):
        parent = QWidget()
        parent.resize(900, 700)
        canvas = FormCanvas(session, realizer, _Host(), parent)
        canvas.resize(900, 700)
        parent.show()
        _pump()
        glue = MenuEditGlue(session, realizer, canvas, said.append, said.append, lambda s, o: True, parent)
        canvas.setFocus()
        central = session.document.by_name("centralwidget")[0]
        session.selection.set((central,), source=SelectionSource.PROGRAM)
        QTest.keyClick(canvas.viewport(), Qt.Key.Key_Delete)
        assert said[-1] == "The central area belongs to the window. Delete what's inside it instead."
        assert "centralwidget" in session.document.names()
        glue.dispose()
        canvas.dispose()
        parent.deleteLater()
