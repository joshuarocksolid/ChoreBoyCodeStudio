# pyright: reportAttributeAccessIssue=false
"""The wrap popover, the remove-layout confirm, and the canvas context menu."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import pytest

from app.qt.QtCore import QPoint, Qt, QTimer
from app.qt.QtGui import QContextMenuEvent
from app.qt.QtTest import QTest
from app.qt.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from tests.form_builder.qtside.support import form
from tests.unit.features.form_builder.test_workbench import _open

pytestmark = pytest.mark.usefixtures("qapp")

_UI = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>360</width><height>300</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="one"><property name="text"><string>One</string></property></widget></item>
   <item><widget class="QPushButton" name="two"><property name="text"><string>Two</string></property></widget></item>
   <item>
    <widget class="QGroupBox" name="box">
     <property name="title"><string>Box</string></property>
     <layout class="QVBoxLayout" name="inner">
      <item><widget class="QPushButton" name="three"><property name="text"><string>Three</string></property></widget></item>
     </layout>
    </widget>
   </item>
   <item><widget class="QGroupBox" name="bare"><property name="title"><string>Bare</string></property></widget></item>
  </layout>
""",
)


def test_digit_1_in_the_wrap_popover_wraps_the_selection_in_a_vertical_layout(tmp_path: Path) -> None:
    parent, surface = _shown(tmp_path, "wrap")
    try:
        canvas, root = _canvas(surface)
        one, two = _named(root, "one"), _named(root, "two")
        _click(canvas, one)
        _click(canvas, two, shift=True)

        surface.dispatch("form.action.wrap")
        _flush()
        popover = surface.findChild(QFrame, "formBuilder.wrapPopover")
        assert popover is not None and popover.isVisible()
        header = popover.findChild(QLabel, "formBuilder.wrapHeader")
        assert header is not None and header.text() == "Wrap 2 widgets in\u2026"
        QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_1)
        _flush()

        assert not _visible(surface, "formBuilder.wrapPopover")
        nested = _layout_holding(root.layout(), one)
        assert isinstance(nested, QVBoxLayout) and nested is not root.layout()
        assert nested.indexOf(two) >= 0
        assert _named(root, "one") is one
    finally:
        _close(parent, surface)


def test_only_a_tile_writes_from_the_wrap_popover(tmp_path: Path) -> None:
    parent, surface = _shown(tmp_path, "wrap-esc")
    try:
        canvas, root = _canvas(surface)
        _click(canvas, _named(root, "one"))
        _click(canvas, _named(root, "two"), shift=True)
        before = surface.current_text()

        surface.dispatch("form.action.wrap")
        _flush()
        QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
        _flush()
        assert _visible(surface, "formBuilder.wrapPopover")
        QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Escape)
        _flush()

        assert not _visible(surface, "formBuilder.wrapPopover")
        assert surface.current_text() == before
    finally:
        _close(parent, surface)


def test_change_to_in_the_context_menu_changes_the_right_clicked_widget(tmp_path: Path) -> None:
    parent, surface = _shown(tmp_path, "morph")
    try:
        canvas, root = _canvas(surface)
        _right_click(canvas, _named(root, "one"))
        menu = surface.findChild(QMenu, "formBuilder.contextMenu")
        assert menu is not None and menu.isVisible()

        _action(_submenu(menu, "Change to"), "Tool button").trigger()
        _flush()

        assert isinstance(_named(root, "one"), QToolButton)
        assert isinstance(_named(root, "two"), QPushButton)
    finally:
        _close(parent, surface)


