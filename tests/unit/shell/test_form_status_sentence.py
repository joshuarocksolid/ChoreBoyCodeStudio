"""A form tab reports its own sentence on the shell status bar."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.install import form_builder_enabled  # noqa: E402
from app.qt.QtWidgets import QApplication, QLabel  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0">
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


def test_form_tab_status_matches_the_surface_sentence(tmp_path: Path, qapp: QApplication) -> None:
    if not form_builder_enabled():
        pytest.skip("form builder is registered on PySide6")
    ui_path = tmp_path / "invoice.ui"
    ui_path.write_text(_FORM, encoding="utf-8")
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        assert window._editor_tab_factory.open_file_in_editor(str(ui_path))  # noqa: SLF001
        qapp.processEvents()
        label = window.findChild(QLabel, "shell.editorStatusLabel")
        assert label is not None
        surface = window._tab_content_registry.surface_for_path(str(ui_path))  # noqa: SLF001
        assert label.text() == surface.editor_status_sentence()
        assert label.text() == "Invoice · the form"

        assert surface.reveal(1, {"fb_object": "Invoice"})
        qapp.processEvents()
        assert label.text() == surface.editor_status_sentence()
        assert label.text() == "Invoice · the form"

        assert surface.reveal(1, {"fb_object": "okButton"})
        qapp.processEvents()
        assert label.text() == surface.editor_status_sentence()
        assert "OK" in label.text() and "Push button" in label.text()
        assert label.text() != "Invoice · the form"
    finally:
        shutdown_main_window_for_test(window, qapp)
