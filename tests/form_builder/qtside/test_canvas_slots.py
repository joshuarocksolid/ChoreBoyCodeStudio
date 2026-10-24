# pyright: reportAttributeAccessIssue=false
"""Slot drags through the form surface. One release is one undo step."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.qt.QtCore import QEvent, QPoint, Qt
from app.qt.QtGui import QMouseEvent
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QPushButton, QWidget
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.integration.provider import FormTabProvider
from app.features.form_builder.integration.surface import FormSurface
from app.shell.tab_content_providers import TabSurfaceRequest
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.qtside.support import form

pytestmark = pytest.mark.usefixtures("qapp")

BOX = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="first">
     <property name="text"><string>First</string></property>
    </widget>
   </item>
   <item>
    <widget class="QPushButton" name="second">
     <property name="text"><string>Second</string></property>
    </widget>
   </item>
  </layout>
""",
)

ROWS = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0">
    <widget class="QLabel" name="nameLabel">
     <property name="text"><string>Name</string></property>
    </widget>
   </item>
   <item row="0" column="1">
    <widget class="QLineEdit" name="nameEdit"/>
   </item>
  </layout>
""",
)


def test_dragging_a_laid_out_button_is_one_undo(tmp_path: Path) -> None:
    host, surface = _shown(tmp_path, BOX)
    try:
        canvas = surface._workbench.canvas_view()
        start = _center(canvas, "first")
        end = _shifted(canvas, "second", 0, _widget(canvas, "second").height() // 4)
        _press(canvas.viewport(), start)
        _move(canvas.viewport(), end)
        _release(canvas.viewport(), end)
        assert _box_order(surface) == ("second", "first")
        assert len(surface._session.log.entries()) == 1
        moved = _named(surface, "first")
        assert isinstance(moved, WidgetNode)
        assert moved.prop("geometry") is None
        assert surface._session.log.undo()
        assert _box_order(surface) == ("first", "second")
    finally:
        surface.release()
        host.deleteLater()


def test_escape_during_a_slot_drag_leaves_the_document(tmp_path: Path) -> None:
    host, surface = _shown(tmp_path, BOX)
    try:
        canvas = surface._workbench.canvas_view()
        before = _box_order(surface)
        start = _center(canvas, "first")
        end = _shifted(canvas, "second", 0, _widget(canvas, "second").height() // 4)
        _press(canvas.viewport(), start)
        _move(canvas.viewport(), end)
        canvas.setFocus()
        QTest.keyClick(canvas, _key("Key_Escape"))
        _flush()
        _release(canvas.viewport(), end)
        assert _box_order(surface) == before
        assert not surface._session.log.can_undo()
    finally:
        surface.release()
        host.deleteLater()


def test_a_spacer_dropped_on_a_form_changes_nothing(tmp_path: Path) -> None:
    host, surface = _shown(tmp_path, ROWS)
    try:
        before = _box_order(surface)
        _drag_tile(surface, "Spacer", "nameLabel", _widget(surface._workbench.canvas_view(), "nameLabel").height() // 4)
        assert _box_order(surface) == before
        assert not surface._session.log.can_undo()
        assert surface.editor_status_sentence() == "A spacer can't go in a form."
    finally:
        surface.release()
        host.deleteLater()


def test_a_buddy_drop_opens_the_new_label_selected(tmp_path: Path) -> None:
    host, surface = _shown(tmp_path, ROWS)
    try:
        canvas = surface._workbench.canvas_view()
        _drag_tile(surface, "QPushButton", "nameLabel", _widget(canvas, "nameLabel").height() // 4)
        editor = _editor(canvas)
        assert editor.text() == "New field:"
        assert editor.selectedText() == "New field:"
        assert len(surface._session.log.entries()) == 1
        label = _named(surface, "label")
        assert isinstance(label, WidgetNode)
        assert _text(label) == "New field:"
    finally:
        surface.release()
        host.deleteLater()


def test_escape_in_the_new_label_editor_writes_no_command(tmp_path: Path) -> None:
    host, surface = _shown(tmp_path, ROWS)
    try:
        canvas = surface._workbench.canvas_view()
        _drag_tile(surface, "QPushButton", "nameLabel", _widget(canvas, "nameLabel").height() // 4)
        editor = _editor(canvas)
        QTest.keyClick(editor, _key("Key_Escape"))
        _flush()
        assert len(surface._session.log.entries()) == 1
        label = _named(surface, "label")
        assert isinstance(label, WidgetNode)
        assert _text(label) == "New field:"
    finally:
        surface.release()
        host.deleteLater()


def _text(node: WidgetNode) -> str:
    value = node.value("text")
    assert isinstance(value, StringValue)
    return value.text


def _shown(tmp_path: Path, text: str) -> tuple:
    host = QWidget()
    host.resize(1280, 800)
    surface = _open(host, text, tmp_path / "form.ui")
    surface.resize(1280, 800)
    host.show()
    surface.show()
    _flush()
    return host, surface


def _open(parent: QWidget, text: str, path: Path) -> FormSurface:
    path.write_text(text, encoding="utf-8")
    app = QApplication.instance()
    assert app is not None

    def create_source_editor() -> QPlainTextEdit:
        return QPlainTextEdit(parent)

    return FormTabProvider().create_surface(
        TabSurfaceRequest(
            file_path=str(path),
            initial_text=text,
            parent=parent,
            theme=tokens_from_palette(app.palette(), force_mode="light"),
            create_source_editor=create_source_editor,  # type: ignore[arg-type]
            open_linked_file=lambda _linked: None,
            project_root=None,
        )
    )


def _drag_tile(surface: FormSurface, class_name: str, target: str, y_bias: int) -> None:
    button = surface.findChild(QPushButton, "formBuilder.insert.%s" % class_name)
    assert button is not None and button.isVisible() and button.width() > 0
    canvas = surface._workbench.canvas_view()
    _press(button, button.rect().center())
    end = _shifted(canvas, target, 0, y_bias)
    _move(canvas.viewport(), end)
    _release(canvas.viewport(), end)


def _editor(canvas: QWidget) -> QLineEdit:
    edits = [
        edit
        for edit in canvas.viewport().findChildren(QLineEdit)
        if edit.isVisible()
    ]
    assert len(edits) == 1
    return edits[0]


def _box_order(surface: FormSurface) -> tuple:
    layout = surface._session.document.root.layout
    assert layout is not None
    names = []
    for item in layout.items:
        content = item.content
        assert content is not None
        names.append(str(getattr(content, "object_name", getattr(content, "name", ""))))
    return tuple(names)


def _named(surface: FormSurface, name: str) -> object:
    found = [
        node
        for node in surface._session.document.iter_preorder()
        if getattr(node, "object_name", None) == name or getattr(node, "name", None) == name
    ]
    assert len(found) == 1
    return found[0]


def _center(canvas: QWidget, name: str) -> QPoint:
    return _shifted(canvas, name, 0, 0)


def _shifted(canvas: QWidget, name: str, dx: int, dy: int) -> QPoint:
    widget = _widget(canvas, name)
    root = canvas.page_widget()
    assert root is not None
    local = widget.rect().center() + QPoint(dx, dy)
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    return canvas.mapFromScene(proxy.mapToScene(widget.mapTo(root, local)))


def _widget(canvas: QWidget, name: str) -> QWidget:
    root = canvas.page_widget()
    assert root is not None
    widget = root.findChild(QWidget, name)
    assert widget is not None
    return widget


def _press(widget: QWidget, pos: QPoint) -> None:
    _send(widget, "MouseButtonPress", pos, "LeftButton", "LeftButton")


def _move(widget: QWidget, pos: QPoint) -> None:
    _send(widget, "MouseMove", pos, "NoButton", "LeftButton")


def _release(widget: QWidget, pos: QPoint) -> None:
    _send(widget, "MouseButtonRelease", pos, "LeftButton", "NoButton")


def _send(widget: QWidget, kind_name: str, pos: QPoint, button_name: str, buttons_name: str) -> None:
    kind = getattr(getattr(QEvent, "Type", QEvent), kind_name)
    event = QMouseEvent(
        kind,
        pos,
        widget.mapToGlobal(pos),
        _mouse(button_name),
        _mouse(buttons_name),
        _mods("NoModifier"),
    )
    QApplication.sendEvent(widget, event)
    _flush()


def _flush() -> None:
    app = QApplication.instance()
    assert app is not None
    app.processEvents()


def _mouse(name: str) -> Qt.MouseButton:
    return getattr(getattr(Qt, "MouseButton", Qt), name)


def _mods(name: str) -> Qt.KeyboardModifier:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def _key(name: str) -> Qt.Key:
    return getattr(getattr(Qt, "Key", Qt), name)