def test_cancel_on_the_remove_layout_confirm_writes_nothing(tmp_path: Path) -> None:
    parent, surface = _shown(tmp_path, "remove-cancel")
    try:
        canvas, root = _canvas(surface)
        box = _named(root, "box")
        before = surface.current_text()
        _right_click(canvas, box, QPoint(box.width() // 2, 3))
        menu = surface.findChild(QMenu, "formBuilder.contextMenu")
        assert menu is not None

        asked = _answer(surface, "Cancel")
        _action(menu, "Remove layout\u2026").trigger()
        _flush()

        assert asked == [
            "Remove the layout from box? Its widget keeps its current position and size,"
            " but it won't follow the window any more."
        ]
        assert box.layout() is not None
        assert surface.current_text() == before
    finally:
        _close(parent, surface)


def test_accepting_remove_layout_keeps_the_widget_where_it_was(tmp_path: Path) -> None:
    parent, surface = _shown(tmp_path, "remove-accept")
    try:
        canvas, root = _canvas(surface)
        box = _named(root, "box")
        three = _named(box, "three")
        where = three.geometry()
        _right_click(canvas, box, QPoint(box.width() // 2, 3))
        menu = surface.findChild(QMenu, "formBuilder.contextMenu")
        assert menu is not None

        _answer(surface, "Remove layout")
        _action(menu, "Remove layout\u2026").trigger()
        _flush()

        assert box.layout() is None
        assert _named(box, "three") is three
        assert three.geometry() == where
    finally:
        _close(parent, surface)


def test_shift_f10_on_the_canvas_opens_the_context_menu(tmp_path: Path) -> None:
    parent, surface = _shown(tmp_path, "menu-key")
    try:
        canvas, root = _canvas(surface)
        _click(canvas, _named(root, "one"))
        canvas.setFocus()
        _flush()

        QTest.keyClick(canvas.viewport(), Qt.Key.Key_F10, Qt.KeyboardModifier.ShiftModifier)
        _flush()

        menu = surface.findChild(QMenu, "formBuilder.contextMenu")
        assert menu is not None and menu.isVisible()
        assert _submenu(menu, "Change to") is not None
    finally:
        _close(parent, surface)


def test_the_layout_menu_of_a_bare_container_gives_it_that_layout(tmp_path: Path) -> None:
    parent, surface = _shown(tmp_path, "chip")
    try:
        canvas, root = _canvas(surface)
        bare = _named(root, "bare")
        node = canvas.node_at(_port(canvas, bare, QPoint(bare.width() // 2, bare.height() // 2)))
        assert node is not None

        surface.open_layout_popover(node)
        _flush()
        menu = surface.findChild(QMenu, "formBuilder.layoutPopover")
        assert menu is not None
        _action(menu, "Horizontal").trigger()
        _flush()

        assert isinstance(bare.layout(), QHBoxLayout)
    finally:
        _close(parent, surface)


def _answer(surface: QWidget, button: str) -> List[str]:
    """Click ``button`` on the next layout confirm. Returns the question it asked."""
    asked: List[str] = []

    def click() -> None:
        question = surface.findChild(QFrame, "formBuilder.layoutConfirm")
        if question is None or not question.isVisible():
            QTimer.singleShot(10, click)
            return
        text = question.findChild(QLabel, "formBuilder.layoutConfirmText")
        asked.append(text.text() if text is not None else "")
        for candidate in question.findChildren(QPushButton):
            if candidate.text() == button:
                candidate.click()
                return
        raise AssertionError("no %r button" % button)

    QTimer.singleShot(0, click)
    return asked


def _shown(tmp_path: Path, name: str) -> Tuple[QWidget, QWidget]:
    parent = QWidget()
    parent.resize(1000, 700)
    surface = _open(parent, _UI, tmp_path / ("%s.ui" % name))
    surface.resize(1000, 700)
    parent.show()
    surface.show()
    parent.activateWindow()
    _flush()
    return parent, surface


def _canvas(surface: QWidget) -> Tuple[QWidget, QWidget]:
    canvas = surface.findChild(QWidget, "formBuilder.canvas")
    assert canvas is not None
    root = canvas.page_widget()
    assert root is not None
    return canvas, root


def _named(parent: QWidget, name: str) -> QWidget:
    found = parent.findChild(QWidget, name)
    assert found is not None, name
    return found


def _port(canvas: QWidget, widget: QWidget, at: Optional[QPoint] = None) -> QPoint:
    root = canvas.page_widget()
    point = widget.mapTo(root, at if at is not None else widget.rect().center())
    return canvas.mapFromScene(root.graphicsProxyWidget().mapToScene(point))


def _click(canvas: QWidget, widget: QWidget, shift: bool = False) -> None:
    mods = Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
    QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, mods, _port(canvas, widget))
    _flush()


def _right_click(canvas: QWidget, widget: QWidget, at: Optional[QPoint] = None) -> None:
    port = _port(canvas, widget, at)
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, port, canvas.viewport().mapToGlobal(port))
    QApplication.sendEvent(canvas.viewport(), event)
    _flush()


def _submenu(menu: QMenu, text: str) -> QMenu:
    for found in menu.findChildren(QMenu):
        if found.title() == text:
            return found
    raise AssertionError("no %r submenu" % text)


def _action(menu: QMenu, text: str) -> object:
    for action in menu.actions():
        if action.text() == text:
            return action
    raise AssertionError("%r not in %r" % (text, [action.text() for action in menu.actions()]))


def _layout_holding(layout: object, widget: QWidget) -> Optional[object]:
    for index in range(layout.count()):  # type: ignore[attr-defined]
        inner = layout.itemAt(index).layout()  # type: ignore[attr-defined]
        if inner is not None and inner.indexOf(widget) >= 0:
            return inner
    return None


def _visible(surface: QWidget, name: str) -> bool:
    found = surface.findChild(QFrame, name)
    return found is not None and found.isVisible()


def _close(parent: QWidget, surface: QWidget) -> None:
    for menu in surface.findChildren(QMenu):
        menu.close()
    surface.release()
    parent.deleteLater()
    _flush()


def _flush() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(6):
        app.processEvents()
