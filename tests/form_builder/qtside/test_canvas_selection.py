# pyright: reportAttributeAccessIssue=false
"""Canvas and outline share one selection. Mixed parents cannot wrap."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.qt.QtCore import Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QMenuBar, QTreeWidget, QWidget
from app.features.form_builder.engine.shell_commands import menu_commands
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.integration.chrome_text import MIXED_LAYOUT
from app.features.form_builder.integration.form_menu import register_form_menu
from app.shell.menus import build_menu_stubs, clear_menu_contributors
from tests.form_builder.qtside.support import form
from tests.unit.features.form_builder.test_workbench import _open

pytestmark = pytest.mark.usefixtures("qapp")

_UI = form(
    'class="QWidget" name="Form"',
    """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="one"><property name="text"><string>One</string></property></widget></item>
   <item><widget class="QPushButton" name="two"><property name="text"><string>Two</string></property></widget></item>
   <item>
    <widget class="QGroupBox" name="box">
     <layout class="QVBoxLayout" name="inner">
      <item><widget class="QPushButton" name="three"><property name="text"><string>Three</string></property></widget></item>
     </layout>
    </widget>
   </item>
  </layout>
""",
)


def test_a_canvas_click_and_an_outline_click_select_the_same_widget(tmp_path: Path) -> None:
    parent = QWidget()
    parent.resize(1100, 720)
    surface = _open(parent, _UI, tmp_path / "form.ui")
    surface.resize(1100, 720)
    parent.show()
    surface.show()
    _flush()
    try:
        canvas = surface.findChild(QWidget, "formBuilder.canvas")
        tree = surface.findChild(QTreeWidget, "formBuilder.structure")
        assert isinstance(canvas, FormCanvas)
        assert tree is not None
        one = surface._session.document.by_name("one")[0]  # type: ignore[attr-defined]  # noqa: SLF001
        two = surface._session.document.by_name("two")[0]  # type: ignore[attr-defined]  # noqa: SLF001
        _click(canvas, "one")
        assert _current(tree) == int(one)
        _click_row(tree, two)
        assert surface.editor_status_sentence().startswith("two ·")
        assert _current(tree) == int(two)
    finally:
        surface.release()
        parent.deleteLater()
        _flush()


def test_mixed_parents_block_wrap_and_say_why(tmp_path: Path) -> None:
    parent = QWidget()
    parent.resize(1100, 720)
    surface = _open(parent, _UI, tmp_path / "mixed.ui")
    surface.resize(1100, 720)
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
        form = registry.menus["formBuilder.menu"]
        wrap = registry.actions["form.action.wrap"]
        _click(canvas, "one")
        _click(canvas, "two", shift=True)
        form.aboutToShow.emit()
        assert surface.editor_status_sentence() == "2 selected"
        assert wrap.toolTip() != MIXED_LAYOUT
        _click(canvas, "three", shift=True)
        form.aboutToShow.emit()
        assert surface.editor_status_sentence() == MIXED_LAYOUT
        assert wrap.toolTip() == MIXED_LAYOUT
        command = next(item for item in menu_commands() if item.command_id == "form.action.wrap")
        assert wrap.isEnabled() is (command.available and not surface.mixed_layout_blocked())
        assert not wrap.isEnabled()
    finally:
        clear_menu_contributors()
        surface.release()
        window.deleteLater()
        parent.deleteLater()
        _flush()


def _click(canvas: FormCanvas, name: str, shift: bool = False) -> None:
    mods = _mods("ShiftModifier" if shift else "NoModifier")
    QTest.mouseClick(canvas.viewport(), _mouse("LeftButton"), mods, _center(canvas, name))
    _flush()


def _click_row(tree: QTreeWidget, node: object) -> None:
    item = _item(tree, int(node))  # type: ignore[arg-type]
    QTest.mouseClick(tree.viewport(), _mouse("LeftButton"), _mods("NoModifier"), tree.visualItemRect(item).center())
    _flush()


def _current(tree: QTreeWidget) -> int:
    item = tree.currentItem()
    assert item is not None
    return int(item.data(0, getattr(Qt, "UserRole")))


def _item(tree: QTreeWidget, node: int) -> object:
    role = getattr(Qt, "UserRole")

    def walk(item: object) -> object:
        raw = item.data(0, role)  # type: ignore[attr-defined]
        if raw is not None and int(raw) == node:
            return item
        for index in range(item.childCount()):  # type: ignore[attr-defined]
            found = walk(item.child(index))  # type: ignore[attr-defined]
            if found is not None:
                return found
        return None

    for index in range(tree.topLevelItemCount()):
        found = walk(tree.topLevelItem(index))
        if found is not None:
            return found
    raise AssertionError(node)


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
    for _ in range(6):
        app.processEvents()


def _mouse(name: str) -> Qt.MouseButton:
    return getattr(getattr(Qt, "MouseButton", Qt), name)


def _mods(name: str) -> Qt.KeyboardModifier:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)
