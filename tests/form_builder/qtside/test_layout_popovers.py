# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
"""The wrap popover, the remove-layout confirm, and the canvas context menu."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Tuple

import pytest

from app.qt.QtCore import QPoint, Qt, QTimer
from app.qt.QtGui import QContextMenuEvent, QPainter
from app.qt.QtTest import QTest
from app.qt.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from app.features.form_builder.engine.layout_actions import HSPLIT, ApplyKind
from app.features.form_builder.integration.chrome import chrome_for
from app.shell.theme_tokens import tokens_from_palette
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


@pytest.mark.parity("R3-55")
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


@pytest.mark.parity("R3-56")
def test_set_minimum_to_current_size_in_the_context_menu_locks_the_minimum(tmp_path: Path) -> None:
    parent, surface = _shown(tmp_path, "lock")
    try:
        canvas, root = _canvas(surface)
        one = _named(root, "one")
        size = one.size()
        _right_click(canvas, one)
        menu = surface.findChild(QMenu, "formBuilder.contextMenu")
        assert menu is not None

        _action(_submenu(menu, "Size constraints"), "Set minimum to current size").trigger()
        _flush()

        assert _named(root, "one").minimumSize() == size
        assert _named(root, "two").minimumSize().isNull()
    finally:
        _close(parent, surface)


def test_cancel_on_the_remove_layout_confirm_writes_nothing(tmp_path: Path) -> None:
    parent, surface = _shown(tmp_path, "remove-cancel")
    try:
        canvas, root = _canvas(surface)
        box = _named(root, "box")
        before = surface.current_text()
        _right_click(canvas, box, QPoint(box.width() // 2, 10))
        menu = surface.findChild(QMenu, "formBuilder.contextMenu")
        assert menu is not None

        asked = _answer(surface, "Cancel")
        _action(menu, "Remove layout\u2026").trigger()
        _flush()

        assert asked == [
            "Remove the layout from box? Its widget keeps its current position and size,"
            " but it won't follow the window any more. Box keeps its current size as its smallest size."
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
        _right_click(canvas, box, QPoint(box.width() // 2, 10))
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


_SPLIT = form(
    'class="QWidget" name="Form"',
    """
  <widget class="QSplitter" name="split">
   <property name="orientation"><enum>Qt::Orientation::Horizontal</enum></property>
   <widget class="QTextEdit" name="left"/>
   <widget class="QTextEdit" name="right"/>
  </widget>
