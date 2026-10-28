# pyright: reportAttributeAccessIssue=false
"""Outline pane keyboard, filter, delete, and page order."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Dict, Iterator, Optional, Tuple, cast

import pytest

from app.qt.QtCore import QEvent, QPoint, QRect, Qt
from app.qt.QtGui import QColor, QImage, QKeyEvent, QPainter
from app.qt.QtTest import QTest
from app.qt.qt_compat import enum_value
from app.qt.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QStyleOptionViewItem,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)
from app.features.form_builder.engine.commands.catalog import DeleteNodes, SetProperty
from app.features.form_builder.engine.commands.drop_plan import auto_commands
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.drop_target import DropPayload
from app.features.form_builder.engine.query.outline import layout_row, project
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import NumberValue, StringValue
from app.features.form_builder.integration.workbench import OutlinePane
from app.features.form_builder.qtside.canvas.core.palette import fragment_for
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.qtside.support import form, open_session

pytestmark = pytest.mark.usefixtures("qapp")

_IDENTIFIER = "Names use letters, digits and _, and can't start with a digit."


def _buttons(count: int) -> str:
    rows = "\n".join(
        '   <item><widget class="QPushButton" name="field%d">'
        '<property name="text"><string>B%d</string></property></widget></item>' % (index, index)
        for index in range(count)
    )
    return form(
        'class="QWidget" name="Form"',
        '  <layout class="QVBoxLayout" name="verticalLayout">\n%s\n  </layout>' % rows,
    )


def _pair() -> str:
    return form(
        'class="QWidget" name="Form"',
        """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QLabel" name="shop"><property name="text"><string>Shop</string></property></widget></item>
   <item><widget class="QPushButton" name="other"><property name="text"><string>Other</string></property></widget></item>
  </layout>
""",
    )


def _tabs() -> str:
    return form(
        'class="QTabWidget" name="tabs"',
        """
  <property name="currentIndex"><number>0</number></property>
  <widget class="QWidget" name="pageA">
   <attribute name="title"><string>First</string></attribute>
  </widget>
  <widget class="QWidget" name="pageB">
   <attribute name="title"><string>Second</string></attribute>
  </widget>
""",
    )


def _email() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <widget class="QLabel" name="emailLabel">
   <property name="text"><string>Email:</string></property>
   <property name="buddy"><cstring>email</cstring></property>
  </widget>
  <widget class="QLineEdit" name="email"/>
  <widget class="QPushButton" name="Invoice">
   <property name="text"><string>Save</string></property>
  </widget>
  <widget class="QLineEdit" name="spare"/>
 </widget>
 <tabstops>
  <tabstop>email</tabstop>
  <tabstop>spare</tabstop>
 </tabstops>
 <connections>
  <connection>
   <sender>email</sender>
   <signal>returnPressed()</signal>
   <receiver>Invoice</receiver>
   <slot>accept()</slot>
  </connection>
 </connections>
</ui>
"""


def _long_name() -> str:
    name = "N" * 48
    return form(
        'class="QWidget" name="Form"',
        """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="%s"><property name="text"><string>Hi</string></property></widget></item>
  </layout>
"""
        % name,
    )


@contextmanager
def _opened(
    qapp: QApplication,
    text: str,
    name: str,
    place: Optional[Callable[[str], None]] = None,
    width: int = 320,
    height: int = 480,
) -> Iterator[Tuple[OutlinePane, FormSession]]:
    parent = QWidget()
    parent.resize(width, height)
    opened: Dict[str, FormSession] = {}

    def pick(node: NodeId) -> None:
        # What the form surface does with an outline pick.
        opened["session"].selection.set((node,), source=SelectionSource.OUTLINE)

    pane = OutlinePane(pick, lambda _collapsed: None, parent)
    pane.setGeometry(0, 0, width, height)
    session = open_session(text, "/tmp/cbcs-outline-%s.ui" % name)
    opened["session"] = session
    parent.show()
    qapp.setActiveWindow(parent)
    pane.attach(session, place or (lambda _key: None))
    pane.tree.setFocus()
    qapp.processEvents()
    try:
        yield pane, session
    finally:
        session.dispose()
        parent.close()
        parent.deleteLater()
        qapp.processEvents()


def _key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


def _mod(name: str) -> object:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def _focus(qapp: QApplication) -> QWidget:
    qapp.processEvents()
    widget = QApplication.focusWidget()
    assert isinstance(widget, QWidget)
    return widget


def _editor(qapp: QApplication) -> QLineEdit:
    widget = _focus(qapp)
    assert widget.objectName() == "formBuilder.outlineRename"
    assert isinstance(widget, QLineEdit)
    return widget


def _find_item(tree: QTreeWidget, text: str) -> QTreeWidgetItem:
    found = _walk_item(tree, text)
    assert found is not None
    return found


def _walk_item(tree: QTreeWidget, text: str) -> Optional[QTreeWidgetItem]:
    def walk(item: QTreeWidgetItem) -> Optional[QTreeWidgetItem]:
        if item.text(0) == text:
            return item
        for index in range(item.childCount()):
            child = item.child(index)
            if child is None:
                continue
            match = walk(child)
            if match is not None:
                return match
        return None

    for index in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(index)
        if top is None:
            continue
        match = walk(top)
        if match is not None:
            return match
    return None


