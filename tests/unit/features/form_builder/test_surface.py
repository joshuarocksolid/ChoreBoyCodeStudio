"""Opening a .ui builds the structure surface, and save writes the source bytes."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.editors.editor_manager import EditorManager  # noqa: E402
from app.features.form_builder.engine.ui4.writer import write_ui  # noqa: E402
from app.features.form_builder.integration.content_source import open_document_log  # noqa: E402
from app.features.form_builder.integration.provider import FormTabProvider  # noqa: E402
from app.features.form_builder.integration.surface import (  # noqa: E402
    XML_APPLY_HINT,
    XML_DISCARD_LABEL,
    FormSurface,
)
from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtGui import QTextCursor  # noqa: E402
from app.qt.QtWidgets import QLabel, QPlainTextEdit, QPushButton, QToolButton, QTreeWidget, QWidget  # noqa: E402
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
        cursor = self.textCursor()
        move = getattr(QTextCursor, "MoveOperation", QTextCursor)
        mode = getattr(QTextCursor, "MoveMode", QTextCursor)
        cursor.movePosition(getattr(move, "Start"))
        cursor.movePosition(getattr(move, "Down"), getattr(mode, "MoveAnchor"), max(0, int(line_number) - 1))
        self.setTextCursor(cursor)

    def set_line_notes(self, _notes: object) -> None:
        return None


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
        publish_problems=lambda _path, _rows: None,
        show_problems=lambda: None,
        save_file=lambda _path: True,
        unsaved_text=lambda _path: None,
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
    assert name.text() == "Form · Vertical layout"
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

    toggle = surface.findChild(QToolButton, "formBuilder.viewXml")
    assert toggle is not None
    toggle.setChecked(True)
    editor = surface.source_editor()
    assert isinstance(editor, QPlainTextEdit)
    assert surface.content_source().serialize_count == 0
    banner = surface.findChild(QLabel, "formBuilder.xmlBannerText")
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


def test_decline_reason_ends_with_one_period(qapp) -> None:  # type: ignore[no-untyped-def]
    del qapp
    parent = QWidget()
    with pytest.raises(ProviderDeclined) as caught:
        FormTabProvider().create_surface(_request(parent, "\ud800", "/tmp/broken.ui"))

    reason = caught.value.reason
    assert reason.endswith(".")
    assert not reason.endswith("..")


_LOOSE = """<?xml version="1.0" encoding="UTF-8"?>

<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form"/>
 <resources/>
 <connections/>
</ui>
"""


def test_save_without_edits_keeps_noncanonical_bytes(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    del qapp
    canonical = write_ui(open_document_log(_LOOSE).document).text
    assert canonical != _LOOSE
    path = tmp_path / "invoice.ui"
    path.write_text(_LOOSE, encoding="utf-8")
    before = path.read_bytes()
    parent = QWidget()
    surface = FormTabProvider().create_surface(_request(parent, _LOOSE, str(path)))
    manager = EditorManager()
    opened = manager.open_file(str(path))
    opened.tab.content_source = surface.content_source()

    manager.save_tab(str(path))

    assert path.read_bytes() == before
    toggle = surface.findChild(QToolButton, "formBuilder.viewXml")
    assert toggle is not None
    toggle.setChecked(True)
    editor = surface.source_editor()
    assert isinstance(editor, QPlainTextEdit)
    assert editor.toPlainText() == _LOOSE
    surface.release()


def test_invalid_xml_save_then_design_stays_in_xml(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    canonical = write_ui(open_document_log(_FORM).document).text
    path = tmp_path / "invoice.ui"
    path.write_text(canonical, encoding="utf-8")
    parent = QWidget()
    surface = FormTabProvider().create_surface(_request(parent, canonical, str(path)))
    manager = EditorManager()
    opened = manager.open_file(str(path))
    opened.tab.content_source = surface.content_source()
    toggle = surface.findChild(QToolButton, "formBuilder.viewXml")
    assert toggle is not None
    toggle.setChecked(True)
    editor = surface.source_editor()
    assert isinstance(editor, QPlainTextEdit)
    editor.setPlainText("\n" * 5 + "<ui>")

    manager.save_tab(str(path))
    saved_bytes = path.read_bytes()
    toggle.setChecked(False)

    assert surface.content_source().mode == "xml"
    assert toggle.isChecked() is True
    assert path.read_bytes() == saved_bytes
    assert b"<ui>" in saved_bytes
    assert b"okButton" not in saved_bytes
    banner = surface.findChild(QLabel, "formBuilder.xmlBannerText")
    assert banner is not None
    assert banner.isVisibleTo(surface) is True
    assert banner.text().startswith("Line ")
    assert banner.text().endswith("Fix it, or")
    assert "[Discard" not in banner.text()
    discard = surface.findChild(QPushButton, "formBuilder.discardXml")
    assert discard is not None
    assert discard.text() == XML_DISCARD_LABEL
    assert discard.isVisibleTo(surface) is True
    assert discard.focusPolicy() != Qt.NoFocus
    tree = surface.findChild(QTreeWidget, "formBuilder.structure")
    assert tree is not None
    assert tree.isHidden() is True
    for mode in ("light", "dark", "high_contrast_light", "high_contrast_dark"):
        tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
        surface.apply_theme(tokens)
        assert tokens.diag_error_color in banner.parentWidget().styleSheet()

    reported = int(banner.text().split(":", 1)[0].replace("Line ", ""))
    assert editor.textCursor().blockNumber() == reported - 1

    discard.click()

    assert surface.content_source().mode == "visual"
    assert toggle.isChecked() is False
    assert banner.isVisibleTo(surface) is False
    assert discard.isVisibleTo(surface) is False
    assert "QPushButton  okButton" in _tree_labels(surface)
    assert surface.content_source().log.document.root.object_name == "Form"
    surface.release()


def test_form_controls_have_accessible_names(qapp) -> None:  # type: ignore[no-untyped-def]
    del qapp
    parent = QWidget()
    canonical = write_ui(open_document_log(_FORM).document).text
    surface = FormTabProvider().create_surface(_request(parent, canonical, "/tmp/invoice.ui"))

    name = surface.findChild(QLabel, "formBuilder.name")
    tree = surface.findChild(QTreeWidget, "formBuilder.structure")
    banner = surface.findChild(QLabel, "formBuilder.xmlBannerText")
    assert name is not None and tree is not None and banner is not None
    assert name.accessibleName() == "Form · Vertical layout"
    assert tree.accessibleName() == "Form structure"
    assert banner.accessibleName() == "XML notice"
    surface.release()
