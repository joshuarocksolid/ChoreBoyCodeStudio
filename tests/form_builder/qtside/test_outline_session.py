# pyright: reportAttributeAccessIssue=false
"""Keyboard-only outline session inside a real main window."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.query.outline import project  # noqa: E402
from app.features.form_builder.engine.ui4.writer import write_ui  # noqa: E402
from app.features.form_builder.install import form_builder_enabled  # noqa: E402
from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import (  # noqa: E402
    QApplication,
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <property name="geometry"><rect><x>0</x><y>0</y><width>520</width><height>600</height></rect></property>
  <layout class="QVBoxLayout" name="mainLayout">
   <item>
    <widget class="QLabel" name="emailLabel">
     <property name="text"><string>Email:</string></property>
     <property name="buddy"><cstring>email</cstring></property>
    </widget>
   </item>
   <item><widget class="QLineEdit" name="email"/></item>
   <item>
    <widget class="QGroupBox" name="receiptGroup">
     <property name="title"><string>Receipt</string></property>
    </widget>
   </item>
   <item>
    <widget class="QCheckBox" name="printCopy">
     <property name="text"><string>Print copy</string></property>
    </widget>
   </item>
   <item>
    <widget class="QTabWidget" name="tabs">
     <property name="currentIndex"><number>0</number></property>
     <widget class="QWidget" name="pageA"><attribute name="title"><string>First</string></attribute></widget>
     <widget class="QWidget" name="pageB"><attribute name="title"><string>Second</string></attribute></widget>
     <widget class="QWidget" name="pageC"><attribute name="title"><string>Third</string></attribute></widget>
    </widget>
   </item>
   <item>
    <layout class="QGridLayout" name="grid">
     <item row="0" column="0"><widget class="QLabel" name="cellA"><property name="text"><string>A</string></property></widget></item>
     <item row="0" column="1"><widget class="QLabel" name="cellB"><property name="text"><string>B</string></property></widget></item>
     <item row="1" column="0"><widget class="QLabel" name="cellC"><property name="text"><string>C</string></property></widget></item>
    </layout>
   </item>
   <item>
    <widget class="QPushButton" name="okButton">
     <property name="text"><string>OK</string></property>
    </widget>
   </item>
  </layout>
 </widget>
 <tabstops>
  <tabstop>email</tabstop>
  <tabstop>printCopy</tabstop>
  <tabstop>okButton</tabstop>
 </tabstops>
 <resources/>
 <connections>
  <connection>
   <sender>email</sender>
   <signal>returnPressed()</signal>
   <receiver>okButton</receiver>
   <slot>click()</slot>
  </connection>
 </connections>
</ui>
"""


def _require() -> None:
    if not form_builder_enabled():
        pytest.skip("form builder is registered on PySide6")


def _key(name: str) -> Qt.Key:
    return getattr(getattr(Qt, "Key", Qt), name)


def _mod(name: str) -> Qt.KeyboardModifier:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def _open(window: MainWindow, qapp: QApplication, path: Path, text: str) -> object:
    path.write_text(text, encoding="utf-8")
    assert window._editor_tab_factory.open_file_in_editor(str(path))  # noqa: SLF001
    window._center_stack.setCurrentIndex(1)  # noqa: SLF001
    window.resize(1400, 900)
    window.show()
    qapp.processEvents()
    surface = window._tab_content_registry.surface_for_path(str(path))  # noqa: SLF001
    assert surface is not None
    return surface


def _tree(surface: object) -> QTreeWidget:
    tree = surface.findChild(QTreeWidget, "formBuilder.structure")  # type: ignore[attr-defined]
    assert isinstance(tree, QTreeWidget)
    return tree