""",
)


def test_an_already_horizontal_splitter_says_nothing_to_change(tmp_path: Path) -> None:
    parent = QWidget()
    parent.resize(800, 600)
    surface = _open(parent, _SPLIT, tmp_path / "split.ui")
    parent.show()
    surface.show()
    _flush()
    try:
        split = surface._session.document.by_name("split")[0]
        before = len(surface._session.log.entries())
        surface.run_layout(ApplyKind(HSPLIT), (split,))
        _flush()
        assert len(surface._session.log.entries()) == before
        assert "Nothing to change." in surface.editor_status_sentence()
    finally:
        _close(parent, surface)


def test_the_change_to_menu_follows_the_dark_theme(qapp: QApplication, tmp_path: Path) -> None:
    parent, surface = _shown(tmp_path, "theme")
    try:
        tokens = tokens_from_palette(qapp.palette(), force_mode="dark")
        surface.apply_theme(tokens)
        _flush()
        box_id = surface._session.document.by_name("box")[0]
        surface.open_context_menu(box_id, None)
        _flush()
        menu = surface.findChild(QMenu, "formBuilder.contextMenu")
        assert menu is not None and menu.isVisible()
        change = _submenu(menu, "Change to")
        chrome = chrome_for(tokens)
        assert chrome.panel in change.styleSheet()
        assert chrome.text in change.styleSheet()
        menu.close()
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


_SHOT_MODES = ("light", "dark", "high_contrast_light", "high_contrast_dark")
_SHOT_SIZES = ((1080, 600), (1400, 900))


def test_layout_command_screenshots(qapp: QApplication, tmp_path: Path) -> None:
    out = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not out:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    _shoot_layout_commands(qapp, tmp_path, folder)


def _shoot_layout_commands(qapp: QApplication, tmp_path: Path, folder: Path) -> None:
    parent, surface = _shown(tmp_path, "shots")
    try:
        canvas, root = _canvas(surface)
        one, two = _named(root, "one"), _named(root, "two")
        box = _named(root, "box")
        for mode, width, height in _shot_frames():
            _frame(parent, surface, qapp, mode, width, height)
            _click(canvas, one)
            _click(canvas, two, shift=True)
            surface.dispatch("form.action.wrap")
            _flush()
            popover = surface.findChild(QFrame, "formBuilder.wrapPopover")
            assert popover is not None and popover.isVisible()
            assert popover.findChild(QLabel, "formBuilder.wrapHeader").text() == "Wrap 2 widgets in\u2026"
            _save(parent, popover, folder, "wrap-popover", mode, width, height)
            popover.close()
            _flush()
            _close_menus(surface)

            _right_click(canvas, box, QPoint(box.width() // 2, 10))
            menu = _context_menu(surface)
            change = _submenu(menu, "Change to")
            change.popup(menu.mapToGlobal(menu.rect().topRight()))
            _flush()
            _save(parent, change, folder, "change-to", mode, width, height)
            _close_menus(surface)

            _right_click(canvas, box, QPoint(box.width() // 2, 10))
            menu = _context_menu(surface)
            _grab_confirm(parent, surface, folder, mode, width, height)
            _action(menu, "Remove layout\u2026").trigger()
            _flush()

            QTest.mouseClick(
                canvas.viewport(),
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                _port(canvas, box, QPoint(max(2, box.width() // 2), 6)),
            )
            _flush()
            pane = surface.findChild(QWidget, "formBuilder.inspector")
            assert pane is not None
            pane.flush()
            _flush()
            kind = pane.findChild(QWidget, "formBuilder.layout.kind")
            assert kind is not None and kind.isVisible()
            scroll = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
            if scroll is not None:
                scroll.ensureWidgetVisible(kind)
            _flush()
            _save(parent, None, folder, "layout-kind", mode, width, height)
            _close_menus(surface)
    finally:
        _close(parent, surface)


def _shot_frames() -> List[Tuple[str, int, int]]:
    frames = []
    for mode in _SHOT_MODES:
        for width, height in _SHOT_SIZES:
            if mode.startswith("high_contrast") and (width, height) != (1080, 600):
                continue
            frames.append((mode, width, height))
    return frames


def _frame(parent: QWidget, surface: QWidget, qapp: QApplication, mode: str, width: int, height: int) -> None:
    parent.resize(width, height)
    surface.resize(width, height)
    surface.apply_theme(tokens_from_palette(qapp.palette(), force_mode=mode))
    _flush()


def _save(
    host: QWidget,
    overlay: Optional[QWidget],
    folder: Path,
    stem: str,
    mode: str,
    width: int,
    height: int,
) -> None:
    app = QApplication.instance()
    assert app is not None
    app.processEvents()
    image = host.grab()
    if overlay is not None and overlay.isVisible():
        overlay.adjustSize()
        app.processEvents()
        tile = overlay.grab()
        painter = QPainter(image)
        origin = host.mapFromGlobal(overlay.mapToGlobal(QPoint(0, 0)))
        painter.drawPixmap(origin, tile)
        painter.end()
    image.save(str(folder / ("%s-%s-%dx%d.png" % (stem, mode, width, height))))


def _grab_confirm(parent: QWidget, surface: QWidget, folder: Path, mode: str, width: int, height: int) -> None:
    def grab() -> None:
        question = surface.findChild(QFrame, "formBuilder.layoutConfirm")
        if question is None or not question.isVisible():
            QTimer.singleShot(10, grab)
            return
        _save(parent, question, folder, "remove-layout-confirm", mode, width, height)
        for button in question.findChildren(QPushButton):
            if button.text() == "Cancel":
                button.click()
                return
        raise AssertionError("confirm has no Cancel button")

    QTimer.singleShot(0, grab)


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


def _context_menu(surface: QWidget) -> QMenu:
    """The open context menu. A closed one stays until deleteLater runs."""
    visible = [
        menu
        for menu in surface.findChildren(QMenu)
        if menu.objectName() == "formBuilder.contextMenu" and menu.isVisible()
    ]
    assert visible, "context menu is not open"
    return visible[-1]


def _close_menus(surface: QWidget) -> None:
    for menu in surface.findChildren(QMenu):
        menu.hide()
        menu.close()
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
