# pyright: reportAttributeAccessIssue=false
"""Splitter grip and keep-at-content size inside a real main window."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.commands.catalog import SetProperty  # noqa: E402
from app.features.form_builder.engine.query.selection import SelectionSource  # noqa: E402
from app.features.form_builder.engine.sizing import WORD_HUG, effective_word  # noqa: E402
from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode  # noqa: E402
from app.features.form_builder.engine.ui4.values import (  # noqa: E402
    NumberValue,
    RectValue,
    SizePolicyValue,
    SizeValue,
)
from app.features.form_builder.engine.ui4.writer import write_ui  # noqa: E402
from app.features.form_builder.install import form_builder_enabled  # noqa: E402
from app.qt.QtCore import QPoint, Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import (  # noqa: E402
    QAction,
    QApplication,
    QGroupBox,
    QLabel,
    QMenu,
    QSplitter,
    QSplitterHandle,
    QWidget,
)
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.unit

_LISTS = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Ledger</class>
 <widget class="QWidget" name="Ledger">
  <property name="geometry">
   <rect><x>0</x><y>0</y><width>640</width><height>360</height></rect>
  </property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QListWidget" name="customers"/>
   </item>
   <item>
    <widget class="QListWidget" name="invoices"/>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_GROUP = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <property name="geometry">
   <rect><x>0</x><y>0</y><width>420</width><height>280</height></rect>
  </property>
  <layout class="QVBoxLayout" name="pageLayout">
   <property name="spacing">
    <number>12</number>
   </property>
   <item>
    <widget class="QGroupBox" name="receiptGroup">
     <property name="title"><string>Receipt</string></property>
     <layout class="QVBoxLayout" name="receiptLayout">
      <item>
       <widget class="QLineEdit" name="customer"/>
      </item>
      <item>
       <widget class="QLineEdit" name="amount"/>
      </item>
      <item>
       <widget class="QPushButton" name="saveButton">
        <property name="text"><string>Save</string></property>
       </widget>
      </item>
     </layout>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _require() -> None:
    if not form_builder_enabled():
        pytest.skip("form builder is registered on PySide6")


def _key(name: str) -> Qt.Key:
    return getattr(getattr(Qt, "Key", Qt), name)


def _mod(name: str) -> Qt.KeyboardModifier:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def _mouse(name: str) -> Qt.MouseButton:
    return getattr(getattr(Qt, "MouseButton", Qt), name)


def _open(window: MainWindow, qapp: QApplication, path: Path, text: str) -> object:
    path.write_text(text, encoding="utf-8")
    assert window._editor_tab_factory.open_file_in_editor(str(path))  # noqa: SLF001
    stack = window._center_stack  # noqa: SLF001
    assert stack is not None
    stack.setCurrentIndex(1)
    window.resize(1400, 900)
    window.show()
    qapp.processEvents()
    surface = window._tab_content_registry.surface_for_path(str(path))  # noqa: SLF001
    assert surface is not None
    return surface


def _flush(qapp: QApplication) -> None:
    for _ in range(6):
        qapp.processEvents()


def _canvas(surface: object) -> QWidget:
    canvas = surface.findChild(QWidget, "formBuilder.canvas")  # type: ignore[attr-defined]
    assert isinstance(canvas, QWidget)
    return canvas


def _focus(surface: object, qapp: QApplication) -> QWidget:
    canvas = _canvas(surface)
    canvas.window().activateWindow()
    canvas.setFocus()
    _flush(qapp)
    return canvas


def _splitter(canvas: QWidget) -> QSplitter:
    root = canvas.page_widget()  # type: ignore[attr-defined]
    assert isinstance(root, QWidget)
    found = root.findChild(QSplitter)
    assert isinstance(found, QSplitter)
    return found


def _view_point(canvas: QWidget, widget: QWidget, local: QPoint) -> QPoint:
    root = canvas.page_widget()  # type: ignore[attr-defined]
    assert isinstance(root, QWidget)
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    return canvas.mapFromScene(proxy.mapToScene(widget.mapTo(root, local)))


def _drag_handle(qapp: QApplication, canvas: QWidget, handle: QSplitterHandle, shift: int) -> None:
    viewport = canvas.viewport()  # type: ignore[attr-defined]
    assert isinstance(viewport, QWidget)
    origin = handle.rect().center()
    start = _view_point(canvas, handle, origin)
    end = _view_point(canvas, handle, origin + QPoint(shift, 0))
    action = QTest.MouseAction
    button = _mouse("LeftButton")
    mods = _mod("NoModifier")
    QTest.mouseEvent(action.MousePress, viewport, button, mods, start, 0)
    _flush(qapp)
    QTest.mouseEvent(action.MouseMove, viewport, button, mods, end, 0)
    _flush(qapp)
    QTest.mouseEvent(action.MouseRelease, viewport, button, mods, end, 0)
    _flush(qapp)


def _menu_action(menu: QMenu, object_name: str) -> QAction:
    for action in menu.findChildren(QAction):
        if action.objectName() == object_name:
            return action
    raise AssertionError(object_name)


def _click_key(qapp: QApplication, widget: QWidget, name: str) -> None:
    QTest.keyClick(widget, _key(name))
    _flush(qapp)


def _row_label(action: QAction) -> str:
    return action.text().split("\t", 1)[0]


def _highlight(qapp: QApplication, menu: QMenu, label: str) -> None:
    for _ in range(len(menu.actions()) + 1):
        current = menu.activeAction()
        if current is not None and _row_label(current) == label:
            return
        _click_key(qapp, menu, "Key_Down")
    raise AssertionError(label)


def test_a_horizontal_splitter_grip_drag_survives_save_and_undo(
    tmp_path: Path, qapp: QApplication
) -> None:
    _require()
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    path = tmp_path / "ledger.ui"
    reopened: Optional[MainWindow] = None
    try:
        surface = _open(window, qapp, path, _LISTS)
        session = surface.session  # type: ignore[attr-defined]
        document = session.document
        customers = document.by_name("customers")
        invoices = document.by_name("invoices")
        assert len(customers) == 1 and len(invoices) == 1
        session.selection.set(
            (customers[0], invoices[0]),
            current=invoices[0],
            source=SelectionSource.COMMAND,
        )
        original = write_ui(document).text
        canvas = _focus(surface, qapp)
        QTest.keyClick(canvas, _key("Key_3"), _mod("ControlModifier"))
        _flush(qapp)
        splitter = _splitter(canvas)
        assert splitter.count() == 2
        before = tuple(splitter.sizes())
        handle = splitter.handle(1)
        assert isinstance(handle, QSplitterHandle)
        assert handle.width() > 0 and handle.height() > 0
        left = splitter.widget(0)
        assert isinstance(left, QWidget)
        floor = max(left.minimumWidth(), left.minimumSizeHint().width())
        room = before[0] - floor
        shift = room // 2 if room > handle.width() else before[0] // 3
        assert shift > handle.width()
        _drag_handle(qapp, canvas, handle, shift)
        dragged = tuple(splitter.sizes())
        assert dragged != before
        assert len(session.log.entries()) == 2
        assert window._save_workflow.handle_save_action()  # noqa: SLF001
        _flush(qapp)

        reopened = MainWindow(state_root=str((tmp_path / "state-again").resolve()))
        again = _open(reopened, qapp, path, path.read_text(encoding="utf-8"))
        restored = tuple(_splitter(_canvas(again)).sizes())
        assert restored == dragged

        assert session.log.undo()
        assert session.log.undo()
        _flush(qapp)
        assert write_ui(session.document).text == original
        assert not session.log.can_undo()
    finally:
        if reopened is not None:
            shutdown_main_window_for_test(reopened)
        shutdown_main_window_for_test(window)


@pytest.mark.pain("P-14")
def test_keep_at_content_size_holds_a_group_in_a_vertical_layout(
    tmp_path: Path, qapp: QApplication
) -> None:
    _require()
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    path = tmp_path / "invoice.ui"
    reopened: Optional[MainWindow] = None
    try:
        surface = _open(window, qapp, path, _GROUP)
        session = surface.session  # type: ignore[attr-defined]
        document = session.document
        group_id = document.by_name("receiptGroup")
        assert len(group_id) == 1
        session.selection.set(group_id, current=group_id[0], source=SelectionSource.COMMAND)
        layout = document.root.layout
        assert isinstance(layout, LayoutNode)
        spacing = layout.value("spacing")
        assert isinstance(spacing, NumberValue) and spacing.value == 12
        _focus(surface, qapp)
        menu = window.findChild(QMenu, "formBuilder.menu")
        assert isinstance(menu, QMenu)
        menu.popup(window.mapToGlobal(QPoint(8, window.menuBar().height())))
        _flush(qapp)
        assert menu.isVisible()
        keep = _menu_action(menu, "form.action.keepAtContentSize")
        assert keep.isEnabled(), keep.toolTip()
        _highlight(qapp, menu, "Layout")
        _click_key(qapp, menu, "Key_Right")
        layout_menu = window.findChild(QMenu, "formBuilder.menu.Layout")
        assert isinstance(layout_menu, QMenu) and layout_menu.isVisible()
        _highlight(qapp, layout_menu, "Keep at content size")
        _click_key(qapp, layout_menu, "Key_Return")
        _flush(qapp)
        assert len(session.log.entries()) == 1
        toast = surface.findChild(QLabel, "formBuilder.toastText")  # type: ignore[attr-defined]
        assert isinstance(toast, QLabel)
        assert toast.text() == "receiptGroup now keeps its content height"

        root = document.root
        geometry = root.value("geometry")
        assert isinstance(geometry, RectValue)
        session.log.execute(
            SetProperty(root.id, "geometry", RectValue(geometry.x, geometry.y, geometry.width, 800))
        )
        _flush(qapp)
        page = surface.page_widget()  # type: ignore[attr-defined]
        assert isinstance(page, QWidget)
        group = page.findChild(QGroupBox, "receiptGroup")
        assert isinstance(group, QGroupBox)
        assert abs(page.height() - 800) <= 2
        assert abs(group.height() - group.sizeHint().height()) <= 4

        assert window._save_workflow.handle_save_action()  # noqa: SLF001
        _flush(qapp)
        reopened = MainWindow(state_root=str((tmp_path / "state-again").resolve()))
        again = _open(reopened, qapp, path, path.read_text(encoding="utf-8"))
        saved = again.session.document  # type: ignore[attr-defined]
        saved_group = saved.node(saved.by_name("receiptGroup")[0])
        assert isinstance(saved_group, WidgetNode)
        policy = saved_group.value("sizePolicy")
        assert isinstance(policy, SizePolicyValue)
        minimum = saved_group.value("minimumSize")
        maximum = saved_group.value("maximumSize")
        locked = (
            isinstance(minimum, SizeValue)
            and isinstance(maximum, SizeValue)
            and minimum.height == maximum.height
        )
        assert effective_word(policy.vsizetype, locked) == WORD_HUG
        assert policy.verstretch == 0
        saved_layout = saved.root.layout
        assert isinstance(saved_layout, LayoutNode)
        assert saved_layout.field("stretch") in (None, "0")
        saved_spacing = saved_layout.value("spacing")
        assert isinstance(saved_spacing, NumberValue) and saved_spacing.value == 12
    finally:
        if reopened is not None:
            shutdown_main_window_for_test(reopened)
        shutdown_main_window_for_test(window)