def _item(tree: QTreeWidget, text: str) -> QTreeWidgetItem:
    found = None

    def walk(item: QTreeWidgetItem) -> None:
        nonlocal found
        if item.text(0) == text:
            found = item
        for index in range(item.childCount()):
            child = item.child(index)
            if child is not None:
                walk(child)

    for index in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(index)
        if top is not None:
            walk(top)
    assert isinstance(found, QTreeWidgetItem)
    return found


def _ids(tree: QTreeWidget) -> Tuple[int, ...]:
    role = int(getattr(Qt, "UserRole"))
    found = []

    def walk(item: QTreeWidgetItem) -> None:
        raw = item.data(0, role)
        if raw is not None:
            found.append(int(raw))
        for index in range(item.childCount()):
            child = item.child(index)
            if child is not None:
                walk(child)

    for index in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(index)
        if top is not None:
            walk(top)
    return tuple(found)


def _matches(tree: QTreeWidget, surface: object) -> None:
    session = surface.session  # type: ignore[attr-defined]
    forest = project(session.document, frozenset(), lambda name: name)
    assert _ids(tree) == tuple(int(row.node) for row in forest.rows)


def _stay(surface: object) -> None:
    focus = QApplication.focusWidget()
    pane = surface.findChild(QWidget, "formBuilder.outline")  # type: ignore[attr-defined]
    assert isinstance(focus, QWidget) and isinstance(pane, QWidget)
    assert focus is pane or pane.isAncestorOf(focus)


def _select(tree: QTreeWidget, qapp: QApplication, text: str) -> QTreeWidgetItem:
    item = _item(tree, text)
    tree.setCurrentItem(item)
    tree.setFocus()
    qapp.processEvents()
    return item


def _press(widget: QWidget, qapp: QApplication, key: str, *mods: str) -> None:
    modifier = _mod("NoModifier")
    for name in mods:
        modifier = modifier | _mod(name)  # type: ignore[operator]
    QTest.keyClick(widget, _key(key), modifier)
    qapp.processEvents()


