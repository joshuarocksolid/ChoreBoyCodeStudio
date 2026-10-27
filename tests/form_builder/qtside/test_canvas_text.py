# pyright: reportAttributeAccessIssue=false
"""In-place text. One undo step, Esc cancels, and typing does not reflow."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import pytest

from app.qt.QtCore import QPoint, Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLineEdit, QMenuBar, QWidget
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.integration.form_menu import register_form_menu
from app.features.form_builder.qtside.canvas.core.gesture import ZoomAsked
from app.features.form_builder.qtside.canvas.core.space import ZoomTo
from app.shell.menus import build_menu_stubs, clear_menu_contributors
from tests.form_builder.qtside.support import form, opened
from tests.unit.features.form_builder.test_workbench import _open as _open_surface

pytestmark = pytest.mark.usefixtures("qapp")

BUTTON = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <widget class="QPushButton" name="ok">
   <property name="geometry"><rect><x>40</x><y>40</y><width>80</width><height>28</height></rect></property>
   <property name="text"><string>OK</string></property>
  </widget>
""",
)

NESTED = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <widget class="QGroupBox" name="box">
   <property name="geometry"><rect><x>20</x><y>20</y><width>300</width><height>200</height></rect></property>
   <widget class="QPushButton" name="ok">
    <property name="geometry"><rect><x>20</x><y>40</y><width>120</width><height>28</height></rect></property>
    <property name="text"><string>OK</string></property>
   </widget>
  </widget>
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

    def open_context_menu(self, node: object, at: object) -> None:
        return None


def test_enter_writes_one_undo_step() -> None:
    with opened(BUTTON) as (session, realizer):
        canvas, parent = _canvas(session, realizer)
        _click(canvas, "ok")
        edit = _open(canvas)
        QTest.keyClicks(edit, "Save")
        QTest.keyClick(edit, _qt_key("Key_Return"))
        _flush()
        assert _button(canvas).text() == "Save"
        assert _stored(session) == "Save"
        assert session.log.undo_label() == "Edit text"
        assert session.log.undo()
        _flush()
        assert _button(canvas).text() == "OK"
        assert _stored(session) == "OK"
        assert not session.log.can_undo()
        canvas.dispose()
        parent.deleteLater()


def test_change_text_opens_the_in_place_editor(tmp_path: Path) -> None:
    parent = QWidget()
    parent.resize(960, 720)
    surface = _open_surface(parent, BUTTON, tmp_path / "button.ui")
    surface.resize(960, 720)
    parent.show()
    surface.show()
    _flush()
    window = QWidget()
    register_form_menu(window)

    class _Tab:
        def __init__(self, path: str) -> None:
            self.file_path = path

    class _Manager:
        def active_tab(self) -> _Tab:
            return _Tab(surface.form_path())

    class _Registry:
        def surface_for_path(self, path: str) -> object:
            del path
            return surface

    window._editor_manager = _Manager()  # type: ignore[attr-defined]
    window._tab_content_registry = _Registry()  # type: ignore[attr-defined]
    bar = QMenuBar(window)
    try:
        canvas = surface.findChild(QWidget, "formBuilder.canvas")
        assert isinstance(canvas, FormCanvas)
        registry = build_menu_stubs(bar)
        menu = registry.menus["formBuilder.menu"]
        change = registry.actions["form.action.editText"]
        assert "Change text" in change.text()
        menu.aboutToShow.emit()
        assert not change.isEnabled()
        _click(canvas, "ok")
        menu.aboutToShow.emit()
        assert change.isEnabled()
        change.trigger()
        _flush()
        edit = _visible_edit(canvas)
        assert edit is not None
        assert edit.text() == "OK"
        assert edit.isVisible()
    finally:
        clear_menu_contributors()
        surface.release()
        window.deleteLater()
        parent.deleteLater()
        _flush()


def test_escape_cancels_without_a_write() -> None:
    with opened(BUTTON) as (session, realizer):
        canvas, parent = _canvas(session, realizer)
        _click(canvas, "ok")
        edit = _open(canvas)
        QTest.keyClicks(edit, "Save")
        QTest.keyClick(edit, _qt_key("Key_Escape"))
        _flush()
        assert _button(canvas).text() == "OK"
        assert _stored(session) == "OK"
        assert not session.log.can_undo()
        assert _visible_edit(canvas) is None
        canvas.dispose()
        parent.deleteLater()