def _items(tree: QTreeWidget) -> Dict[int, QTreeWidgetItem]:
    found: Dict[int, QTreeWidgetItem] = {}
    role = int(getattr(Qt, "UserRole"))

    def walk(item: QTreeWidgetItem) -> None:
        raw = item.data(0, role)
        if raw is not None:
            found[int(raw)] = item
        for index in range(item.childCount()):
            child = item.child(index)
            if child is not None:
                walk(child)

    for index in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(index)
        if top is not None:
            walk(top)
    return found


def _id(session: FormSession, name: str) -> NodeId:
    found = session.document.by_name(name)
    assert found
    return found[0]


def _show(pane: OutlinePane, session: FormSession, name: str) -> NodeId:
    node = _id(session, name)
    session.selection.set((node,), current=node, source=SelectionSource.OUTLINE)
    pane.show_current(node)
    pane.tree.setFocus()
    return node


def _pages(session: FormSession) -> Tuple[str, ...]:
    host = session.document.node(_id(session, "tabs"))
    assert isinstance(host, WidgetNode)
    return tuple(child.object_name for child in host.child_widgets)


def _current_index(session: FormSession) -> int:
    host = session.document.node(_id(session, "tabs"))
    assert isinstance(host, WidgetNode)
    entry = host.prop("currentIndex")
    if entry is None or not isinstance(entry.value, NumberValue):
        return 0
    return int(entry.value.value)


def _extra(pane: OutlinePane, tip: str) -> QToolButton:
    for button in pane.findChildren(QToolButton, "formBuilder.sectionExtra"):
        if button.accessibleName() == tip:
            assert isinstance(button, QToolButton)
            return button
    raise AssertionError(tip)


def _filter_line(pane: OutlinePane) -> QLineEdit:
    line = pane.findChild(QLineEdit, "formBuilder.outlineFilter")
    assert isinstance(line, QLineEdit)
    return line


def _type_filter(qapp: QApplication, pane: OutlinePane, text: str) -> QLineEdit:
    QTest.keyClick(pane.tree, _key("Key_F"), _mod("ControlModifier"))
    qapp.processEvents()
    line = _filter_line(pane)
    assert _focus(qapp) is line
    QTest.keyClicks(line, text)
    qapp.processEvents()
    return line


@pytest.mark.pain("P-25")
def test_keyboard_rename_keeps_focus_on_each_name(qapp: QApplication) -> None:
    with _opened(qapp, _buttons(10), "rename-ten", height=640) as (pane, session):
        _show(pane, session, "field0")
        qapp.processEvents()
        QTest.keyClick(pane.tree, _key("Key_F2"))
        for index in range(10):
            editor = _editor(qapp)
            assert editor is pane or pane.isAncestorOf(editor)
            QTest.keyClicks(editor, "n%d" % index)
            qapp.processEvents()
            assert _focus(qapp) is editor
            assert editor.text() == "n%d" % index
            QTest.keyClick(editor, _key("Key_Tab"))
            qapp.processEvents()
            focus = _focus(qapp)
            assert focus is pane.tree or focus.objectName() == "formBuilder.outlineRename"
        assert _focus(qapp) is pane.tree
        for index in range(10):
            assert session.document.by_name("n%d" % index)


def test_invalid_tab_keeps_the_old_name(qapp: QApplication) -> None:
    with _opened(qapp, _buttons(1), "rename-bad") as (pane, session):
        _show(pane, session, "field0")
        QTest.keyClick(pane.tree, _key("Key_F2"))
        editor = _editor(qapp)
        QTest.keyClicks(editor, "1bad")
        QTest.keyClick(editor, _key("Key_Tab"))
        qapp.processEvents()
        assert _focus(qapp) is editor
        error = pane.findChild(QLabel, "formBuilder.outlineNameError")
        assert isinstance(error, QLabel)
        assert error.text() == _IDENTIFIER
        assert error.isVisible()
        assert session.document.by_name("field0")
        assert not session.document.by_name("1bad")


def test_name_error_stays_inside_its_row(qapp: QApplication) -> None:
    with _opened(qapp, _buttons(3), "rename-overlap", height=400) as (pane, session):
        _show(pane, session, "field0")
        QTest.keyClick(pane.tree, _key("Key_F2"))
        editor = _editor(qapp)
        QTest.keyClicks(editor, "1bad")
        QTest.keyClick(editor, _key("Key_Tab"))
        qapp.processEvents()
        error = pane.findChild(QLabel, "formBuilder.outlineNameError")
        assert isinstance(error, QLabel)
        assert error.isVisible()
        nxt = pane.tree.visualItemRect(_find_item(pane.tree, "field1"))
        err = error.geometry()
        assert not err.intersects(nxt)
        assert err.bottom() <= nxt.top()


def test_a_narrow_name_error_fits_beside_the_scrollbar(qapp: QApplication) -> None:
    # Twelve rows just fit; the error row is what brings in the vertical scrollbar.
    with _opened(qapp, _buttons(10), "rename-narrow", width=236, height=330) as (pane, session):
        pane.setFixedWidth(236)
        _show(pane, session, "field3")
        QTest.keyClick(pane.tree, _key("Key_F2"))
        editor = _editor(qapp)
        editor.selectAll()
        QTest.keyClicks(editor, "field1")
        QTest.keyClick(editor, _key("Key_Return"))
        qapp.processEvents()
        error = pane.findChild(QLabel, "formBuilder.outlineNameError")
        assert isinstance(error, QLabel) and error.isVisible()
        assert error.text() == "Another widget is already called field1."
        viewport = pane.tree.viewport().width()
        assert pane.tree.verticalScrollBar().isVisible()
        assert editor.geometry().right() < viewport
        assert error.geometry().right() < viewport
        assert error.heightForWidth(error.width()) <= error.height()


