# pyright: reportAttributeAccessIssue=false
"""Text-size preview and two widths stay off the document."""

from __future__ import annotations

from typing import Tuple

import pytest

from app.features.form_builder.engine.preview_state import PreviewState
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.qtside.canvas.preview_apply import apply_preview
from app.features.form_builder.qtside.theme.runtime import startup_font
from app.qt.QtCore import QPoint, Qt
from app.qt.QtGui import QFont, QPalette
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLabel, QWidget
from tests.form_builder.qtside.support import form, opened

pytestmark = pytest.mark.usefixtures("qapp")

_COLUMN = form(
    'class="QWidget" name="Form"',
    """
  <layout class="QVBoxLayout" name="column">
   <item>
    <widget class="QPushButton" name="one">
     <property name="text"><string>One</string></property>
    </widget>
   </item>
   <item>
    <widget class="QPushButton" name="two">
     <property name="text"><string>Two</string></property>
    </widget>
   </item>
  </layout>
""",
)

_FIXED = form(
    'class="QWidget" name="Form"',
    """
  <layout class="QVBoxLayout" name="column">
   <item>
    <widget class="QPushButton" name="child">
     <property name="text"><string>This sentence is much too long to fit inside a fixed button</string></property>
     <property name="sizePolicy">
      <sizepolicy hsizetype="Fixed" vsizetype="Fixed">
       <horstretch>0</horstretch>
       <verstretch>0</verstretch>
      </sizepolicy>
     </property>
     <property name="maximumSize">
      <size><width>40</width><height>16</height></size>
     </property>
    </widget>
   </item>
  </layout>
""",
)

_PAGE = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>640</width><height>480</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="ok">
     <property name="text"><string>OK</string></property>
    </widget>
   </item>
  </layout>