def test_a_click_elsewhere_commits_the_text() -> None:
    with opened(BUTTON) as (session, realizer):
        canvas, parent = _canvas(session, realizer)
        _click(canvas, "ok")
        edit = _open(canvas)
        QTest.keyClicks(edit, "Save")
        QTest.mouseClick(canvas.viewport(), _mouse("LeftButton"), _mods("NoModifier"), QPoint(8, 8))
        _flush()
        assert _button(canvas).text() == "Save"
        assert _stored(session) == "Save"
        assert session.log.undo_label() == "Edit text"
        assert _visible_edit(canvas) is None
        canvas.dispose()
        parent.deleteLater()


def test_typing_does_not_reflow_the_form() -> None:
    with opened(BUTTON) as (session, realizer):
        canvas, parent = _canvas(session, realizer)
        _click(canvas, "ok")
        button = _button(canvas)
        root = canvas.page_widget()
        assert root is not None
        geometry = button.geometry()
        size = (root.width(), root.height())
        revision = session.document.revision
        edit = _open(canvas)
        QTest.keyClicks(edit, "A label long enough to change the hint")
        assert button.geometry() == geometry
        assert (root.width(), root.height()) == size
        assert session.document.revision == revision
        assert button.text() == "OK"
        canvas.dispose()
        parent.deleteLater()


def test_the_editor_text_matches_a_nested_widget_at_half_zoom() -> None:
    """Only the page root is proxied. A child's editor still takes the stage zoom."""
    with opened(NESTED) as (session, realizer):
        canvas, parent = _canvas(session, realizer)
        canvas.send(ZoomAsked(ZoomTo(0.5)))
        _flush()
        _click(canvas, "ok")
        edit = _open(canvas)
        shown = _button(canvas).fontInfo().pixelSize() * 0.5
        assert abs(edit.fontInfo().pixelSize() - shown) <= 1
        canvas.dispose()
        parent.deleteLater()


def _canvas(session: object, realizer: object) -> Tuple[FormCanvas, QWidget]:
    parent = QWidget()
    parent.resize(960, 720)
    canvas = FormCanvas(session, realizer, _Host(), parent)  # type: ignore[arg-type]
    canvas.resize(960, 720)
    parent.show()
    canvas.setFocus()
    _flush()
    return canvas, parent


def _open(canvas: FormCanvas) -> QLineEdit:
    QTest.keyClick(canvas, _qt_key("Key_Return"))
    _flush()
    edit = _visible_edit(canvas)
    assert edit is not None
    return edit


def _visible_edit(canvas: FormCanvas) -> Optional[QLineEdit]:
    for edit in canvas.viewport().findChildren(QLineEdit):
        if edit.isVisible():
            return edit
    return None


def _button(canvas: FormCanvas) -> QWidget:
    root = canvas.page_widget()
    assert root is not None
    button = root.findChild(QWidget, "ok")
    assert button is not None
    return button


def _stored(session: FormSession) -> str:
    node = next(item for item in session.document.iter_preorder() if getattr(item, "object_name", None) == "ok")
    assert isinstance(node, WidgetNode)
    entry = node.prop("text")
    assert entry is not None and isinstance(entry.value, StringValue)
    return entry.value.text


def _click(canvas: FormCanvas, name: str) -> None:
    QTest.mouseClick(canvas.viewport(), _mouse("LeftButton"), _mods("NoModifier"), _center(canvas, name))
    _flush()


def _center(canvas: FormCanvas, name: str) -> object:
    root = canvas.page_widget()
    assert root is not None
    widget = root.findChild(QWidget, name)
    assert widget is not None
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    return canvas.mapFromScene(proxy.mapToScene(widget.mapTo(root, widget.rect().center())))


def _flush() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(4):
        app.processEvents()


def _mouse(name: str) -> Qt.MouseButton:
    return getattr(getattr(Qt, "MouseButton", Qt), name)


def _mods(name: str) -> Qt.KeyboardModifier:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def _qt_key(name: str) -> Qt.Key:
    return getattr(getattr(Qt, "Key", Qt), name)