def test_escape_cancels_a_rename(qapp: QApplication) -> None:
    with _opened(qapp, _buttons(1), "rename-esc") as (pane, session):
        _show(pane, session, "field0")
        QTest.keyClick(pane.tree, _key("Key_F2"))
        editor = _editor(qapp)
        QTest.keyClicks(editor, "tempName")
        QTest.keyClick(editor, _key("Key_Escape"))
        qapp.processEvents()
        assert _focus(qapp) is pane.tree
        assert not editor.isVisible()
        assert session.document.by_name("field0")
        assert not session.document.by_name("tempName")


def test_enter_commits_a_rename(qapp: QApplication) -> None:
    with _opened(qapp, _buttons(2), "rename-enter") as (pane, session):
        _show(pane, session, "field0")
        QTest.keyClick(pane.tree, _key("Key_F2"))
        editor = _editor(qapp)
        QTest.keyClicks(editor, "savedName")
        QTest.keyClick(editor, _key("Key_Return"))
        qapp.processEvents()
        assert _focus(qapp) is pane.tree
        assert session.document.by_name("savedName")
        assert not session.document.by_name("field0")
        assert session.document.by_name("field1")


def test_a_rename_keeps_other_row_items(qapp: QApplication) -> None:
    with _opened(qapp, _buttons(2), "rename-identity") as (pane, session):
        before = _items(pane.tree)
        _show(pane, session, "field0")
        QTest.keyClick(pane.tree, _key("Key_F2"))
        editor = _editor(qapp)
        QTest.keyClicks(editor, "renamed")
        QTest.keyClick(editor, _key("Key_Return"))
        qapp.processEvents()
        after = _items(pane.tree)
        assert set(before) == set(after)
        for node, item in before.items():
            assert after[node] is item
        assert _find_item(pane.tree, "renamed") is before[int(_id(session, "renamed"))]


def test_a_text_edit_keeps_other_row_items(qapp: QApplication) -> None:
    with _opened(qapp, _pair(), "caption") as (pane, session):
        before = _items(pane.tree)
        shop = _id(session, "shop")
        session.log.execute(SetProperty(shop, "text", StringValue("Save")))
        pane.patch_rows(session.document, shop, (shop,))
        qapp.processEvents()
        after = _items(pane.tree)
        for node, item in before.items():
            assert after[node] is item
        assert "\u201cSave\u201d" in after[int(shop)].toolTip(0)
        assert after[int(_id(session, "other"))].text(0) == "other"


def test_page_rows_use_the_title(qapp: QApplication) -> None:
    with _opened(qapp, _tabs(), "page-rows") as (pane, _session):
        page = _find_item(pane.tree, "pageA")
        assert _find_item(pane.tree, "pageB")
        assert page.data(0, int(getattr(Qt, "UserRole")) + 1) == "Page 1 \u00b7 First"


def test_alt_down_reorders_a_tab_page(qapp: QApplication) -> None:
    with _opened(qapp, _tabs(), "page-alt") as (pane, session):
        _show(pane, session, "pageA")
        QTest.keyClick(pane.tree, _key("Key_Down"), _mod("AltModifier"))
        qapp.processEvents()
        assert _focus(qapp) is pane.tree
        assert _pages(session) == ("pageB", "pageA")
        assert _current_index(session) == 1
        caption = int(getattr(Qt, "UserRole")) + 1
        assert _find_item(pane.tree, "pageA").data(0, caption) == "Page 2 \u00b7 First"
        assert _find_item(pane.tree, "pageB").data(0, caption) == "Page 1 \u00b7 Second"


def test_tab_with_no_current_row_selects_the_first_row(qapp: QApplication) -> None:
    with _opened(qapp, _pair(), "tab-first") as (pane, session):
        pane.tree.setCurrentItem(None)
        pane.tree.setFocus()
        QTest.keyClick(pane.tree, _key("Key_Tab"))
        qapp.processEvents()
        assert _focus(qapp) is pane.tree
        assert pane.tree.currentItem() is pane.tree.topLevelItem(0)


def test_a_page_drop_reorders_the_page(qapp: QApplication) -> None:
    with _opened(qapp, _tabs(), "page-drop") as (pane, session):
        page_b = _id(session, "pageB")
        posted = []
        pane.set_drop_bridge(posted.append, lambda: DropPayload("widget", (page_b,)))
        for _cycle in range(3):
            qapp.processEvents()
        target = _find_item(pane.tree, "pageA")
        rect = pane.tree.visualItemRect(target)
        assert rect.height() > 0
        pane.receive_drop(QPoint(rect.x() + 10, rect.y() + 1))
        qapp.processEvents()
        assert posted == []
        assert _pages(session) == ("pageB", "pageA")
        assert _current_index(session) == 1


def test_the_find_button_opens_the_filter(qapp: QApplication) -> None:
    with _opened(qapp, _pair(), "find-button") as (pane, _session):
        _extra(pane, "Find a widget").click()
        qapp.processEvents()
        line = _filter_line(pane)
        assert line.isVisible()
        assert _focus(qapp) is line