""",
)


class _Host:
    def canvas_pressed(self) -> None:
        return None

    def narrate(self, sentence: str) -> None:
        return None

    def hover_changed(self, node: object) -> None:
        return None

    def zoom_changed(self, label: str) -> None:
        return None

    def open_problem(self, node: object) -> None:
        return None

    def open_layout_popover(self, node: object) -> None:
        return None


def test_point_size_reflows_the_column_and_writes_nothing() -> None:
    with opened(_COLUMN) as (session, realizer):
        root = realizer.root_widget
        assert root is not None
        root.resize(320, 160)
        root.show()
        _pump()
        app = QApplication.instance()
        assert app is not None
        font_before = _font_stamp(app.font())
        palette_before = _palette_stamp(app.palette())
        logged = len(session.log.entries())
        startup = startup_font()
        apply_preview(root, PreviewState(text_point_size=10), startup)
        _pump()
        smaller = _heights(root)
        apply_preview(root, PreviewState(text_point_size=16), startup)
        _pump()
        larger = _heights(root)
        assert smaller != larger
        for name in ("one", "two"):
            body = _widget_body(session.text(), name)
            assert "<x>" not in body
            assert "<y>" not in body
        assert _font_stamp(app.font()) == font_before
        assert _palette_stamp(app.palette()) == palette_before
        assert len(session.log.entries()) == logged


def test_larger_preview_shows_the_pill_and_reset_restores_the_startup_font() -> None:
    with opened(_COLUMN) as (session, realizer):
        parent = QWidget()
        canvas = FormCanvas(session, realizer, _Host(), parent)
        try:
            _show(parent, canvas)
            before = session.text()
            startup = QFont(startup_font())
            canvas.set_text_preset("larger")
            _pump()
            pill = canvas.findChild(QLabel, "formBuilder.previewPill")
            assert pill is not None
            assert pill.isVisible()
            assert pill.text() == "Previewing larger text \u00b7 Reset"
            assert pill.accessibleName() == pill.text()
            root = canvas.page_widget()
            assert root is not None
            _assert_above_top_right(canvas, pill, root)
            _click_reset(pill)
            _pump()
            assert not pill.isVisible()
            restored = root.font()
            assert restored.family() == startup.family()
            assert abs(restored.pointSizeF() - startup.pointSizeF()) < 0.05
            assert session.text() == before
        finally:
            canvas.dispose()
            parent.deleteLater()


def test_fixed_button_that_cannot_fit_is_counted_and_gains_no_geometry() -> None:
    with opened(_FIXED) as (session, realizer):
        parent = QWidget()
        canvas = FormCanvas(session, realizer, _Host(), parent)
        try:
            _show(parent, canvas)
            logged = len(session.log.entries())
            canvas.set_text_point_size(16)
            _pump()
            pill = canvas.findChild(QLabel, "formBuilder.previewPill")
            assert pill is not None
            assert pill.isVisible()
            assert "\u00b7 1 widget cut off text" in pill.text()
            child_ids = session.document.by_name("child")
            assert child_ids
            child = session.document.node(child_ids[0])
            assert child.prop("geometry") is None
            body = _widget_body(session.text(), "child")
            assert "<x>" not in body
            assert "<y>" not in body
            assert len(session.log.entries()) == logged
            _click_count(pill)
            _pump()
            assert child_ids[0] in session.selection.state.ids
            assert session.selection.state.ids[0] == child_ids[0]
        finally:
            canvas.dispose()
            parent.deleteLater()


def test_two_widths_keeps_the_file_and_shares_the_selected_name() -> None:
    with opened(_PAGE) as (session, realizer):
        parent = QWidget()
        canvas = FormCanvas(session, realizer, _Host(), parent)
        try:
            _show(parent, canvas)
            before = session.text()
            logged = len(session.log.entries())
            canvas.set_two_widths(True)
            _pump()
            assert session.text() == before
            assert len(session.log.entries()) == logged
            root = canvas.page_widget()
            copy = canvas.wide_realizer()
            assert root is not None and copy is not None
            wide_root = copy.root_widget
            assert wide_root is not None
            assert wide_root.width() == 1366
            narrow = canvas.findChild(QLabel, "formBuilder.narrowLabel")
            wide = canvas.findChild(QLabel, "formBuilder.wideLabel")
            assert narrow is not None and wide is not None
            assert narrow.text() == "Narrowest \u00b7 %d px" % root.width()
            assert wide.text() == "Wide \u00b7 %d px" % wide_root.width()
            assert narrow.isVisible() and wide.isVisible()
            if abs(narrow.x() - wide.x()) < 4:
                assert narrow.y() < wide.y()
            else:
                assert narrow.x() < wide.x()
            assert abs(_span(canvas, root) / root.width() - _span(canvas, wide_root) / wide_root.width()) < 0.05
            button = wide_root.findChild(QWidget, "ok")
            assert button is not None
            QTest.mouseClick(button, _left())
            _pump()
            assert "ok" in canvas.accessibleDescription()
            assert canvas.accessibleDescription() == wide_root.accessibleDescription()
            assert session.text() == before
            child = session.document.node(session.document.by_name("ok")[0])
            assert child.prop("geometry") is None
        finally:
            canvas.dispose()
            parent.deleteLater()


def _heights(root: QWidget) -> Tuple[int, int, int, int]:
    layout = root.layout()
    child = root.findChild(QWidget, "one")
    assert layout is not None and child is not None
    return (
        int(layout.sizeHint().height()),
        int(child.sizeHint().height()),
        int(child.height()),
        int(root.height()),
    )


def _widget_body(text: str, name: str) -> str:
    token = 'name="%s"' % name
    start = text.find(token)
    assert start >= 0
    end = text.find("</widget>", start)
    assert end >= 0
    return text[start:end]


def _font_stamp(font: QFont) -> Tuple[str, float, int, str]:
    return (font.family(), float(font.pointSizeF()), int(font.pixelSize()), font.toString())


def _palette_stamp(palette: QPalette) -> Tuple[int, ...]:
    role = getattr(QPalette, "ColorRole", QPalette)
    names = ("Window", "WindowText", "Button", "ButtonText", "Base", "Text")
    return tuple(int(palette.color(getattr(role, name)).rgba()) for name in names)


def _show(parent: QWidget, canvas: FormCanvas) -> None:
    parent.resize(960, 720)
    canvas.resize(960, 720)
    parent.show()
    canvas.show()
    _pump()


def _assert_above_top_right(canvas: FormCanvas, pill: QLabel, root: QWidget) -> None:
    corner = canvas.mapFromGlobal(root.mapToGlobal(QPoint(root.width(), 0)))
    assert pill.y() + pill.height() <= corner.y() + 2
    assert abs((pill.x() + pill.width()) - corner.x()) <= 24


def _click_reset(pill: QLabel) -> None:
    text = pill.text()
    reset_at = text.rfind(" \u00b7 Reset")
    assert reset_at >= 0
    x = pill.contentsRect().x() + pill.fontMetrics().horizontalAdvance(text[:reset_at]) + 4
    QTest.mouseClick(pill, _left(), _none(), QPoint(x, pill.height() // 2))


def _click_count(pill: QLabel) -> None:
    text = pill.text()
    count_at = text.find("\u00b7")
    reset_at = text.rfind(" \u00b7 Reset")
    assert count_at >= 0 and reset_at > count_at
    metrics = pill.fontMetrics()
    start = pill.contentsRect().x() + metrics.horizontalAdvance(text[:count_at])
    end = pill.contentsRect().x() + metrics.horizontalAdvance(text[:reset_at])
    QTest.mouseClick(pill, _left(), _none(), QPoint((start + end) // 2, pill.height() // 2))


def _span(canvas: FormCanvas, widget: QWidget) -> int:
    left = canvas.mapFromGlobal(widget.mapToGlobal(QPoint(0, 0)))
    right = canvas.mapFromGlobal(widget.mapToGlobal(QPoint(widget.width(), 0)))
    return int(right.x() - left.x())


def _left() -> Qt.MouseButton:
    return getattr(getattr(Qt, "MouseButton", Qt), "LeftButton")


def _none() -> Qt.KeyboardModifier:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), "NoModifier")


def _pump() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(4):
        app.processEvents()
