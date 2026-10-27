# pyright: reportAttributeAccessIssue=false
"""Every focusable builder control has an accessible name."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.install import form_builder_enabled
from app.features.form_builder.qtside.inspector.api import GroupId
from app.qt.QtCore import Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtWidgets import QApplication, QCheckBox, QPushButton, QToolButton, QWidget
from app.shell.main_window import MainWindow
from testing.main_window_shutdown import shutdown_main_window_for_test
from tests.form_builder.perf.reference import reference_form

pytestmark = pytest.mark.usefixtures("qapp")

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <layout class="QVBoxLayout" name="verticalLayout">
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


def test_every_focusable_builder_control_has_an_accessible_name(
    tmp_path: Path, qapp: QApplication
) -> None:
    if not form_builder_enabled():
        pytest.skip("form builder is registered on PySide6")
    path = tmp_path / "invoice.ui"
    path.write_text(_FORM, encoding="utf-8")
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        assert window._editor_tab_factory.open_file_in_editor(str(path))  # noqa: SLF001
        # Without a project the center shows the welcome page. Show the editors.
        stack = window._center_stack  # noqa: SLF001
        assert stack is not None
        stack.setCurrentIndex(1)
        window.resize(1400, 900)
        window.show()
        qapp.processEvents()
        surface = window._tab_content_registry.surface_for_path(str(path))  # noqa: SLF001
        assert isinstance(surface, QWidget)
        seen = _focusable(surface)
        assert any(widget.objectName() == "formBuilder.canvas" for widget in seen)
        missing = [
            widget.objectName() or type(widget).__name__
            for widget in seen
            if not (widget.accessibleName() or "").strip()
        ]
        assert missing == []
        named_with_shortcut = [
            "%s=%r" % (widget.objectName() or type(widget).__name__, widget.accessibleName())
            for widget in seen
            if " (" in (widget.accessibleName() or "")
        ]
        assert named_with_shortcut == []
        canvas = surface.findChild(QWidget, "formBuilder.canvas")
        assert canvas is not None
        assert canvas.accessibleName() == "Form canvas"
        for name, plain in (
            ("formBuilder.undo", "Undo"),
            ("formBuilder.redo", "Redo"),
            ("formBuilder.zoomOut", "Zoom out"),
            ("formBuilder.zoomIn", "Zoom in"),
            ("formBuilder.overflow", "More"),
        ):
            button = surface.findChild(QWidget, name)
            assert button is not None
            assert button.accessibleName() == plain
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_expanded_controls_carry_context_in_their_names(tmp_path: Path, qapp: QApplication) -> None:
    if not form_builder_enabled():
        pytest.skip("form builder is registered on PySide6")
    window, surface = _open_form(tmp_path, qapp, _FORM)
    try:
        _select(surface, "okButton")
        _settle(qapp)
        assert _named(surface, "formBuilder.group.content") == "Content group"
        assert _named(surface, "formBuilder.group.appearance") == "Appearance group"
        assert _check_names(surface, "Bold") == {"Font: Bold"}
        assert _check_names(surface, "Italic") == {"Font: Italic"}
        assert _tool_names(surface) >= {
            "Alignment: Left",
            "Alignment: Horizontal center",
            "Alignment: Vertical center",
            "Alignment: Right",
            "Alignment: Justify",
            "Alignment: Top",
            "Alignment: Bottom",
        }
        crumbs = surface.findChild(QWidget, "formBuilder.inspectorCrumbs")
        assert crumbs is not None and crumbs.isVisible()
        assert crumbs.accessibleName() == "Selection path"
        inspector = surface.findChild(QWidget, "formBuilder.inspector")
        assert inspector is not None
        inspector.set_group_expanded(GroupId.ALL, True)  # type: ignore[attr-defined]
        _select(surface, "okButton", force=True)
        _settle(qapp)
        assert _named(surface, "formBuilder.group.all") == "All properties group"
        icon = surface.findChild(QWidget, "formBuilder.row.icon")
        assert icon is not None
        raw = next(button for button in icon.findChildren(QPushButton) if button.text() == "Raw XML")
        assert raw.accessibleName() == "Icon: Raw XML"
    finally:
        shutdown_main_window_for_test(window, qapp)


@pytest.mark.timeout(120)
def test_every_class_in_the_reference_form_names_focusable_controls(
    tmp_path: Path, qapp: QApplication
) -> None:
    if not form_builder_enabled():
        pytest.skip("form builder is registered on PySide6")
    window, surface = _open_form(tmp_path, qapp, reference_form(25).xml)
    try:
        inspector = surface.findChild(QWidget, "formBuilder.inspector")
        assert inspector is not None
        classes = _one_of_each(surface)
        assert len(classes) >= 10
        for group in GroupId:
            inspector.set_group_expanded(group, False)  # type: ignore[attr-defined]
        for class_name, object_name in classes:
            _select(surface, object_name)
            _settle(qapp)
            _assert_named(surface, "collapsed %s %s" % (class_name, object_name))
        inspector.set_group_expanded(GroupId.ALL, True)  # type: ignore[attr-defined]
        for class_name, object_name in classes:
            _select(surface, object_name, force=True)
            _settle(qapp)
            _assert_named(surface, "expanded %s %s" % (class_name, object_name))
    finally:
        shutdown_main_window_for_test(window, qapp)


def _open_form(tmp_path: Path, qapp: QApplication, text: str) -> tuple:
    path = tmp_path / "invoice.ui"
    path.write_text(text, encoding="utf-8")
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    assert window._editor_tab_factory.open_file_in_editor(str(path))  # noqa: SLF001
    stack = window._center_stack  # noqa: SLF001
    assert stack is not None
    stack.setCurrentIndex(1)
    window.resize(1400, 900)
    window.show()
    qapp.processEvents()
    surface = window._tab_content_registry.surface_for_path(str(path))  # noqa: SLF001
    assert isinstance(surface, QWidget)
    return window, surface


def _settle(qapp: QApplication) -> None:
    for _ in range(4):
        qapp.processEvents()


def _select(surface: QWidget, name: str, *, force: bool = False) -> None:
    session = surface.session  # type: ignore[attr-defined]
    node_id = session.document.by_name(name)[0]
    if force and session.selection.state.ids == (node_id,):
        session.selection.clear(source=SelectionSource.PROGRAM)
    session.selection.set((node_id,), source=SelectionSource.CANVAS)


def _one_of_each(surface: QWidget) -> list:
    chosen = []
    seen = set()
    for widget in surface.session.document.iter_widgets():  # type: ignore[attr-defined]
        if widget.class_name in seen:
            continue
        seen.add(widget.class_name)
        chosen.append((widget.class_name, widget.object_name))
    return chosen


def _named(surface: QWidget, object_name: str) -> str:
    widget = surface.findChild(QWidget, object_name)
    assert widget is not None, object_name
    return widget.accessibleName()


def _check_names(surface: QWidget, text: str) -> set:
    found = [
        box.accessibleName()
        for box in surface.findChildren(QCheckBox)
        if box.isVisible() and box.text() == text
    ]
    assert found, text
    return set(found)


def _tool_names(surface: QWidget) -> set:
    return {
        button.accessibleName()
        for button in surface.findChildren(QToolButton)
        if button.isVisible() and button.accessibleName()
    }


def _assert_named(surface: QWidget, where: str) -> None:
    missing = [
        widget.objectName() or type(widget).__name__
        for widget in _focusable(surface)
        if not (widget.accessibleName() or "").strip()
    ]
    assert missing == [], (where, missing)
    named_with_shortcut = [
        "%s=%r" % (widget.objectName() or type(widget).__name__, widget.accessibleName())
        for widget in _focusable(surface)
        if " (" in (widget.accessibleName() or "")
    ]
    assert named_with_shortcut == [], (where, named_with_shortcut)


def _focusable(root: QWidget) -> list:
    widgets = [root]
    widgets.extend(root.findChildren(QWidget))
    no_focus = getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus")
    return [widget for widget in widgets if widget.isVisible() and widget.focusPolicy() != no_focus]
