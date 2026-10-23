"""Kept-as-is notes follow the XML the view is showing."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.integration.provider import FormTabProvider  # noqa: E402
from app.qt.QtWidgets import QApplication, QPlainTextEdit, QWidget  # noqa: E402
from app.shell.tab_content_providers import TabSurfaceRequest  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402

pytestmark = pytest.mark.unit

_UI = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry">
   <rect>
    <x>0</x>
    <y>0</y>
    <width>100</width>
    <height>40</height>
    <!-- dropped -->
    <!-- dropped -->
    <!-- dropped -->
    <fancything/>
   </rect>
  </property>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


class _NotedEditor(QPlainTextEdit):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.notes: dict[int, str] = {}

    def set_gutter_notes(self, notes: object) -> None:
        self.notes = dict(notes)  # type: ignore[arg-type]

    def go_to_line(self, line_number: int) -> None:
        del line_number

    def apply_theme(self, _tokens: object) -> None:
        return None


def test_kept_note_lands_on_the_fancything_line_of_the_shown_file(qapp: QApplication, tmp_path: Path) -> None:
    path = tmp_path / "form.ui"
    path.write_text(_UI, encoding="utf-8")
    parent = QWidget()
    editor_box: list[_NotedEditor] = []

    def create_source_editor() -> _NotedEditor:
        editor = _NotedEditor(parent)
        editor_box.append(editor)
        return editor

    app = QApplication.instance()
    assert app is not None
    request = TabSurfaceRequest(
        file_path=str(path),
        initial_text=_UI,
        parent=parent,
        theme=tokens_from_palette(app.palette(), force_mode="light"),
        create_source_editor=create_source_editor,  # type: ignore[arg-type]
        open_linked_file=lambda _linked: None,
        project_root=None,
    )
    surface = FormTabProvider().create_surface(request)
    try:
        toggle = surface.findChild(QWidget, "formBuilder.viewXml")
        assert toggle is not None
        toggle.setChecked(True)  # type: ignore[attr-defined]
        qapp.processEvents()
        editor = editor_box[0]
        shown = editor.toPlainText().splitlines()
        marked = [shown[line - 1] for line in editor.notes]
        assert any("fancything" in line for line in marked)
    finally:
        surface.release()
        parent.deleteLater()
