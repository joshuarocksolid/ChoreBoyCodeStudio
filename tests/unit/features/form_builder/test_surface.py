"""Opening a .ui builds the structure surface, and save writes the source bytes."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.editors.editor_manager import EditorManager  # noqa: E402
from app.features.form_builder.engine.ui4.writer import write_ui  # noqa: E402
from app.features.form_builder.integration.content_source import open_document_log  # noqa: E402
from app.features.form_builder.integration.provider import FormTabProvider  # noqa: E402
from app.features.form_builder.integration.surface import XML_APPLY_HINT, FormSurface  # noqa: E402
from app.qt.QtWidgets import QLabel, QPlainTextEdit, QPushButton, QTreeWidget, QWidget  # noqa: E402
from app.shell.tab_content_providers import (  # noqa: E402
    ProviderDeclined,
    TabMatchContext,
    TabSurfaceRequest,
)
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="okButton">
     <property name="text">
      <string>OK</string>
     </property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


class _Editor(QPlainTextEdit):
    def apply_theme(self, _tokens: object) -> None:
        return None

    def go_to_line(self, line_number: int) -> None:
        del line_number


def _request(parent: QWidget, text: str, path: str) -> TabSurfaceRequest:
    from app.qt.QtWidgets import QApplication

    app = QApplication.instance()
    assert app is not None
    created: list[_Editor] = []

    def create_source_editor() -> _Editor:
        if created:
            raise RuntimeError("create_source_editor may be called at most once per surface")
        editor = _Editor(parent)
        editor.setObjectName("shell.editorTabs.textEditor")
        created.append(editor)
        return editor

    return TabSurfaceRequest(
        file_path=path,
        initial_text=text,
        parent=parent,
        theme=tokens_from_palette(app.palette(), force_mode="light"),
        create_source_editor=create_source_editor,  # type: ignore[arg-type]
        open_linked_file=lambda _linked: None,
        project_root=None,
    )


def _tree_labels(surface: FormSurface) -> list[str]:
    tree = surface.findChild(QTreeWidget, "formBuilder.structure")
    assert tree is not None
    labels: list[str] = []

    def walk(item: object) -> None:
        labels.append(item.text(0))  # type: ignore[attr-defined]
        for index in range(item.childCount()):  # type: ignore[attr-defined]
            walk(item.child(index))  # type: ignore[attr-defined]

    for index in range(tree.topLevelItemCount()):
        walk(tree.topLevelItem(index))
    return labels


def test_open_shows_the_form_name_and_structure(qapp) -> None:  # type: ignore[no-untyped-def]
    del qapp
    parent = QWidget()
    canonical = write_ui(open_document_log(_FORM).document).text
    surface = FormTabProvider().create_surface(_request(parent, canonical, "/tmp/invoice.ui"))

    assert isinstance(surface, FormSurface)
    name = surface.findChild(QLabel, "formBuilder.name")
    assert name is not None
    assert name.text() == "Form"
    labels = _tree_labels(surface)
    assert "QWidget  Form" in labels
    assert "QPushButton  okButton" in labels
    assert surface.content_source().serialize_count == 0
    assert surface.source_editor() is None
    surface.release()


def test_view_xml_edit_saves_byte_exact_and_undoes(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    del qapp
    canonical = write_ui(open_document_log(_FORM).document).text
    path = tmp_path / "invoice.ui"
    path.write_text(canonical, encoding="utf-8")
    parent = QWidget()
    surface = FormTabProvider().create_surface(_request(parent, canonical, str(path)))
    manager = EditorManager()
    opened = manager.open_file(str(path))
    opened.tab.content_source = surface.content_source()

    toggle = surface.findChild(QPushButton, "formBuilder.viewXml")
    assert toggle is not None
    toggle.setChecked(True)
    editor = surface.source_editor()
    assert isinstance(editor, QPlainTextEdit)
    assert surface.content_source().serialize_count == 1
    banner = surface.findChild(QLabel, "formBuilder.xmlBanner")
    assert banner is not None
    assert banner.text() == XML_APPLY_HINT
    editor.setPlainText(editor.toPlainText().replace(">OK<", ">Save<"))
    toggle.setChecked(False)

    saved = manager.save_tab(str(path))
    disk = path.read_bytes()
    assert disk == saved.current_content.encode("utf-8")
    assert b">Save<" in disk
    assert saved.is_dirty is False

    assert surface.undo() is True
    assert b">OK<" in surface.content_source().current_text().encode("utf-8")
    assert b">Save<" not in surface.content_source().current_text().encode("utf-8")
    assert surface.content_source().is_dirty() is True
    surface.release()


def test_malformed_ui_declines_with_a_line(qapp) -> None:  # type: ignore[no-untyped-def]
    del qapp
    parent = QWidget()
    with pytest.raises(ProviderDeclined) as caught:
        FormTabProvider().create_surface(_request(parent, "<ui>\n", "/tmp/broken.ui"))

    assert "form builder" in caught.value.reason
    assert "line" in caught.value.reason
    assert FormTabProvider().matches("broken.ui", TabMatchContext(project_root=None)) is True
    assert FormTabProvider().matches("broken.py", TabMatchContext(project_root=None)) is False