def test_filter_empty_copy_uses_the_query(qapp: QApplication) -> None:
    with _opened(qapp, _pair(), "filter-empty") as (pane, _session):
        _type_filter(qapp, pane, "xyz")
        label = pane.findChild(QLabel, "formBuilder.outlineEmpty")
        clear = pane.findChild(QPushButton, "formBuilder.outlineClear")
        assert isinstance(label, QLabel)
        assert isinstance(clear, QPushButton)
        assert label.text() == "No widget matches \u201cxyz\u201d."
        assert label.isVisible()
        assert clear.text() == "Clear"
        assert clear.isVisible()


def test_filter_paints_ancestors_faint(qapp: QApplication) -> None:
    with _opened(qapp, _pair(), "filter-faint") as (pane, _session):
        tokens = tokens_from_palette(qapp.palette(), force_mode="light")
        pane.apply_colors(tokens)
        _type_filter(qapp, pane, "shop")
        layout = _find_item(pane.tree, "verticalLayout")
        shop = _find_item(pane.tree, "shop")
        other = _find_item(pane.tree, "other")
        assert not layout.isHidden()
        assert not shop.isHidden()
        assert other.isHidden()
        muted = QColor(tokens.text_muted)
        assert layout.foreground(0).color().name() == muted.name()


def test_escape_clears_the_filter(qapp: QApplication) -> None:
    with _opened(qapp, _pair(), "filter-esc") as (pane, _session):
        line = _type_filter(qapp, pane, "shop")
        QTest.keyClick(line, _key("Key_Escape"))
        qapp.processEvents()
        assert _focus(qapp) is pane.tree
        assert not line.isVisible()
        assert line.text() == ""
        assert not _find_item(pane.tree, "other").isHidden()


def test_enter_selects_the_first_filter_match(qapp: QApplication) -> None:
    with _opened(qapp, _pair(), "filter-enter") as (pane, session):
        line = _type_filter(qapp, pane, "shop")
        QTest.keyClick(line, _key("Key_Return"))
        qapp.processEvents()
        assert session.selection.state.current == _id(session, "shop")
        assert pane.tree.currentItem() is _find_item(pane.tree, "shop")


def _click_row(pane: OutlinePane, qapp: QApplication, name: str) -> None:
    rect = pane.tree.visualItemRect(_find_item(pane.tree, name))
    left = getattr(getattr(Qt, "MouseButton", Qt), "LeftButton")
    QTest.mouseClick(pane.tree.viewport(), left, _mod("NoModifier"), rect.center())
    qapp.processEvents()


@pytest.mark.parametrize(("typed", "kept"), [("keptName", "keptName"), ("1bad", "field0")])
def test_clicking_another_row_ends_the_rename(qapp: QApplication, typed: str, kept: str) -> None:
    """A valid name is kept and an invalid one dropped; the outline keys work afterwards."""
    with _opened(qapp, _buttons(3), "rename-abandon") as (pane, session):
        _show(pane, session, "field0")
        QTest.keyClick(pane.tree, _key("Key_F2"))
        editor = _editor(qapp)
        QTest.keyClicks(editor, typed)
        _click_row(pane, qapp, "field2")
        assert not editor.isVisible()
        assert session.document.by_name(kept)
        assert pane.tree.currentItem() is _find_item(pane.tree, "field2")
        assert _focus(qapp) is pane.tree
        QTest.keyClick(pane.tree, _key("Key_Delete"))
        qapp.processEvents()
        assert not session.document.by_name("field2")
        QTest.keyClick(pane.tree, _key("Key_F"), _mod("ControlModifier"))
        assert _focus(qapp).objectName() == "formBuilder.outlineFilter"


def test_removing_the_row_being_renamed_closes_the_editor(qapp: QApplication) -> None:
    with _opened(qapp, _buttons(2), "rename-gone") as (pane, session):
        _show(pane, session, "field0")
        QTest.keyClick(pane.tree, _key("Key_F2"))
        editor = _editor(qapp)
        session.log.execute(DeleteNodes((session.document.by_name("field0")[0],)))
        pane.note_edited()
        qapp.processEvents()
        assert not editor.isVisible()
        _show(pane, session, "field1")
        QTest.keyClick(pane.tree, _key("Key_Delete"))
        qapp.processEvents()
        assert not session.document.by_name("field1")


def test_delete_toasts_an_unreferenced_widget(qapp: QApplication) -> None:
    with _opened(qapp, _pair(), "delete-free") as (pane, session):
        _show(pane, session, "other")
        QTest.keyClick(pane.tree, _key("Key_Delete"))
        qapp.processEvents()
        assert _focus(qapp) is pane.tree
        confirm = pane.findChild(QFrame, "formBuilder.outlineConfirm")
        assert isinstance(confirm, QFrame)
        assert not confirm.isVisible()
        toast = pane.findChild(QLabel, "formBuilder.toastText")
        assert isinstance(toast, QLabel)
        assert toast.text() == "Deleted other \u00b7 Undo"
        assert not session.document.by_name("other")


def test_backspace_deletes_an_unreferenced_widget(qapp: QApplication) -> None:
    with _opened(qapp, _pair(), "delete-back") as (pane, session):
        _show(pane, session, "other")
        QTest.keyClick(pane.tree, _key("Key_Backspace"))
        qapp.processEvents()
        assert _focus(qapp) is pane.tree
        assert not session.document.by_name("other")