def test_a_keyboard_session_stays_in_the_outline(tmp_path: Path, qapp: QApplication) -> None:
    _require()
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    path = tmp_path / "invoice.ui"
    try:
        surface = _open(window, qapp, path, _FORM)
        tree = _tree(surface)
        _select(tree, qapp, "Invoice")
        _stay(surface)
        before = tree.currentItem()
        _press(tree, qapp, "Key_Down")
        _stay(surface)
        assert tree.currentItem() is not before
        _press(tree, qapp, "Key_End")
        _press(tree, qapp, "Key_Home")
        _stay(surface)
        assert tree.currentItem() is not None
        assert tree.currentItem().text(0) == "Invoice"

        _select(tree, qapp, "email")
        _press(tree, qapp, "Key_F2")
        editor = QApplication.focusWidget()
        assert isinstance(editor, QLineEdit)
        _stay(surface)
        editor.selectAll()
        QTest.keyClicks(editor, "class")
        qapp.processEvents()
        _press(editor, qapp, "Key_Return")
        error = surface.findChild(QLabel, "formBuilder.outlineNameError")  # type: ignore[attr-defined]
        assert isinstance(error, QLabel) and error.isVisible()
        assert error.text() == "class is a Python word, so it can't be a name."
        _stay(surface)
        editor = QApplication.focusWidget()
        assert isinstance(editor, QLineEdit)
        editor.selectAll()
        QTest.keyClicks(editor, "customerEmail")
        qapp.processEvents()
        _press(editor, qapp, "Key_Return")
        _stay(surface)
        assert _item(tree, "customerEmail")
        _matches(tree, surface)

        _select(tree, qapp, "printCopy")
        _press(tree, qapp, "Key_Tab")
        _stay(surface)
        _matches(tree, surface)
        assert surface.session.log.entries()[-1].label == "Nest"  # type: ignore[attr-defined]
        _press(tree, qapp, "Key_Backtab", "ShiftModifier")
        _stay(surface)
        _matches(tree, surface)

        _select(tree, qapp, "pageA")
        _press(tree, qapp, "Key_Up", "AltModifier")
        _stay(surface)
        assert tree.currentItem() is not None
        assert tree.currentItem().text(0) == "pageA"
        spoken = surface.editor_status_sentence()  # type: ignore[attr-defined]
        shown = window._status_controller.editor_status_text()  # noqa: SLF001
        assert "already the first page" in spoken
        assert "already the first page" in shown

        _select(tree, qapp, "cellA")
        _press(tree, qapp, "Key_Down", "AltModifier")
        _stay(surface)
        assert tree.currentItem().text(0) == "cellA"

        _select(tree, qapp, "cellB")
        _press(tree, qapp, "Key_Down", "AltModifier")
        _matches(tree, surface)
        _press(tree, qapp, "Key_Z", "ControlModifier")
        _matches(tree, surface)
        order = _ids(tree)
        assert order.index(int(surface.session.document.by_name("cellA")[0])) < order.index(  # type: ignore[attr-defined]
            int(surface.session.document.by_name("cellB")[0])  # type: ignore[attr-defined]
        )

        _press(tree, qapp, "Key_F", "ControlModifier")
        field = surface.findChild(QLineEdit, "formBuilder.outlineFilter")  # type: ignore[attr-defined]
        assert isinstance(field, QLineEdit) and field.isVisible()
        _stay(surface)
        _press(field, qapp, "Key_Escape")
        _stay(surface)
        assert not field.isVisible()

        _select(tree, qapp, "customerEmail")
        _press(tree, qapp, "Key_Delete")
        confirm = surface.findChild(QFrame, "formBuilder.outlineConfirm")  # type: ignore[attr-defined]
        delete = surface.findChild(QPushButton, "formBuilder.outlineDelete")  # type: ignore[attr-defined]
        assert isinstance(confirm, QFrame) and confirm.isVisible()
        assert isinstance(delete, QPushButton)
        _stay(surface)
        _press(delete, qapp, "Key_Escape")
        _stay(surface)
        assert not confirm.isVisible()
        assert tree.currentItem().text(0) == "customerEmail"

        _select(tree, qapp, "cellC")
        _press(tree, qapp, "Key_Delete")
        _stay(surface)
        _matches(tree, surface)
        assert not surface.session.document.by_name("cellC")  # type: ignore[attr-defined]
        current = tree.currentItem()
        assert current is not None and current.text(0) in ("cellB", "grid")
        _press(tree, qapp, "Key_Z", "ControlModifier")
        _matches(tree, surface)
        assert surface.session.document.by_name("cellC")  # type: ignore[attr-defined]
        _press(tree, qapp, "Key_Z", "ControlModifier", "ShiftModifier")
        _matches(tree, surface)
        assert not surface.session.document.by_name("cellC")  # type: ignore[attr-defined]

        _select(tree, qapp, "okButton")
        _press(tree, qapp, "Key_Slash")
        listed = surface.findChild(QListWidget, "formBuilder.outlineInsertList")  # type: ignore[attr-defined]
        assert isinstance(listed, QListWidget) and listed.isVisible()
        _stay(surface)
        _press(listed, qapp, "Key_Escape")
        _stay(surface)

        saved = write_ui(surface.session.document).text  # type: ignore[attr-defined]
        path.write_text(saved, encoding="utf-8")
    finally:
        shutdown_main_window_for_test(window)

    reopened = MainWindow(state_root=str((tmp_path / "state-again").resolve()))
    try:
        again = _open(reopened, qapp, path, path.read_text(encoding="utf-8"))
        tree = _tree(again)
        qapp.processEvents()
        assert _item(tree, "customerEmail")
        assert _item(tree, "pageA").data(0, int(getattr(Qt, "UserRole")) + 1) == "First"
        _matches(tree, again)
        _select(tree, qapp, "okButton")
        _stay(again)
    finally:
        shutdown_main_window_for_test(reopened)
