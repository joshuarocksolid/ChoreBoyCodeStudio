# pyright: reportAttributeAccessIssue=false
"""Every focusable builder control has an accessible name."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.install import form_builder_enabled
from app.qt.QtCore import Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtWidgets import QApplication, QWidget
from app.shell.main_window import MainWindow
from testing.main_window_shutdown import shutdown_main_window_for_test

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


def _focusable(root: QWidget) -> list:
    widgets = [root]
    widgets.extend(root.findChildren(QWidget))
    no_focus = getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus")
    return [widget for widget in widgets if widget.isVisible() and widget.focusPolicy() != no_focus]