def test_a_tab_stop_deletes_without_asking(qapp: QApplication) -> None:
    with _opened(qapp, _email(), "delete-stop") as (pane, session):
        _show(pane, session, "spare")
        QTest.keyClick(pane.tree, _key("Key_Delete"))
        qapp.processEvents()
        confirm = pane.findChild(QFrame, "formBuilder.outlineConfirm")
        assert isinstance(confirm, QFrame)
        assert not confirm.isVisible()
        toast = pane.findChild(QLabel, "formBuilder.toastText")
        assert isinstance(toast, QLabel)
        assert toast.text() == "Deleted spare \u00b7 Undo"
        assert not session.document.by_name("spare")
        assert _focus(qapp) is pane.tree


def test_delete_asks_when_a_buddy_uses_the_name(qapp: QApplication) -> None:
    with _opened(qapp, _email(), "delete-ask") as (pane, session):
        _show(pane, session, "email")
        QTest.keyClick(pane.tree, _key("Key_Delete"))
        qapp.processEvents()
        confirm = pane.findChild(QFrame, "formBuilder.outlineConfirm")
        label = pane.findChild(QLabel, "formBuilder.outlineDeleteText")
        delete = pane.findChild(QPushButton, "formBuilder.outlineDelete")
        cancel = pane.findChild(QPushButton, "formBuilder.outlineCancel")
        assert isinstance(confirm, QFrame) and confirm.isVisible()
        assert isinstance(label, QLabel)
        assert isinstance(delete, QPushButton) and delete.text() == "Delete"
        assert isinstance(cancel, QPushButton) and cancel.text() == "Cancel"
        assert label.text() == session.refs.ask_sentence(session.document, "email", ())
        focus = _focus(qapp)
        assert focus is pane or pane.isAncestorOf(focus)
        assert session.document.by_name("email")


def test_confirming_delete_removes_the_widget(qapp: QApplication) -> None:
    with _opened(qapp, _email(), "delete-yes") as (pane, session):
        _show(pane, session, "email")
        QTest.keyClick(pane.tree, _key("Key_Delete"))
        qapp.processEvents()
        delete = pane.findChild(QPushButton, "formBuilder.outlineDelete")
        assert isinstance(delete, QPushButton)
        delete.click()
        qapp.processEvents()
        assert not session.document.by_name("email")
        assert _focus(qapp) is pane.tree


def test_cancel_keeps_a_referenced_widget(qapp: QApplication) -> None:
    with _opened(qapp, _email(), "delete-cancel") as (pane, session):
        _show(pane, session, "email")
        QTest.keyClick(pane.tree, _key("Key_Delete"))
        qapp.processEvents()
        cancel = pane.findChild(QPushButton, "formBuilder.outlineCancel")
        assert isinstance(cancel, QPushButton)
        cancel.click()
        qapp.processEvents()
        assert session.document.by_name("email")
        assert _focus(qapp) is pane.tree
        confirm = pane.findChild(QFrame, "formBuilder.outlineConfirm")
        assert isinstance(confirm, QFrame)
        assert not confirm.isVisible()


def test_copy_does_not_change_the_form(qapp: QApplication) -> None:
    with _opened(qapp, _pair(), "copy") as (pane, session):
        _show(pane, session, "shop")
        before = session.text()
        QTest.keyClick(pane.tree, _key("Key_C"), _mod("ControlModifier"))
        qapp.processEvents()
        assert session.text() == before
        assert _focus(qapp) is pane.tree


def test_slash_opens_the_insert_list(qapp: QApplication) -> None:
    with _opened(qapp, _pair(), "slash") as (pane, _session):
        _show(pane, _session, "shop")
        QTest.keyClick(pane.tree, _key("Key_Slash"))
        qapp.processEvents()
        pop = pane.findChild(QFrame, "formBuilder.outlineInsert")
        listed = pane.findChild(QListWidget, "formBuilder.outlineInsertList")
        assert isinstance(pop, QFrame) and pop.isVisible()
        assert isinstance(listed, QListWidget)
        assert listed.count() > 0
        assert _focus(qapp) is listed


def test_activating_the_insert_row_places_the_widget(qapp: QApplication) -> None:
    holder: Dict[str, object] = {}

    def place(key: str) -> None:
        session = holder["session"]
        assert isinstance(session, FormSession)
        before = _class_count(session, key)
        commands = auto_commands(
            session.document,
            session.selection.state.current,
            DropPayload("widget"),
            fragment_for(key),
        )
        assert commands
        with session.log.transaction("Drop") as txn:
            for command in commands:
                txn.execute(command)
        holder["grew"] = _class_count(session, key) > before

    with _opened(qapp, _pair(), "insert-place", place=place) as (pane, session):
        holder["session"] = session
        _show(pane, session, "shop")
        QTest.keyClick(pane.tree, _key("Key_Slash"))
        qapp.processEvents()
        listed = pane.findChild(QListWidget, "formBuilder.outlineInsertList")
        assert isinstance(listed, QListWidget)
        QTest.keyClick(listed, _key("Key_Return"))
        qapp.processEvents()
        assert holder.get("grew") is True
        assert _focus(qapp) is pane.tree


def _class_count(session: FormSession, class_name: str) -> int:
    total = 0
    for node in session.document.iter_preorder():
        if isinstance(node, WidgetNode) and node.class_name == class_name:
            total += 1
    return total


