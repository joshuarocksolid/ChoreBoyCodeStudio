# pyright: reportAttributeAccessIssue=false
"""Problems single click, the Form menu mnemonic, and Insert Return."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.diagnostics import (  # noqa: E402
    DiagnosticLocation,
    FormDiagnostic,
    Severity,
)
from app.features.form_builder.install import form_builder_enabled  # noqa: E402
from app.intelligence.diagnostics_models import CodeDiagnostic, DiagnosticSeverity  # noqa: E402
from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import (  # noqa: E402
    QApplication,
    QListWidget,
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
  <layout class="QVBoxLayout" name="mainLayout">
   <item>
    <widget class="QPushButton" name="okButton">
     <property name="text"><string>OK</string></property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_DUPLICATE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <layout class="QVBoxLayout" name="mainLayout">
   <item>
    <widget class="QPushButton" name="okButton">
     <property name="text"><string>OK</string></property>
     <property name="text"><string>Save</string></property>
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


def _button() -> Qt.MouseButton:
    return getattr(getattr(Qt, "MouseButton", Qt), "LeftButton")


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


def _window(tmp_path: Path) -> MainWindow:
    return MainWindow(state_root=str((tmp_path / "state").resolve()))


def _xml_checked(surface: object) -> bool:
    toggle = surface.findChild(QWidget, "formBuilder.viewXml")  # type: ignore[attr-defined]
    assert toggle is not None
    return bool(toggle.isChecked())


def _selected_name(surface: object) -> str:
    tree = surface.findChild(QTreeWidget, "formBuilder.structure")  # type: ignore[attr-defined]
    assert isinstance(tree, QTreeWidget)
    item = tree.currentItem()
    if item is None:
        return ""
    return item.text(0)


def _show_problems(window: MainWindow, qapp: QApplication) -> QTreeWidget:
    tabs = window._bottom_tabs_widget  # noqa: SLF001
    panel = window._problems_panel  # noqa: SLF001
    assert tabs is not None and panel is not None
    tabs.setCurrentWidget(panel)
    splitter = window._vertical_splitter  # noqa: SLF001
    splitter.setSizes([600, 280])
    qapp.processEvents()
    return panel.tree_widget()


def _row(tree: QTreeWidget, text: str) -> QTreeWidgetItem:
    app = QApplication.instance()
    for _ in range(5):
        if app is not None:
            app.processEvents()
        found = _live_row(tree, text)
        if found is not None:
            return found
    raise AssertionError(text)


def _live_row(tree: QTreeWidget, text: str) -> QTreeWidgetItem | None:
    for index in range(tree.topLevelItemCount()):
        group = tree.topLevelItem(index)
        if group is None:
            continue
        try:
            child_count = group.childCount()
        except RuntimeError:
            continue
        for child_index in range(child_count):
            try:
                child = group.child(child_index)
                if child is not None and text in child.text(1):
                    return child
            except RuntimeError:
                continue
    return None


def _click(tree: QTreeWidget, item: QTreeWidgetItem, qapp: QApplication, *, double: bool) -> None:
    tree.scrollToItem(item)
    qapp.processEvents()
    pos = tree.visualItemRect(item).center()
    button = _button()
    modifier = _mod("NoModifier")
    if double:
        QTest.mouseDClick(tree.viewport(), button, modifier, pos)
    else:
        QTest.mouseClick(tree.viewport(), button, modifier, pos)
    qapp.processEvents()


def _problems_focus(window: MainWindow) -> bool:
    focus = QApplication.focusWidget()
    panel = window._problems_panel  # noqa: SLF001
    assert panel is not None
    tree = panel.tree_widget()
    return focus is tree or (isinstance(focus, QWidget) and tree.isAncestorOf(focus))


def test_single_click_on_a_form_problem_selects_the_widget(tmp_path: Path, qapp: QApplication) -> None:
    _require()
    window = _window(tmp_path)
    try:
        surface = _open(window, qapp, tmp_path / "invoice.ui", _DUPLICATE)
        tree = _show_problems(window, qapp)
        _click(tree, _row(tree, "okButton"), qapp, double=False)
        assert not _xml_checked(surface)
        assert _selected_name(surface) == "okButton"
        assert _problems_focus(window)
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_single_click_on_a_form_problem_without_a_widget_does_nothing(
    tmp_path: Path, qapp: QApplication
) -> None:
    _require()
    window = _window(tmp_path)
    path = tmp_path / "invoice.ui"
    try:
        surface = _open(window, qapp, path, _FORM)
        panel = window._problems_panel  # noqa: SLF001
        assert panel is not None
        panel.set_diagnostics(
            [
                CodeDiagnostic(
                    code="FB006",
                    severity=DiagnosticSeverity.INFO,
                    file_path=str(path),
                    line_number=1,
                    message="Kept an extra root widget.",
                    detail={"source_label": "Form", "location_label": "Ln 1"},
                )
            ]
        )
        tree = _show_problems(window, qapp)
        _click(tree, _row(tree, "Kept an extra root widget."), qapp, double=False)
        assert not _xml_checked(surface)
        assert _selected_name(surface) == ""
        assert _problems_focus(window)
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_double_click_on_a_form_problem_without_a_widget_opens_xml(
    tmp_path: Path, qapp: QApplication
) -> None:
    _require()
    window = _window(tmp_path)
    try:
        surface = _open(window, qapp, tmp_path / "invoice.ui", _FORM)
        toggle = surface.findChild(QWidget, "formBuilder.viewXml")  # type: ignore[attr-defined]
        assert toggle is not None
        toggle.click()
        qapp.processEvents()
        toggle.click()
        qapp.processEvents()
        assert not toggle.isChecked()
        surface.session.diagnostics.publish(  # type: ignore[attr-defined]
            "reader",
            (
                FormDiagnostic(
                    code="FB003",
                    severity=Severity.WARNING,
                    message='This form says version "9". The form builder expects 4.x.',
                    location=DiagnosticLocation(line=2),
                    source="reader",
                ),
            ),
        )
        qapp.processEvents()
        tree = _show_problems(window, qapp)
        item = _row(tree, "version")
        tree.scrollToItem(item)
        qapp.processEvents()
        item = _row(tree, "version")
        pos = tree.visualItemRect(item).center()
        button = _button()
        modifier = _mod("NoModifier")
        QTest.mouseClick(tree.viewport(), button, modifier, pos)
        qapp.processEvents()
        assert not toggle.isChecked()
        item = _row(tree, "version")
        QTest.mouseDClick(tree.viewport(), button, modifier, tree.visualItemRect(item).center())
        qapp.processEvents()
        assert toggle.isChecked()
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_alt_o_opens_the_form_menu(tmp_path: Path, qapp: QApplication) -> None:
    _require()
    window = _window(tmp_path)
    try:
        _open(window, qapp, tmp_path / "invoice.ui", _FORM)
        window.activateWindow()
        qapp.processEvents()
        QTest.keyClick(window, _key("Key_O"), _mod("AltModifier"))
        qapp.processEvents()
        popup = QApplication.activePopupWidget()
        assert popup is not None
        assert popup.objectName() == "formBuilder.menu"
    finally:
        popup = QApplication.activePopupWidget()
        if popup is not None:
            popup.close()
        shutdown_main_window_for_test(window, qapp)


@pytest.mark.parametrize("key_name", ["Key_Return", "Key_Enter"])
def test_enter_on_an_insert_tile_inserts_the_widget(
    tmp_path: Path, qapp: QApplication, key_name: str
) -> None:
    _require()
    window = _window(tmp_path)
    try:
        surface = _open(window, qapp, tmp_path / "invoice.ui", _FORM)
        body = surface.findChild(QListWidget, "formBuilder.insertBody")  # type: ignore[attr-defined]
        assert isinstance(body, QListWidget)
        tile = None
        for index in range(body.count()):
            item = body.item(index)
            if item is not None and item.text() == "Button":
                tile = item
        assert tile is not None
        body.setCurrentItem(tile)
        body.setFocus()
        qapp.processEvents()
        before = len(surface.session.log.entries())  # type: ignore[attr-defined]
        QTest.keyClick(body, _key(key_name))
        qapp.processEvents()
        assert len(surface.session.log.entries()) == before + 1  # type: ignore[attr-defined]
        assert _selected_name(surface) == "pushButton"
    finally:
        shutdown_main_window_for_test(window, qapp)
