# pyright: reportAttributeAccessIssue=false
"""Inspector session: canvas overrides, tab order, spins, scroll, and focus."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.query.selection import SelectionSource  # noqa: E402
from app.features.form_builder.engine.ui4.writer import write_ui  # noqa: E402
from app.features.form_builder.install import form_builder_enabled  # noqa: E402
from app.features.form_builder.qtside.inspector.api import GROUP_ORDER, GroupId  # noqa: E402
from app.qt.QtCore import QPoint, Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QToolButton,
    QWidget,
)
from app.qt.qt_compat import enum_value  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Main</class>
 <widget class="QMainWindow" name="Main">
  <property name="geometry">
   <rect><x>0</x><y>0</y><width>480</width><height>320</height></rect>
  </property>
  <widget class="QWidget" name="central">
   <layout class="QVBoxLayout" name="verticalLayout">
    <item>
     <widget class="QLineEdit" name="email">
      <property name="focusPolicy">
       <enum>Qt::StrongFocus</enum>
      </property>
     </widget>
    </item>
    <item>
     <widget class="QPushButton" name="okButton">
      <property name="text"><string>OK</string></property>
     </widget>
    </item>
   </layout>
  </widget>
  <widget class="QMenuBar" name="menuBar">
   <property name="nativeMenuBar">
    <bool>true</bool>
   </property>
   <widget class="QMenu" name="menuFile">
    <property name="title"><string>File</string></property>
   </widget>
   <addaction name="menuFile"/>
  </widget>
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


def _mods(name: str) -> Qt.KeyboardModifier:
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


def _settle(qapp: QApplication) -> None:
    for _ in range(4):
        qapp.processEvents()


def _start(tmp_path: Path, qapp: QApplication) -> tuple:
    _require()
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    surface = _open(window, qapp, tmp_path / "main.ui", _FORM)
    qapp.setActiveWindow(window)
    _settle(qapp)
    return window, surface


def _xml(surface: object) -> str:
    return write_ui(surface.session.document).text  # type: ignore[attr-defined]


def _page(surface: object, name: str) -> QWidget:
    root = surface.page_widget()  # type: ignore[attr-defined]
    assert isinstance(root, QWidget)
    widget = root.findChild(QWidget, name)
    assert widget is not None, name
    return widget


def _nofocus(widget: QWidget) -> bool:
    no_focus = getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus")
    return enum_value(widget.focusPolicy()) == enum_value(no_focus)


def _inspector(surface: object) -> QWidget:
    found = surface.findChild(QWidget, "formBuilder.inspector")  # type: ignore[attr-defined]
    assert isinstance(found, QWidget)
    return found


def _select(surface: object, qapp: QApplication, name: str, *, all_properties: bool = False) -> None:
    inspector = _inspector(surface)
    if all_properties:
        inspector.set_group_expanded(GroupId.ALL, True)  # type: ignore[attr-defined]
    session = surface.session  # type: ignore[attr-defined]
    session.selection.set((session.document.by_name(name)[0],), source=SelectionSource.CANVAS)
    _settle(qapp)


def _click_canvas(surface: object, qapp: QApplication, name: str, modifier: str = "NoModifier") -> None:
    canvas = surface.findChild(QWidget, "formBuilder.canvas")  # type: ignore[attr-defined]
    assert canvas is not None
    root = surface.page_widget()  # type: ignore[attr-defined]
    assert isinstance(root, QWidget)
    widget = root.findChild(QWidget, name)
    assert widget is not None, name
    center = widget.mapTo(root, widget.rect().center())
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    mapped = canvas.mapFromScene(proxy.mapToScene(center))
    port = QPoint(int(mapped.x()), int(mapped.y()))
    QTest.mouseClick(canvas.viewport(), _mouse("LeftButton"), _mods(modifier), port)
    _settle(qapp)


def _row(surface: object, key: str) -> QWidget:
    found = surface.findChild(QWidget, "formBuilder.row.%s" % key)  # type: ignore[attr-defined]
    assert isinstance(found, QWidget), key
    return found


def _combo(surface: object, key: str) -> QComboBox:
    combo = _row(surface, key).findChild(QComboBox)
    assert isinstance(combo, QComboBox), key
    return combo


def _pick(combo: QComboBox, qapp: QApplication, name: str) -> None:
    index = -1
    for row in range(combo.count()):
        if combo.itemText(row) == name or combo.itemData(row) == name:
            index = row
            break
    assert index >= 0, name
    combo.showPopup()
    _settle(qapp)
    view = combo.view()
    model_index = view.model().index(index, 0)
    view.scrollTo(model_index)
    rect = view.visualRect(model_index)
    QTest.mouseClick(view.viewport(), _mouse("LeftButton"), _mods("NoModifier"), rect.center())
    _settle(qapp)


def _reset(surface: object, qapp: QApplication, key: str) -> None:
    row = _row(surface, key)
    editor = row.findChild(QComboBox) or row.findChild(QCheckBox) or row.findChild(QSpinBox)
    assert editor is not None
    editor.setFocus()
    _settle(qapp)
    focus = QApplication.focusWidget()
    inside = isinstance(focus, QWidget) and (focus is row or row.isAncestorOf(focus))
    if not inside:
        _hover_row(row)
        _settle(qapp)
    button = row.findChild(QToolButton, "formBuilder.rowReset")
    assert isinstance(button, QToolButton) and button.isVisible()
    QTest.mouseClick(button, _mouse("LeftButton"))
    _settle(qapp)


def _hover_row(row: QWidget) -> None:
    """The reset shows on hover. setFocus does not land inside the row on macOS."""
    from app.qt.QtCore import QPointF
    from app.qt.QtGui import QEnterEvent

    point = QPointF(row.width() / 2.0, row.height() / 2.0)
    row.enterEvent(QEnterEvent(point, point, point))


def _tool(surface: object, qapp: QApplication, name: str) -> None:
    button = surface.findChild(QWidget, name)  # type: ignore[attr-defined]
    assert isinstance(button, QWidget) and button.isEnabled(), name
    QTest.mouseClick(button, _mouse("LeftButton"))
    _settle(qapp)


def _undo_count(surface: object) -> int:
    return len(surface.session.log.entries())  # type: ignore[attr-defined]


def _spin_line(surface: object, key: str, index: int = 0) -> tuple:
    row = _row(surface, key)
    spins = row.findChildren(QSpinBox)
    assert len(spins) > index, key
    spin = spins[index]
    line = spin.lineEdit()
    assert line is not None
    return spin, line


def _type_number(qapp: QApplication, line: QLineEdit, text: str) -> None:
    line.setFocus()
    line.selectAll()
    _settle(qapp)
    QTest.keyClicks(line, text, delay=0)
    _settle(qapp)


def _inside(ancestor: QWidget, widget: Optional[QWidget]) -> bool:
    return widget is not None and (widget is ancestor or ancestor.isAncestorOf(widget))


def _tab_stops(start: QWidget, inspector: QWidget, qapp: QApplication) -> List[QWidget]:
    sequence: List[QWidget] = []
    seen = set()
    focus: Optional[QWidget] = start
    for _ in range(80):
        assert focus is not None
        QTest.keyClick(focus, _key("Key_Tab"))
        _settle(qapp)
        focus = QApplication.focusWidget()
        if not _inside(inspector, focus) or focus in seen or focus is start:
            break
        assert focus is not None
        seen.add(focus)
        sequence.append(focus)
    return sequence


def _header_names(inspector: QWidget) -> Sequence[str]:
    names = []
    for group in GROUP_ORDER:
        button = inspector.findChild(QWidget, "formBuilder.group.%s" % group.value)
        if button is not None and button.isVisible():
            names.append(button.objectName())
    return names


def _assert_group_tabs(inspector: QWidget, sequence: Sequence[QWidget]) -> None:
    headers = [widget for widget in sequence if widget.objectName().startswith("formBuilder.group.")]
    assert [widget.objectName() for widget in headers] == list(_header_names(inspector))
    names = [widget.objectName() for widget in headers]
    assert "formBuilder.group.content" in names
    assert names.index("formBuilder.group.content") < names.index("formBuilder.group.appearance")
    for index, header in enumerate(headers):
        group = header.parentWidget()
        assert group is not None
        start = sequence.index(header)
        end = sequence.index(headers[index + 1]) if index + 1 < len(headers) else len(sequence)
        body = [widget for widget in sequence[start + 1 : end] if widget is not header]
        for widget in body:
            assert group.isAncestorOf(widget), (header.objectName(), widget.objectName())
        if header.objectName() == "formBuilder.group.content":
            assert body


def test_canvas_stays_nofocus_across_focus_policy_edits(tmp_path: Path, qapp: QApplication) -> None:
    window, surface = _start(tmp_path, qapp)
    try:
        email = _page(surface, "email")
        assert _nofocus(email)
        assert "StrongFocus" in _xml(surface)
        _select(surface, qapp, "email", all_properties=True)
        combo = _combo(surface, "focusPolicy")
        assert combo.currentText() == "Strong focus"
        _pick(combo, qapp, "ClickFocus")
        email = _page(surface, "email")
        assert _nofocus(email)
        assert "ClickFocus" in _xml(surface)
        assert "StrongFocus" not in _xml(surface)
        assert _combo(surface, "focusPolicy").currentText() == "Click focus"
        _reset(surface, qapp, "focusPolicy")
        assert _nofocus(_page(surface, "email"))
        assert "focusPolicy" not in _xml(surface)
        assert _combo(surface, "focusPolicy").currentText() == "Strong focus"
        _tool(surface, qapp, "formBuilder.undo")
        assert _nofocus(_page(surface, "email"))
        assert "ClickFocus" in _xml(surface)
        _tool(surface, qapp, "formBuilder.redo")
        assert _nofocus(_page(surface, "email"))
        assert "focusPolicy" not in _xml(surface)
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_tab_from_the_canvas_does_not_focus_a_page_child(tmp_path: Path, qapp: QApplication) -> None:
    window, surface = _start(tmp_path, qapp)
    try:
        page = surface.page_widget()  # type: ignore[attr-defined]
        assert isinstance(page, QWidget)
        email = page.findChild(QWidget, "email")
        assert email is not None and _nofocus(email)
        assert "StrongFocus" in _xml(surface)
        canvas = surface.findChild(QWidget, "formBuilder.canvas")  # type: ignore[attr-defined]
        assert canvas is not None
        canvas.setFocus()
        _settle(qapp)
        focus: Optional[QWidget] = canvas
        for _ in range(8):
            assert focus is not None
            QTest.keyClick(focus, _key("Key_Tab"))
            _settle(qapp)
            focus = QApplication.focusWidget()
            assert not _inside(page, focus)
    finally:
        shutdown_main_window_for_test(window, qapp)


def _menu_native(bar: QWidget) -> bool:
    # Qt 6 names the getter isNativeMenuBar. The document property stays nativeMenuBar.
    reader = getattr(bar, "isNativeMenuBar", None)
    if callable(reader):
        return bool(reader())
    return bool(bar.nativeMenuBar())


def _toggle_check(surface: object, box: QCheckBox, qapp: QApplication) -> None:
    scroll = surface.findChild(QScrollArea, "formBuilder.inspectorScroll")  # type: ignore[attr-defined]
    if isinstance(scroll, QScrollArea):
        scroll.ensureWidgetVisible(box)
    box.setFocus()
    _settle(qapp)
    # The indicator sits at the left. A center click misses a stretched check box.
    point = QPoint(max(1, min(8, box.width() // 2)), max(1, box.height() // 2))
    QTest.mouseClick(box, _mouse("LeftButton"), _mods("NoModifier"), point)
    _settle(qapp)


def test_menu_bar_stays_non_native_across_edits(tmp_path: Path, qapp: QApplication) -> None:
    window, surface = _start(tmp_path, qapp)
    try:
        bar = _page(surface, "menuBar")
        assert _menu_native(bar) is False
        assert "<bool>true</bool>" in _xml(surface)
        _select(surface, qapp, "menuBar", all_properties=True)
        box = _row(surface, "nativeMenuBar").findChild(QCheckBox)
        assert isinstance(box, QCheckBox) and box.isChecked()
        _toggle_check(surface, box, qapp)
        assert _menu_native(_page(surface, "menuBar")) is False
        assert not _row(surface, "nativeMenuBar").findChild(QCheckBox).isChecked()
        assert "<bool>false</bool>" in _xml(surface)
        _reset(surface, qapp, "nativeMenuBar")
        assert _menu_native(_page(surface, "menuBar")) is False
        assert "nativeMenuBar" not in _xml(surface)
        _tool(surface, qapp, "formBuilder.undo")
        assert _menu_native(_page(surface, "menuBar")) is False
        assert "<bool>false</bool>" in _xml(surface)
        _tool(surface, qapp, "formBuilder.undo")
        assert _menu_native(_page(surface, "menuBar")) is False
        assert "<bool>true</bool>" in _xml(surface)
        _tool(surface, qapp, "formBuilder.redo")
        assert _menu_native(_page(surface, "menuBar")) is False
        assert "<bool>false</bool>" in _xml(surface)
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_tab_from_search_visits_each_group_before_the_next(tmp_path: Path, qapp: QApplication) -> None:
    window, surface = _start(tmp_path, qapp)
    try:
        _click_canvas(surface, qapp, "okButton")
        inspector = _inspector(surface)
        search = surface.findChild(QLineEdit, "formBuilder.inspectorSearch")  # type: ignore[attr-defined]
        assert isinstance(search, QLineEdit)
        search.setFocus()
        _settle(qapp)
        sequence = _tab_stops(search, inspector, qapp)
        _assert_group_tabs(inspector, sequence)
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_shift_tab_reverses_the_inspector_group_order(tmp_path: Path, qapp: QApplication) -> None:
    window, surface = _start(tmp_path, qapp)
    try:
        _click_canvas(surface, qapp, "okButton")
        inspector = _inspector(surface)
        search = surface.findChild(QLineEdit, "formBuilder.inspectorSearch")  # type: ignore[attr-defined]
        assert isinstance(search, QLineEdit)
        search.setFocus()
        _settle(qapp)
        forward = _tab_stops(search, inspector, qapp)
        assert len(forward) >= 2
        last = forward[-1]
        last.setFocus()
        _settle(qapp)
        backward: List[QWidget] = []
        focus: Optional[QWidget] = last
        for _ in range(len(forward) - 1):
            assert focus is not None
            QTest.keyClick(focus, _key("Key_Backtab"))
            _settle(qapp)
            focus = QApplication.focusWidget()
            assert _inside(inspector, focus)
            assert focus is not None
            backward.append(focus)
        assert backward == list(reversed(forward[:-1]))
        QTest.keyClick(backward[-1], _key("Key_Backtab"))
        _settle(qapp)
        assert QApplication.focusWidget() is search
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_font_size_commits_once_on_enter(tmp_path: Path, qapp: QApplication) -> None:
    window, surface = _start(tmp_path, qapp)
    try:
        _select(surface, qapp, "okButton")
        _spin, line = _spin_line(surface, "font")
        before = _undo_count(surface)
        _type_number(qapp, line, "120")
        assert _undo_count(surface) == before
        assert "<pointsize>120</pointsize>" not in _xml(surface)
        assert _spin_line(surface, "font")[0].value() != 120
        QTest.keyClick(line, _key("Key_Return"))
        _settle(qapp)
        assert _undo_count(surface) == before + 1
        assert _spin_line(surface, "font")[0].value() == 120
        assert "<pointsize>120</pointsize>" in _xml(surface)
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_font_size_escape_reverts_uncommitted_digits(tmp_path: Path, qapp: QApplication) -> None:
    window, surface = _start(tmp_path, qapp)
    try:
        _select(surface, qapp, "okButton")
        spin, line = _spin_line(surface, "font")
        shown = spin.text()
        before = _undo_count(surface)
        _type_number(qapp, line, "120")
        assert line.text() != shown
        QTest.keyClick(line, _key("Key_Escape"))
        _settle(qapp)
        assert _spin_line(surface, "font")[0].text() == shown
        assert _undo_count(surface) == before
        assert "<pointsize>120</pointsize>" not in _xml(surface)
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_minimum_size_width_commits_once_on_enter(tmp_path: Path, qapp: QApplication) -> None:
    window, surface = _start(tmp_path, qapp)
    try:
        _select(surface, qapp, "okButton", all_properties=True)
        _spin, line = _spin_line(surface, "minimumSize", 0)
        before = _undo_count(surface)
        _type_number(qapp, line, "120")
        assert _undo_count(surface) == before
        assert "<width>120</width>" not in _xml(surface)
        assert _spin_line(surface, "minimumSize", 0)[0].value() != 120
        QTest.keyClick(line, _key("Key_Return"))
        _settle(qapp)
        assert _undo_count(surface) == before + 1
        assert _spin_line(surface, "minimumSize", 0)[0].value() == 120
        assert "<width>120</width>" in _xml(surface)
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_minimum_size_width_escape_reverts_uncommitted_digits(tmp_path: Path, qapp: QApplication) -> None:
    window, surface = _start(tmp_path, qapp)
    try:
        _select(surface, qapp, "okButton", all_properties=True)
        spin, line = _spin_line(surface, "minimumSize", 0)
        shown = spin.text()
        before = _undo_count(surface)
        _type_number(qapp, line, "120")
        assert line.text() != shown
        QTest.keyClick(line, _key("Key_Escape"))
        _settle(qapp)
        assert _spin_line(surface, "minimumSize", 0)[0].text() == shown
        assert _undo_count(surface) == before
        assert "<width>120</width>" not in _xml(surface)
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_shift_click_scrolls_the_inspector_to_the_top(tmp_path: Path, qapp: QApplication) -> None:
    window, surface = _start(tmp_path, qapp)
    try:
        inspector = _inspector(surface)
        inspector.set_group_expanded(GroupId.ALL, True)  # type: ignore[attr-defined]
        _click_canvas(surface, qapp, "email")
        scroll = surface.findChild(QScrollArea, "formBuilder.inspectorScroll")  # type: ignore[attr-defined]
        assert isinstance(scroll, QScrollArea)
        bar = scroll.verticalScrollBar()
        assert bar.maximum() > 0
        bar.setValue(bar.maximum())
        assert bar.value() > 0
        _click_canvas(surface, qapp, "okButton", "ShiftModifier")
        assert bar.value() == 0
        names = set()
        session = surface.session  # type: ignore[attr-defined]
        for node_id in session.selection.state.ids:
            node = session.document.node(node_id)
            name = getattr(node, "object_name", "")
            if name:
                names.add(name)
        assert names == {"email", "okButton"}
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_committing_a_connection_keeps_focus_inside_the_inspector(
    tmp_path: Path, qapp: QApplication
) -> None:
    window, surface = _start(tmp_path, qapp)
    try:
        _select(surface, qapp, "okButton")
        inspector = _inspector(surface)
        tabs = surface.findChild(QTabWidget, "formBuilder.inspectorTabs")  # type: ignore[attr-defined]
        assert isinstance(tabs, QTabWidget)
        bar = tabs.tabBar()
        QTest.mouseClick(bar, _mouse("LeftButton"), _mods("NoModifier"), bar.tabRect(1).center())
        _settle(qapp)
        add = next(button for button in inspector.findChildren(QPushButton) if "Add connection" in button.text())
        before = len(surface.session.document.connections())  # type: ignore[attr-defined]
        QTest.mouseClick(add, _mouse("LeftButton"))
        _settle(qapp)
        signal = surface.findChild(QComboBox, "formBuilder.draftSignal")  # type: ignore[attr-defined]
        slot = surface.findChild(QComboBox, "formBuilder.draftSlot")  # type: ignore[attr-defined]
        assert isinstance(signal, QComboBox) and isinstance(slot, QComboBox)
        assert slot.count() > 0
        signal.hidePopup()
        slot.setFocus()
        slot.showPopup()
        _settle(qapp)
        outside: List[str] = []

        def watch(_old: object, new: object) -> None:
            if new is None:
                return
            if isinstance(new, QWidget) and _inside(inspector, new):
                return
            if not isinstance(new, QWidget):
                outside.append("none")
                return
            chain = []
            current: Optional[QWidget] = new
            for _ in range(8):
                if current is None:
                    break
                chain.append(current.objectName() or type(current).__name__)
                current = current.parentWidget()
            outside.append(">".join(chain))

        qapp.focusChanged.connect(watch)
        try:
            focus = QApplication.focusWidget() or slot
            QTest.keyClick(focus, _key("Key_Down"))
            _settle(qapp)
            current = QApplication.focusWidget() or focus
            QTest.keyClick(current, _key("Key_Return"))
            _settle(qapp)
        finally:
            qapp.focusChanged.disconnect(watch)
        assert outside == []
        final = QApplication.focusWidget()
        if final is not None:
            assert _inside(inspector, final), final
        draft = surface.findChild(QWidget, "formBuilder.connectionDraft")  # type: ignore[attr-defined]
        assert draft is None
        assert len(surface.session.document.connections()) == before + 1  # type: ignore[attr-defined]
    finally:
        shutdown_main_window_for_test(window, qapp)