def test_row_boxes_stay_disjoint_at_236(qapp: QApplication) -> None:
    with _opened(qapp, _long_name(), "elide", width=236, height=360) as (pane, session):
        pane.setFixedWidth(236)
        qapp.processEvents()
        name = "N" * 48
        item = _find_item(pane.tree, name)
        pane.tree.scrollToItem(item)
        qapp.processEvents()
        rect = pane.tree.visualItemRect(item)
        assert rect.width() > 0
        caption = "\u201c" in item.toolTip(0)
        boxes = layout_row(rect.width(), caption, False)
        shown = [boxes.glyph, boxes.name]
        if boxes.caption is not None:
            shown.append(boxes.caption)
        if boxes.problem is not None:
            shown.append(boxes.problem)
        for index, left in enumerate(shown):
            for right in shown[index + 1 :]:
                assert not _overlaps(left, right)
        advance = pane.tree.fontMetrics().horizontalAdvance(item.text(0))
        assert advance > boxes.name[2]
        mode = pane.tree.textElideMode()
        elide = getattr(getattr(Qt, "TextElideMode", Qt), "ElideRight")
        assert enum_value(mode) == enum_value(elide)
        assert pane.tree.indentation() == 12
        assert session.document.by_name(name)


def _deep_label() -> str:
    return form(
        'class="QWidget" name="Form"',
        """
  <layout class="QVBoxLayout" name="l0">
   <item>
    <widget class="QGroupBox" name="g1">
     <layout class="QVBoxLayout" name="l1">
      <item>
       <widget class="QLabel" name="streetLabel">
        <property name="text"><string>Street</string></property>
       </widget>
      </item>
     </layout>
    </widget>
   </item>
  </layout>
""",
    )


def test_a_depth_4_name_keeps_its_prefix_at_the_default_width(qapp: QApplication) -> None:
    with _opened(qapp, _deep_label(), "deep", width=232, height=360) as (pane, _session):
        pane.setFixedWidth(232)
        qapp.processEvents()
        item = _find_item(pane.tree, "streetLabel")
        depth = 0
        walker: Optional[QTreeWidgetItem] = item
        while walker is not None and walker.parent() is not None:
            depth += 1
            walker = walker.parent()
        assert depth >= 4
        pane.tree.scrollToItem(item)
        qapp.processEvents()
        rect = pane.tree.visualItemRect(item)
        metrics = pane.tree.fontMetrics()
        name_px = metrics.horizontalAdvance("streetLabel")
        boxes = layout_row(rect.width(), False, False, 0, name_px)
        elide = getattr(getattr(Qt, "TextElideMode", Qt), "ElideRight")
        shown = metrics.elidedText("streetLabel", elide, boxes.name[2])
        assert shown.startswith("streetLa") or shown == "streetLabel"
        assert "streetLabel" in item.toolTip(0)
        assert pane.tree.indentation() == 12


def test_shift_click_extends_the_outline_selection(qapp: QApplication) -> None:
    with _opened(qapp, _buttons(3), "shift") as (pane, session):
        _click_row(pane, qapp, "field0")
        rect = pane.tree.visualItemRect(_find_item(pane.tree, "field2"))
        left = getattr(getattr(Qt, "MouseButton", Qt), "LeftButton")
        QTest.mouseClick(pane.tree.viewport(), left, _mod("ShiftModifier"), rect.center())
        qapp.processEvents()
        chosen = {int(node) for node in session.selection.state.ids}
        assert chosen == {int(_id(session, "field0")), int(_id(session, "field1")), int(_id(session, "field2"))}


def test_ctrl_click_toggles_an_outline_row(qapp: QApplication) -> None:
    with _opened(qapp, _buttons(3), "ctrl") as (pane, session):
        _click_row(pane, qapp, "field0")
        rect = pane.tree.visualItemRect(_find_item(pane.tree, "field2"))
        left = getattr(getattr(Qt, "MouseButton", Qt), "LeftButton")
        QTest.mouseClick(pane.tree.viewport(), left, _mod("ControlModifier"), rect.center())
        qapp.processEvents()
        chosen = {int(node) for node in session.selection.state.ids}
        assert chosen == {int(_id(session, "field0")), int(_id(session, "field2"))}


def _tree_ids(tree: QTreeWidget) -> Tuple[int, ...]:
    role = int(getattr(Qt, "UserRole"))
    found: list = []

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


def _project_ids(session: FormSession) -> Tuple[int, ...]:
    forest = project(session.document, frozenset(), lambda name: name)
    return tuple(int(row.node) for row in forest.rows)


def _matches(pane: OutlinePane, session: FormSession) -> None:
    assert _tree_ids(pane.tree) == _project_ids(session)


_BARE = form(
    'class="QWidget" name="Form"',
    """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QGroupBox" name="receiptGroup">
    <property name="title"><string>Receipt</string></property>
   </widget></item>
   <item><widget class="QCheckBox" name="printCopy">
    <property name="text"><string>Print copy</string></property>
   </widget></item>
   <item><widget class="QTabWidget" name="tabs">
    <property name="currentIndex"><number>0</number></property>
    <widget class="QWidget" name="pageA"/>
   </widget></item>
   <item><layout class="QGridLayout" name="grid">
    <item row="0" column="0"><widget class="QLabel" name="cellA"><property name="text"><string>A</string></property></widget></item>
    <item row="0" column="1"><widget class="QLabel" name="cellB"><property name="text"><string>B</string></property></widget></item>
    <item row="1" column="0"><widget class="QLabel" name="cellC"><property name="text"><string>C</string></property></widget></item>
   </layout></item>
  </layout>
""",
)


