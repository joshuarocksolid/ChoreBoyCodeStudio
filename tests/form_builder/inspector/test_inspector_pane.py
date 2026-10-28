# pyright: reportAttributeAccessIssue=false

from __future__ import annotations

import re
from typing import Optional

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.integration.workbench import OutlinePane
from app.features.form_builder.qtside.inspector import InspectorPane
from app.features.form_builder.qtside.realize import Realizer
from app.qt.QtCore import Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtGui import QKeySequence  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtTest import QTest
from app.qt.QtWidgets import (
    QAction,
    QApplication,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from tests.form_builder.qtside.support import realize

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <layout class="QVBoxLayout" name="mainLayout">
   <item>
    <widget class="QLineEdit" name="email">
     <property name="text"><string>Pay</string></property>
    </widget>
   </item>
   <item>
    <widget class="QLineEdit" name="phone"/>
   </item>
   <item>
    <widget class="QPushButton" name="okButton"/>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

def _control() -> Qt.KeyboardModifier:
    return getattr(Qt, "ControlModifier")

@pytest.mark.parity("R3-29")
def test_keyboard_path_through_the_inspector(qapp: QApplication) -> None:
    session, realizer = realize(_FORM)
    fired = {"f2": 0, "find": 0}
    left = {"n": 0}
    window = QWidget()
    _action(window, QKeySequence(Qt.Key_F2), fired, "f2")
    _action(window, QKeySequence(QKeySequence.Find), fired, "find")
    pane = InspectorPane(
        session,
        realizer,
        data_tab=False,
        on_leave=lambda: left.__setitem__("n", left["n"] + 1),
        parent=window,
    )
    layout = QVBoxLayout(window)
    layout.addWidget(pane)
    window.resize(900, 700)
    window.show()
    _activate(window)
    pane.flush()
    button = session.document.by_name("okButton")[0]
    email = session.document.by_name("email")[0]
    session.selection.set((button,), source=SelectionSource.PROGRAM)
    pane.flush()
    search = pane.findChild(QLineEdit, "formBuilder.inspectorSearch")
    name = pane.findChild(QLineEdit, "formBuilder.inspectorName")
    assert search is not None and name is not None
    name.setFocus()
    QTest.keyClick(window, Qt.Key_F, _control())
    assert qapp.focusWidget() is search
    QTest.keyClicks(search, "text")
    assert "text" in search.text().lower()
    session.selection.set((email,), source=SelectionSource.PROGRAM)
    qapp.processEvents()
    assert qapp.focusWidget() is search
    QTest.keyClick(search, Qt.Key_Escape)
    assert search.text() == ""
    session.selection.set((button,), source=SelectionSource.PROGRAM)
    QTest.keyClick(window, Qt.Key_F2)
    assert qapp.focusWidget() is name
    assert name.selectedText() == name.text()
    QTest.keyClicks(name, "1bad")
    QTest.keyClick(name, Qt.Key_Return)
    error = pane.findChild(QLabel, "formBuilder.inspectorNameError")
    assert error is not None
    assert "FB011" in error.text()
    assert name.text() == "1bad"
    button_node = session.document.node(button)
    assert isinstance(button_node, WidgetNode)
    assert button_node.object_name == "okButton"
    QTest.keyClick(name, Qt.Key_Escape)
    assert name.text() == "okButton"
    assert "FB011" not in error.text()
    QTest.keyClick(name, Qt.Key_Escape)
    assert left["n"] == 1
    assert fired == {"f2": 0, "find": 0}
    pane.dispose()
    realizer.dispose()
    session.dispose()
    window.close()

@pytest.mark.parity("R3-145")
def test_commit_keeps_focus_in_the_editor(qapp: QApplication) -> None:
    session, realizer = realize(_FORM)
    window = _shown(session, realizer)
    pane = window.findChild(InspectorPane, "formBuilder.inspector")
    assert pane is not None
    email = session.document.by_name("email")[0]
    session.selection.set((email,), source=SelectionSource.PROGRAM)
    pane.flush()
    editor = _text_editor(pane)
    editor.setFocus()
    editor.selectAll()
    QTest.keyClicks(editor, "Hello")
    QTest.keyClick(editor, Qt.Key_Return)
    pane.flush()
    assert qapp.focusWidget() is editor
    row = pane.findChild(QWidget, "formBuilder.row.text")
    assert row is not None
    bar = row.findChild(QWidget, "formBuilder.rowChanged")
    reset = row.findChild(QWidget, "formBuilder.rowReset")
    assert bar is not None and bar.isVisible() and bar.property("fbChanged") == "true"
    assert reset is not None and reset.isVisible()
    _close(window, pane, realizer, session)

@pytest.mark.parity("R3-28")
def test_outline_click_fills_the_header(qapp: QApplication) -> None:
    del qapp
    session, realizer = realize(_FORM)
    window = QWidget()
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    outline = OutlinePane(
        lambda node_id: session.selection.set((node_id,), source=SelectionSource.OUTLINE),
        lambda _collapsed: None,
        window,
    )
    layout = QVBoxLayout(window)
    layout.addWidget(outline)
    layout.addWidget(pane)
    outline.rebuild(session.document, None)
    window.resize(480, 640)
    window.show()
    chosen = _tree_item(outline.tree, "okButton")
    outline.tree.setCurrentItem(chosen)
    name = pane.findChild(QLineEdit, "formBuilder.inspectorName")
    kind = pane.findChild(QLabel, "formBuilder.inspectorClass")
    assert name is not None and kind is not None
    assert name.text() == "okButton"
    assert "QPushButton" in kind.text()
    _close(window, pane, realizer, session)

@pytest.mark.parity("R3-28")
def test_crumb_click_selects_the_ancestor(qapp: QApplication) -> None:
    del qapp
    session, realizer = realize(_FORM)
    window = _shown(session, realizer)
    pane = window.findChild(InspectorPane, "formBuilder.inspector")
    assert pane is not None
    button = session.document.by_name("okButton")[0]
    session.selection.set((button,), source=SelectionSource.PROGRAM)
    pane.flush()
    crumbs = pane.findChild(QLabel, "formBuilder.inspectorCrumbs")
    assert crumbs is not None and crumbs.isVisible()
    found = re.search(r'href="(\d+)"', crumbs.text())
    assert found is not None
    seen = []
    session.selection.subscribe(lambda change: seen.append(change))
    crumbs.linkActivated.emit(found.group(1))
    assert seen
    assert seen[-1].source is SelectionSource.INSPECTOR
    assert session.selection.state.current != button
    name = pane.findChild(QLineEdit, "formBuilder.inspectorName")
    assert name is not None
    assert name.text() == "Invoice"
    _close(window, pane, realizer, session)

@pytest.mark.parity("R3-146")
def test_changed_marker_and_reset(qapp: QApplication) -> None:
    del qapp
    session, realizer = realize(_FORM)
    window = _shown(session, realizer)
    pane = window.findChild(InspectorPane, "formBuilder.inspector")
    assert pane is not None
    phone = session.document.by_name("phone")[0]
    session.selection.set((phone,), source=SelectionSource.PROGRAM)
    pane.flush()
    editor = _text_editor(pane)
    row = pane.findChild(QWidget, "formBuilder.row.text")
    assert row is not None
    # An unchanged row has no changed bar or visible reset; both are made on first use.
    unchanged_bar = row.findChild(QWidget, "formBuilder.rowChanged")
    assert unchanged_bar is None or unchanged_bar.property("fbChanged") != "true"
    unchanged_reset = row.findChild(QWidget, "formBuilder.rowReset")
    assert unchanged_reset is None or not unchanged_reset.isVisible()
    editor.setFocus()
    QTest.keyClicks(editor, "Hi")
    QTest.keyClick(editor, Qt.Key_Return)
    pane.flush()
    bar = row.findChild(QWidget, "formBuilder.rowChanged")
    reset = row.findChild(QWidget, "formBuilder.rowReset")
    assert bar is not None and reset is not None
    assert bar.property("fbChanged") == "true" and reset.isVisible()
    assert session.document.node(phone).prop("text") is not None
    reset.click()
    pane.flush()
    assert session.document.node(phone).prop("text") is None
    # The bar keeps its 2 px slot and turns transparent, so the row does not shift.
    assert bar.property("fbChanged") == "false"
    _close(window, pane, realizer, session)

@pytest.mark.parity("R3-147", "R3-19")
def test_multi_select_edit_is_one_undo(qapp: QApplication) -> None:
    """One inspector edit changes every selected widget in one undo step."""
    del qapp
    session, realizer = realize(_FORM)
    window = _shown(session, realizer)
    pane = window.findChild(InspectorPane, "formBuilder.inspector")
    assert pane is not None
    email = session.document.by_name("email")[0]
    phone = session.document.by_name("phone")[0]
    session.selection.set((email, phone), source=SelectionSource.PROGRAM)
    pane.flush()
    editor = _text_editor(pane)
    editor.setFocus()
    editor.selectAll()
    QTest.keyClicks(editor, "Both")
    QTest.keyClick(editor, Qt.Key_Return)
    pane.flush()
    assert session.log.undo_label() == "Edit"
    assert len(session.log.entries()) == 1
    assert session.log.undo() is True
    assert session.log.undo() is False
    email_text = session.document.node(email).prop("text")
    assert email_text is not None and isinstance(email_text.value, StringValue)
    assert email_text.value.text == "Pay"
    assert session.document.node(phone).prop("text") is None
    _close(window, pane, realizer, session)

def _action(window: QWidget, shortcut: QKeySequence, fired: dict, key: str) -> QAction:
    action = QAction(window)
    action.setShortcut(shortcut)
    action.setShortcutContext(Qt.WindowShortcut)
    action.triggered.connect(lambda: fired.__setitem__(key, fired[key] + 1))
    window.addAction(action)
    return action

def _shown(session: FormSession, realizer: Realizer) -> QWidget:
    window = QWidget()
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    layout = QVBoxLayout(window)
    layout.addWidget(pane)
    window.resize(900, 700)
    window.show()
    _activate(window)
    pane.flush()
    return window

def _activate(window: QWidget) -> None:
    app = QApplication.instance()
    if isinstance(app, QApplication):
        app.setActiveWindow(window)

def _text_editor(pane: QWidget) -> QLineEdit:
    row = pane.findChild(QWidget, "formBuilder.row.text")
    assert row is not None
    editor = row.findChild(QLineEdit)
    assert editor is not None
    return editor

def _tree_item(tree: QTreeWidget, needle: str) -> QTreeWidgetItem:
    def walk(item: QTreeWidgetItem) -> Optional[QTreeWidgetItem]:
        if needle in item.text(0):
            return item
        for index in range(item.childCount()):
            child = item.child(index)
            if child is None:
                continue
            found = walk(child)
            if found is not None:
                return found
        return None

    for index in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(index)
        if top is None:
            continue
        found = walk(top)
        if found is not None:
            return found
    raise AssertionError(needle)


def _close(window: QWidget, pane: InspectorPane, realizer: Realizer, session: FormSession) -> None:
    pane.dispose()
    realizer.dispose()
    session.dispose()
    window.close()
