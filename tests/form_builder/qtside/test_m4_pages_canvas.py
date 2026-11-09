# pyright: reportAttributeAccessIssue=false
"""Shown page and start page on the canvas (UX-CONT-006, UX-CONT-007, UX-KEY-004)."""

from __future__ import annotations

from typing import List

import pytest

from app.qt.QtCore import QPoint, Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QWidget
from app.features.form_builder.engine.shell_commands import is_widget_shortcut, FORM_COMMANDS
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.ui4.values import NumberValue
from app.features.form_builder.engine.ui4.writer import write_ui
from tests.form_builder.qtside.support import form, opened

pytestmark = pytest.mark.usefixtures("qapp")

TABS = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>600</width><height>400</height></rect></property>
  <widget class="QTabWidget" name="tabs">
   <property name="geometry"><rect><x>20</x><y>20</y><width>400</width><height>260</height></rect></property>
   <property name="currentIndex"><number>0</number></property>
   <widget class="QWidget" name="tab_a">
    <attribute name="title"><string>Alpha</string></attribute>
    <widget class="QLabel" name="inside_a">
     <property name="geometry"><rect><x>10</x><y>10</y><width>80</width><height>24</height></rect></property>
     <property name="text"><string>In A</string></property>
    </widget>
   </widget>
   <widget class="QWidget" name="tab_b">
    <attribute name="title"><string>Beta</string></attribute>
    <widget class="QLabel" name="inside_b">
     <property name="geometry"><rect><x>10</x><y>10</y><width>80</width><height>24</height></rect></property>
     <property name="text"><string>In B</string></property>
    </widget>
   </widget>
  </widget>
""",
)


class _Host:
    def __init__(self) -> None:
        self.sentences: List[str] = []

    def canvas_pressed(self) -> None:
        return None

    def narrate(self, sentence: str) -> None:
        self.sentences.append(sentence)

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


def _flush() -> None:
    app = QApplication.instance()
    assert app is not None
    app.processEvents()


def _press_key(canvas: FormCanvas, key: str, modifier: str) -> None:
    mods = getattr(getattr(Qt, "KeyboardModifier", Qt), modifier)
    QTest.keyClick(canvas, getattr(getattr(Qt, "Key", Qt), key), mods)
    _flush()


def _click(canvas: FormCanvas, name: str) -> None:
    root = canvas.page_widget()
    assert root is not None
    widget = root.findChild(QWidget, name)
    assert widget is not None
    center = widget.mapTo(root, widget.rect().center())
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    port = canvas.mapFromScene(proxy.mapToScene(center))
    QTest.mouseClick(canvas.viewport(), getattr(getattr(Qt, "MouseButton", Qt), "LeftButton"), getattr(getattr(Qt, "KeyboardModifier", Qt), "NoModifier"), port)
    _flush()


def _shown_index(canvas: FormCanvas, name: str) -> int:
    root = canvas.page_widget()
    assert root is not None
    widget = root.findChild(QWidget, name)
    assert widget is not None
    return int(widget.currentIndex())  # type: ignore[attr-defined]


def test_ctrl_page_down_shows_the_next_page_and_only_that() -> None:
    host = _Host()
    with opened(TABS) as (session, realizer):
        parent = QWidget()
        parent.resize(640, 480)
        canvas = FormCanvas(session, realizer, host, parent)
        canvas.resize(640, 480)
        parent.show()
        canvas.setFocus()
        _flush()
        before = write_ui(session.document).text
        dirty_before = session.log.is_dirty()
        _click(canvas, "inside_a")
        _press_key(canvas, "Key_PageDown", "ControlModifier")
        assert _shown_index(canvas, "tabs") == 1
        assert write_ui(session.document).text == before
        assert session.log.is_dirty() == dirty_before
        assert host.sentences[-1] == "Showing page 2 of 2: Beta · the file still starts on page 1"
        _press_key(canvas, "Key_PageDown", "ControlModifier")
        assert _shown_index(canvas, "tabs") == 0, "Ctrl+PgDown wraps to the first page"
        assert host.sentences[-1] == "Showing page 1 of 2: Alpha"
        canvas.dispose()
        parent.deleteLater()


def test_ctrl_page_up_wraps_to_the_last_page() -> None:
    host = _Host()
    with opened(TABS) as (session, realizer):
        parent = QWidget()
        parent.resize(640, 480)
        canvas = FormCanvas(session, realizer, host, parent)
        canvas.resize(640, 480)
        parent.show()
        canvas.setFocus()
        _flush()
        _click(canvas, "inside_a")
        _press_key(canvas, "Key_PageUp", "ControlModifier")
        assert _shown_index(canvas, "tabs") == 1
        canvas.dispose()
        parent.deleteLater()


def test_start_on_this_page_changes_only_the_saved_index() -> None:
    with opened(TABS) as (session, realizer):
        tabs = session.document.by_name("tabs")[0]
        before = write_ui(session.document).text
        session.log.execute(SetProperty(tabs, "currentIndex", NumberValue(1)))
        after = write_ui(session.document).text
        assert after != before
        session.log.undo()
        assert write_ui(session.document).text == before


def test_page_keys_are_registered_as_widget_keys_without_a_window_shortcut() -> None:
    rows = {command.command_id: command for command in FORM_COMMANDS}
    for command_id, key in (("form.action.showNextPage", "Ctrl+PgDown"), ("form.action.showPreviousPage", "Ctrl+PgUp")):
        command = rows[command_id]
        assert command.shortcut == key
        assert set(command.contexts) == {"canvas", "outline"}
        assert is_widget_shortcut(command)
        assert not command.available, "the key reaches the canvas, which shows the page"