def test_undo_of_a_nest_keeps_every_outline_row(qapp: QApplication) -> None:
    with _opened(qapp, _BARE, "undo-nest") as (pane, session):
        print_copy = _items(pane.tree)[int(_id(session, "printCopy"))]
        _show(pane, session, "printCopy")
        QTest.keyClick(pane.tree, _key("Key_Tab"))
        qapp.processEvents()
        assert session.log.entries()[-1].label == "Nest"
        _matches(pane, session)
        session.log.undo()
        pane.note_edited()
        qapp.processEvents()
        _matches(pane, session)
        assert _items(pane.tree)[int(_id(session, "printCopy"))] is print_copy


def test_undo_of_a_cell_move_restores_reading_order(qapp: QApplication) -> None:
    with _opened(qapp, _BARE, "undo-cell") as (pane, session):
        _show(pane, session, "cellB")
        QTest.keyClick(pane.tree, _key("Key_Down"), _mod("AltModifier"))
        qapp.processEvents()
        _matches(pane, session)
        session.log.undo()
        pane.note_edited()
        qapp.processEvents()
        _matches(pane, session)
        names = [_find_item(pane.tree, name).text(0) for name in ("cellA", "cellB", "cellC")]
        assert names == ["cellA", "cellB", "cellC"]
        order = _tree_ids(pane.tree)
        assert order.index(int(_id(session, "cellA"))) < order.index(int(_id(session, "cellB")))
        assert order.index(int(_id(session, "cellB"))) < order.index(int(_id(session, "cellC")))


def test_a_refused_alt_move_stays_on_the_row(qapp: QApplication) -> None:
    notes: list = []
    with _opened(qapp, _BARE, "alt-refuse") as (pane, session):
        pane.set_status(notes.append)
        _show(pane, session, "pageA")
        before = pane.tree.currentItem()
        QTest.keyClick(pane.tree, _key("Key_Up"), _mod("AltModifier"))
        qapp.processEvents()
        assert pane.tree.currentItem() is before
        assert notes[-1] == "pageA is already the first page."
        _show(pane, session, "cellA")
        current = pane.tree.currentItem()
        QTest.keyClick(pane.tree, _key("Key_Down"), _mod("AltModifier"))
        qapp.processEvents()
        assert pane.tree.currentItem() is current
        assert "can't move" in notes[-1]


def test_the_delete_confirm_fits_and_answers_from_the_keyboard(qapp: QApplication) -> None:
    with _opened(qapp, _email(), "confirm", width=236, height=480) as (pane, session):
        pane.setFixedWidth(236)
        qapp.processEvents()
        _show(pane, session, "email")
        QTest.keyClick(pane.tree, _key("Key_Delete"))
        qapp.processEvents()
        confirm = pane.findChild(QFrame, "formBuilder.outlineConfirm")
        delete = pane.findChild(QPushButton, "formBuilder.outlineDelete")
        assert isinstance(confirm, QFrame) and isinstance(delete, QPushButton)
        assert confirm.isVisible()
        assert confirm.width() <= 236
        assert confirm.geometry().right() <= pane.width()
        assert confirm.geometry().bottom() <= pane.height()
        QTest.keyClick(delete, _key("Key_Escape"))
        qapp.processEvents()
        assert not confirm.isVisible()
        assert _focus(qapp) is pane.tree
        QTest.keyClick(pane.tree, _key("Key_Delete"))
        qapp.processEvents()
        QTest.keyClick(delete, _key("Key_Return"))
        qapp.processEvents()
        assert not confirm.isVisible()
        assert not session.document.by_name("email")


def test_the_outline_claims_f2_and_find(qapp: QApplication) -> None:
    with _opened(qapp, _pair(), "claim") as (pane, session):
        _show(pane, session, "shop")
        kind = getattr(QEvent, "ShortcutOverride", None)
        if kind is None:
            kind = getattr(QEvent.Type, "ShortcutOverride")
        event = QKeyEvent(kind, cast(int, _key("Key_F2")), cast(int, _mod("NoModifier")))
        assert pane.eventFilter(pane.tree, event)
        assert event.isAccepted()
        find = QKeyEvent(kind, cast(int, _key("Key_F")), cast(int, _mod("ControlModifier")))
        assert pane.eventFilter(pane.tree, find)
        assert find.isAccepted()


def _receipt() -> str:
    return form(
        'class="QWidget" name="Form"',
        """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QGroupBox" name="receiptGroup">
    <property name="title"><string>Receipt</string></property>
   </widget></item>
   <item><widget class="QPushButton" name="ok"><property name="text"><string>Go</string></property></widget></item>
   <item><widget class="QLabel" name="emailLabel"><property name="text"><string>Email:</string></property></widget></item>
   <item><widget class="QPushButton" name="%s"><property name="text"><string>Hi</string></property></widget></item>
  </layout>
"""
        % ("N" * 48),
    )


class _Recorder(QPainter):
    """Keeps every text the delegate paints with the box it was given."""

    def __init__(self, device: QImage) -> None:
        super().__init__(device)
        self.drawn: list = []

    def drawText(self, *args: object) -> None:  # noqa: N802
        if len(args) == 3 and isinstance(args[0], QRect):
            self.drawn.append((QRect(args[0]), str(args[2])))
        super().drawText(*args)  # type: ignore[call-overload]


