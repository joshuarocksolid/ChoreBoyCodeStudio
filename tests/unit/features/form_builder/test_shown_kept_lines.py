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


def test_kept_note_lands_on_the_first_line_of_the_kept_rect(qapp: QApplication, tmp_path: Path) -> None:
    """``<rect>`` does not read because of ``<fancything/>``, so the whole rect is kept."""
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
        assert [shown[line - 1].strip() for line in editor.notes] == ["<rect>"]
        (start,) = editor.notes
        span = shown[start - 1 :]
        assert any("fancything" in line for line in span[: span.index("   </rect>") + 1])
    finally:
        surface.release()
        parent.deleteLater()


_MIXED = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <widget class="QLabel" name="title">
   <property name="text"><string>Invoice entry</string></property>
  </widget>
  <widget class="QLabel" name="shopName">
   <property name="text"><string>a<b>x</b>c</string></property>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _surface(qapp: QApplication, tmp_path: Path, text: str) -> tuple:
    path = tmp_path / "invoice.ui"
    path.write_text(text, encoding="utf-8")
    parent = QWidget()
    editors: list[_NotedEditor] = []

    def create_source_editor() -> _NotedEditor:
        editor = _NotedEditor(parent)
        editors.append(editor)
        return editor

    request = TabSurfaceRequest(
        file_path=str(path),
        initial_text=text,
        parent=parent,
        theme=tokens_from_palette(qapp.palette(), force_mode="light"),
        create_source_editor=create_source_editor,  # type: ignore[arg-type]
        open_linked_file=lambda _linked: None,
        project_root=None,
    )
    return FormTabProvider().create_surface(request), parent, editors


def _marked(editor: _NotedEditor) -> list:
    shown = editor.toPlainText().splitlines()
    return [shown[line - 1].strip() for line in sorted(editor.notes)]


def test_kept_note_is_on_the_opaque_string_line_only(qapp: QApplication, tmp_path: Path) -> None:
    surface, parent, editors = _surface(qapp, tmp_path, _MIXED)
    try:
        surface.toggle_source_view()
        qapp.processEvents()
        assert _marked(editors[0]) == ['<property name="text"><string>a<b>x</b>c</string></property>']

        # A later XML edit moves the string down two lines. The note follows it.
        editor = editors[0]
        before = sorted(editor.notes)
        editor.setPlainText(editor.toPlainText().replace(" <class>Invoice</class>\n", " <class>Invoice</class>\n\n\n"))
        surface._kept_timer.timeout.emit()  # noqa: SLF001 - the typing pause
        assert sorted(editor.notes) == [line + 2 for line in before]
        assert _marked(editor) == ['<property name="text"><string>a<b>x</b>c</string></property>']

        # Apply, then look again: the view now shows the writer's layout.
        surface.toggle_source_view()
        qapp.processEvents()
        surface.toggle_source_view()
        qapp.processEvents()
        marked = _marked(editor)
        assert len(marked) == 1 and "<string>a<b>x</b>c</string>" in marked[0]
    finally:
        surface.release()
        parent.deleteLater()
