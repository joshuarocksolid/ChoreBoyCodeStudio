# pyright: reportAttributeAccessIssue=false
"""K10 Pages (UX_SPEC 12.3).

The surface test opens the Pages menu with Shift+F10 and chooses the rows
by keys. The command test still checks that undo returns the original bytes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.commands.catalog_ext.pages import DeletePage, InsertPage
from app.features.form_builder.engine.query.pages import page_widget_count, pages
from app.features.form_builder.engine.ui4.values import NumberValue
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.integration.canvas import FormCanvas
from app.qt.QtCore import QPoint, Qt
from app.qt.qt_compat import delete_now, wrapper_is_valid
from app.qt.QtTest import QTest
from app.qt.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QLineEdit,
    QMenu,
    QTabWidget,
    QTreeWidget,
    QWidget,
)
from tests.form_builder.engine.commands._support import open_log, saved
from tests.form_builder.qtside.support import opened
from tests.form_builder.qtside.test_m4_pages_canvas import TABS, _Host, _click, _press_key, _shown_index
from tests.unit.features.form_builder.test_workbench import _open

pytestmark = pytest.mark.usefixtures("qapp")


def test_k10_ctrl_page_up_then_start_on_this_page_then_delete_and_undo() -> None:
    host = _Host()
    log = open_log(TABS)
    doc = log.document
    tabs = doc.by_name("tabs")[0]
    original = saved(doc)
    log.execute(InsertPage(tabs))  # the "Insert page after" of the last page (UX-CONT-003)
    assert len(pages(doc, tabs)) == 3
    with opened(saved(doc)) as (session, realizer):
        parent = QWidget()
        parent.resize(640, 480)
        canvas = FormCanvas(session, realizer, host, parent)
        canvas.resize(640, 480)
        parent.show()
        canvas.setFocus()
        _click(canvas, "inside_a")
        before = saved(session.document)
        dirty = session.log.is_dirty()
        _press_key(canvas, "Key_PageUp", "ControlModifier")
        assert _shown_index(canvas, "tabs") == 2
        assert host.sentences[-1].startswith("Showing page 3 of 3")
        assert "the file still starts on page 1" in host.sentences[-1]
        assert saved(session.document) == before and session.log.is_dirty() == dirty
        canvas.dispose()
        parent.deleteLater()
    log.execute(SetProperty(tabs, "currentIndex", NumberValue(2)))  # "Start on this page"
    assert 'name="currentIndex"' in saved(doc)
    assert page_widget_count(doc, pages(doc, tabs)[1].id) == 1  # the Beta page holds inside_b: the confirm would ask
    log.execute(DeletePage(tabs, 1))
    assert [page.object_name for page in pages(doc, tabs)] == ["tab_a", "tab_3"]
    assert 'name="currentIndex"' in saved(doc) and "<number>1</number>" in saved(doc)  # still on the new page
    for _ in range(5):
        if log.can_undo():
            assert log.undo()
    assert saved(doc) == original


def _flush(times: int = 6) -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(times):
        app.processEvents()


def _surface(tmp_path: Path, name: str) -> tuple:
    parent = QWidget()
    parent.resize(1100, 760)
    surface = _open(parent, TABS, tmp_path / ("%s.ui" % name))
    surface.resize(1100, 760)
    parent.show()
    surface.show()
    _flush()
    return parent, surface


def _close(parent: QWidget, surface: QWidget) -> None:
    for menu in surface.findChildren(QMenu):
        menu.close()
    surface.release()  # type: ignore[attr-defined]
    parent.deleteLater()
    _flush()


def _canvas(surface: QWidget) -> QWidget:
    canvas = surface.findChild(QWidget, "formBuilder.canvas")
    assert canvas is not None
    return canvas


def _port(canvas: QWidget, widget: QWidget) -> QPoint:
    root = canvas.page_widget()  # type: ignore[attr-defined]
    assert root is not None
    point = widget.mapTo(root, widget.rect().center())
    return canvas.mapFromScene(root.graphicsProxyWidget().mapToScene(point))


def _click_widget(canvas: QWidget, widget: QWidget) -> None:
    QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, _port(canvas, widget))
    _flush()


def _release_popup(widget: QWidget) -> None:
    """Close a popup, then reactivate the window.

    Offscreen Qt drops the active window when a popup closes, so shortcuts
    and focus reads go quiet until the window is activated again.
    """
    host = widget
    while isinstance(host, QMenu) and host.parentWidget() is not None:
        host = host.parentWidget()
    window = None if isinstance(host, QMenu) else host.window()
    for _ in range(6):
        focus = QApplication.focusWidget()
        popup = QApplication.activePopupWidget()
        if not isinstance(focus, QMenu) and popup is None:
            break
        target = focus if isinstance(focus, QMenu) else popup
        if isinstance(target, QWidget):
            target.hide()
            target.close()
            if isinstance(target, QMenu) and wrapper_is_valid(target):
                delete_now(target)
        _flush(2)
    if (
        window is not None
        and QApplication.activeWindow() is None
        and QApplication.activePopupWidget() is None
    ):
        window.activateWindow()
        _flush(2)


def _open_menu(canvas: QWidget, surface: QWidget) -> QMenu:
    _release_popup(canvas)
    window = canvas.window()
    window.activateWindow()
    canvas.setFocus(Qt.FocusReason.OtherFocusReason)
    _flush()
    if not canvas.hasFocus():
        QTest.mouseClick(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            canvas.viewport().rect().center(),
        )
        _flush()
    QTest.keyClick(canvas, Qt.Key.Key_F10, Qt.KeyboardModifier.ShiftModifier)
    _flush()
    visible = [
        menu
        for menu in surface.findChildren(QMenu)
        if menu.objectName() == "formBuilder.contextMenu" and menu.isVisible()
    ]
    focus = QApplication.focusWidget()
    assert visible, "Shift+F10 did not open the context menu (focus %s, canvas focus %s)" % (
        type(focus).__name__ if focus is not None else None,
        canvas.hasFocus(),
    )
    return visible[-1]


def _step(menu: QMenu, prefix: str) -> object:
    menu.setFocus()
    _flush(2)
    for _ in range(24):
        active = menu.activeAction()
        if active is not None and active.text().startswith(prefix):
            return active
        QTest.keyClick(menu, Qt.Key.Key_Down)
        _flush(2)
    labels = [action.text() for action in menu.actions()]
    raise AssertionError("no %r in %r" % (prefix, labels))


def _pick(menu: QMenu, prefix: str) -> None:
    _step(menu, prefix)
    QTest.keyClick(menu, Qt.Key.Key_Return)
    _flush()
    # Offscreen Qt leaves the popup focused after the key activates a row.
    # Close the chain so the next key goes to the editor or the canvas.
    current: QWidget = menu
    chain = []
    while isinstance(current, QMenu):
        chain.append(current)
        parent = current.parentWidget()
        if parent is None:
            break
        current = parent
    for item in chain:
        item.hide()
        item.close()
    _release_popup(menu)


def _pages(menu: QMenu) -> QMenu:
    action = _step(menu, "Pages")
    QTest.keyClick(menu, Qt.Key.Key_Right)
    _flush()
    sub = action.menu()
    assert sub is not None and sub.isVisible(), "Pages did not open"
    return sub


def _go_to_row(tree: QTreeWidget, text: str) -> None:
    for key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
        for _ in range(16):
            item = tree.currentItem()
            caption = "" if item is None else str(item.data(0, int(Qt.ItemDataRole.UserRole) + 1) or "")
            if item is not None and (item.text(0) == text or caption == text):
                return
            QTest.keyClick(tree, key)
            _flush(2)
    labels = []
    for index in range(tree.topLevelItemCount()):
        labels.extend(_row_texts(tree.topLevelItem(index)))
    raise AssertionError("%r not in %r" % (text, labels))


def _row_texts(item: object) -> list:
    found = [item.text(0)]  # type: ignore[attr-defined]
    for index in range(item.childCount()):  # type: ignore[attr-defined]
        found.extend(_row_texts(item.child(index)))  # type: ignore[attr-defined]
    return found


def _start_index(document: object, name: str) -> int:
    node = document.get(document.by_name(name)[0])  # type: ignore[attr-defined]
    prop = node.prop("currentIndex")
    assert prop is not None and isinstance(prop.value, NumberValue)
    return prop.value.value


def _tabs(surface: QWidget) -> QTabWidget:
    root = _canvas(surface).page_widget()  # type: ignore[attr-defined]
    found = root.findChild(QTabWidget, "tabs")
    assert isinstance(found, QTabWidget)
    return found


@pytest.mark.timeout(90)
def test_k10_shift_f10_pages_menu_then_keys(tmp_path: Path) -> None:
    parent, surface = _surface(tmp_path, "k10")
    try:
        canvas = _canvas(surface)
        root = canvas.page_widget()  # type: ignore[attr-defined]
        label = root.findChild(QLabel, "inside_b")
        assert label is not None
        _click_widget(canvas, label)
        before = write_ui(surface.session.document).text  # type: ignore[attr-defined]
        QTest.keyClick(canvas, Qt.Key.Key_PageDown, Qt.KeyboardModifier.ControlModifier)
        _flush()
        assert _tabs(surface).currentIndex() == 1

        pages_menu = _pages(_open_menu(canvas, surface))
        _pick(pages_menu, "Insert tab after")
        _flush(12)
        edits = [widget for widget in canvas.findChildren(QLineEdit) if widget.isVisible()]
        assert edits, "the title editor did not open"
        editor = edits[-1]
        editor.setFocus()
        QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClicks(editor, "Printing")
        QTest.keyClick(editor, Qt.Key.Key_Return)
        _flush()
        tabs = _tabs(surface)
        titles = [tabs.tabText(index) for index in range(tabs.count())]
        assert tabs.count() == 3 and tabs.currentIndex() == 2 and tabs.tabText(2) == "Printing", (
            titles,
            tabs.currentIndex(),
        )
        titled = write_ui(surface.session.document).text  # type: ignore[attr-defined]

        QTest.keyClick(canvas, Qt.Key.Key_PageUp, Qt.KeyboardModifier.ControlModifier)
        _flush()
        assert _tabs(surface).currentIndex() == 1
        status = surface.editor_status_sentence()  # type: ignore[attr-defined]
        assert "starts on page 1" in status, status
        assert write_ui(surface.session.document).text == titled  # type: ignore[attr-defined]
        assert _start_index(surface.session.document, "tabs") == 0  # type: ignore[attr-defined]

        pages_menu = _pages(_open_menu(canvas, surface))
        _pick(pages_menu, "Start on this page")
        _flush()
        assert _start_index(surface.session.document, "tabs") == 1  # type: ignore[attr-defined]

        _click_widget(canvas, root.findChild(QLabel, "inside_b"))
        _release_popup(canvas)
        focus = QApplication.focusWidget() or canvas
        QTest.keyClick(focus, Qt.Key.Key_1, Qt.KeyboardModifier.AltModifier)
        _flush()
        tree = surface.findChild(QTreeWidget, "formBuilder.structure")
        assert tree is not None and (tree.hasFocus() or surface.focusWidget() is tree)
        # The outline caption still shows the object name (M4.1). tab_3 is the Printing page.
        _go_to_row(tree, "tab_3")
        QTest.keyClick(tree, Qt.Key.Key_Up, Qt.KeyboardModifier.AltModifier)
        _flush()
        assert _tabs(surface).tabText(1) == "Printing"

        _go_to_row(tree, "tab_a")
        QTest.keyClick(tree, Qt.Key.Key_Delete)
        _flush()
        confirm = surface.findChild(QFrame, "formBuilder.outlineConfirm")
        assert confirm is not None and confirm.isVisible()
        assert "widget" in confirm.findChild(QLabel).text()  # type: ignore[union-attr]
        QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Escape)
        _flush()
        assert _tabs(surface).count() == 3
        QTest.keyClick(tree, Qt.Key.Key_Delete)
        _flush()
        QTest.keyClick(surface.findChild(QWidget, "formBuilder.outlineDelete"), Qt.Key.Key_Return)
        _flush()
        assert _tabs(surface).count() == 2
        assert any("Deleted page" in label.text() for label in surface.findChildren(QLabel))
        focus = QApplication.focusWidget()
        outline = surface.findChild(QWidget, "formBuilder.outline")
        assert outline is not None and (focus is outline or outline.isAncestorOf(focus) or focus is tree)

        for _ in range(5):
            assert surface.undo()  # type: ignore[attr-defined]
        assert write_ui(surface.session.document).text == before  # type: ignore[attr-defined]
    finally:
        _close(parent, surface)


def test_delete_from_the_canvas_menu_anchors_the_confirm_on_the_tab(tmp_path: Path) -> None:
    parent, surface = _surface(tmp_path, "anchor")
    try:
        canvas = _canvas(surface)
        root = canvas.page_widget()  # type: ignore[attr-defined]
        label = root.findChild(QLabel, "inside_a")
        assert label is not None
        _click_widget(canvas, label)
        page_id = pages(surface.session.document, surface.session.document.by_name("tabs")[0])[0].id  # type: ignore[attr-defined]
        local = canvas.tab_viewport_rect(page_id)  # type: ignore[attr-defined]
        assert local is not None
        tab_at = canvas.viewport().mapToGlobal(local.topLeft())
        tree = surface.findChild(QTreeWidget, "formBuilder.structure")
        assert tree is not None and tree.currentItem() is not None
        row_at = tree.viewport().mapToGlobal(tree.visualItemRect(tree.currentItem()).topLeft())
        _pick(_pages(_open_menu(canvas, surface)), "Delete page")
        _flush()
        confirm = surface.findChild(QFrame, "formBuilder.outlineConfirm")
        assert confirm is not None and confirm.isVisible()
        placed = confirm.mapToGlobal(QPoint(0, 0))
        assert abs(placed.x() - tab_at.x()) < abs(placed.x() - row_at.x())
        assert abs(placed.y() - (tab_at.y() + local.height())) < 80
    finally:
        _close(parent, surface)