def _painted(pane: OutlinePane, item: QTreeWidgetItem) -> list:
    tree = pane.tree
    tree.setCurrentItem(item)
    index = tree.currentIndex()
    option = QStyleOptionViewItem()
    option.rect = tree.visualItemRect(item)
    option.font = tree.font()
    option.fontMetrics = tree.fontMetrics()
    option.palette = tree.palette()
    option.widget = tree
    image = QImage(tree.viewport().size(), QImage.Format.Format_ARGB32)
    painter = _Recorder(image)
    try:
        tree.itemDelegate().paint(painter, option, index)
    finally:
        painter.end()
    # The glyph is one character. Keep the name and the caption.
    return [(rect, text) for rect, text in painter.drawn if len(text) > 1]


@pytest.mark.parametrize("width", [236, 198])
def test_a_narrow_outline_drops_the_caption_before_the_name(qapp: QApplication, width: int) -> None:
    with _opened(qapp, _receipt(), "caption-%d" % width, width=width, height=360) as (pane, _session):
        pane.setFixedWidth(width)
        qapp.processEvents()
        metrics = pane.tree.fontMetrics()
        for name in ("Form", "verticalLayout", "receiptGroup", "ok", "emailLabel", "N" * 48):
            item = _find_item(pane.tree, name)
            caption = str(item.data(0, int(getattr(Qt, "UserRole")) + 1) or "")
            assert caption
            drawn = _painted(pane, item)
            for rect, text in drawn:
                assert metrics.horizontalAdvance(text) <= rect.width(), (width, name, text)
            texts = [text for _rect, text in drawn]
            rect = pane.tree.visualItemRect(item)
            room = min(rect.width(), pane.tree.viewport().width() - max(rect.x(), 0)) - 20
            if metrics.horizontalAdvance(name) <= room:
                assert texts[0] == name, (width, texts)
            else:
                assert texts[0] != name and "\u2026" in texts[0], (width, texts)
                assert caption not in texts
            if caption in texts:
                assert texts[0] == name
        # The reviewer's case: the name fits on its own, the caption does not.
        group = [text for _rect, text in _painted(pane, _find_item(pane.tree, "receiptGroup"))]
        assert group[0] == "receiptGroup"
        assert pane.tree.horizontalScrollBar().isVisible() is False


def _overlaps(left: Tuple[int, int, int, int], right: Tuple[int, int, int, int]) -> bool:
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    if lw <= 0 or lh <= 0 or rw <= 0 or rh <= 0:
        return False
    return lx < rx + rw and rx < lx + lw and ly < ry + rh and ry < ly + lh


def _shape(tree: QTreeWidget) -> Tuple[Tuple[int, int, str], ...]:
    """Pre-order (id, parent id, text) of the tree items."""
    role = int(getattr(Qt, "UserRole"))
    found: list = []

    def walk(item: QTreeWidgetItem, parent: int) -> None:
        node = int(item.data(0, role))
        found.append((node, parent, item.text(0)))
        for index in range(item.childCount()):
            walk(item.child(index), node)

    for index in range(tree.topLevelItemCount()):
        walk(tree.topLevelItem(index), -1)
    return tuple(found)


def _project_shape(session: FormSession) -> Tuple[Tuple[int, int, str], ...]:
    forest = project(session.document, frozenset(), lambda name: name)
    return tuple((int(row.node), -1 if row.parent is None else int(row.parent), row.primary) for row in forest.rows)


@pytest.mark.parametrize("seed", range(6))
def test_random_edits_undo_and_redo_keep_the_outline_equal_to_the_form(qapp: QApplication, seed: int) -> None:
    """Structural edits patch rows in place: shape, collapsed rows and the current row survive."""
    import random

    from app.features.form_builder.engine.commands.base import CommandRejected
    from tests.support.form_builder.gen import FORMS, command_for

    rng = random.Random(seed)
    with _opened(qapp, FORMS[seed % len(FORMS)], "random-%d" % seed, height=640) as (pane, session):
        log = session.log
        for step in range(30):
            items = _items(pane.tree)
            parents = [node for node, item in items.items() if item.childCount()]
            if parents and rng.randrange(2) == 0:
                items[rng.choice(parents)].setExpanded(False)
            opened = {node: item.isExpanded() for node, item in items.items() if item.childCount()}
            roll = rng.randrange(8)
            if roll == 0:
                log.undo()
            elif roll == 1:
                log.redo()
            else:
                command = command_for(session.document, rng, seed * 1000 + step)
                if command is None or type(command).__name__ == "ReplaceDocument":
                    continue
                try:
                    log.execute(command)
                except CommandRejected:
                    continue
            pane.note_edited()
            qapp.processEvents()
            assert _shape(pane.tree) == _project_shape(session), "seed %d step %d" % (seed, step)
            items = _items(pane.tree)
            current = session.selection.state.current
            revealed = set()
            if current is not None and int(current) in items:
                assert pane.tree.currentItem() is items[int(current)]
                parent = items[int(current)].parent()
                while parent is not None:
                    revealed.add(int(parent.data(0, int(getattr(Qt, "UserRole")))))
                    parent = parent.parent()
            for node, was in opened.items():
                item = items.get(node)
                if item is None or not item.childCount() or node in revealed:
                    continue
                assert item.isExpanded() == was, "seed %d step %d node %d" % (seed, step, node)
