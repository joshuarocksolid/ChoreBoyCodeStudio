"""Unit tests for CodeEditorWidget editing behavior."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import QEvent, QMimeData, Qt  # noqa: E402
from PySide2.QtGui import QKeyEvent, QTextCursor  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.editors.code_editor_widget import CodeEditorWidget  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


@pytest.fixture()
def editor() -> CodeEditorWidget:
    widget = CodeEditorWidget()
    yield widget
    widget.close()
    widget.deleteLater()
    QApplication.processEvents()


def test_toggle_comment_selection_expands_partial_selection_to_full_lines(editor: CodeEditorWidget) -> None:
    editor.setPlainText("alpha = 1\nbeta = 2\n")
    cursor = editor.textCursor()
    cursor.setPosition(2)
    cursor.setPosition(len("alpha = 1\nbe"), QTextCursor.KeepAnchor)
    editor.setTextCursor(cursor)

    editor.toggle_comment_selection()

    assert editor.toPlainText() == "#alpha = 1\n#beta = 2\n"


def test_enter_key_auto_indents_after_colon(editor: CodeEditorWidget) -> None:
    editor.setPlainText("if ready:")
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.End)
    editor.setTextCursor(cursor)

    editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))

    assert editor.toPlainText() == "if ready:\n    "


def test_enter_key_auto_indents_with_tab_preference(editor: CodeEditorWidget) -> None:
    editor.set_editor_preferences(
        tab_width=4,
        font_point_size=10,
        indent_style="tabs",
        indent_size=4,
    )
    editor.setPlainText("if ready:")
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.End)
    editor.setTextCursor(cursor)

    editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))

    assert editor.toPlainText() == "if ready:\n\t"


def test_replace_document_text_preserves_single_undo_step(editor: CodeEditorWidget) -> None:
    editor.setPlainText("import b\nimport a\n")

    editor.replace_document_text("import a\nimport b\n")

    assert editor.toPlainText() == "import a\nimport b\n"

    editor.undo()

    assert editor.toPlainText() == "import b\nimport a\n"


def test_paste_reindented_flat_python_inserts_repaired_text_and_undoes(editor: CodeEditorWidget) -> None:
    QApplication.clipboard().setText("def first():\nreturn 1")

    result = editor.paste_reindented_flat_python()

    assert result.parse_ok is True
    assert editor.toPlainText() == "def first():\n    return 1"

    editor.undo()

    assert editor.toPlainText() == ""


def test_paste_reindented_flat_python_uses_tab_preference(editor: CodeEditorWidget) -> None:
    editor.set_editor_preferences(
        tab_width=4,
        font_point_size=10,
        indent_style="tabs",
        indent_size=4,
    )
    QApplication.clipboard().setText("def first():\nreturn 1")

    editor.paste_reindented_flat_python()

    assert editor.toPlainText() == "def first():\n\treturn 1"


def test_reindent_flat_python_selection_changes_only_selected_lines(editor: CodeEditorWidget) -> None:
    editor.setPlainText("before = True\ndef first():\nreturn 1\nafter = True")
    cursor = editor.textCursor()
    cursor.setPosition(len("before = True\n"))
    cursor.setPosition(len("before = True\ndef first():\nreturn 1"), QTextCursor.KeepAnchor)
    editor.setTextCursor(cursor)

    result = editor.reindent_flat_python_selection()

    assert result.parse_ok is True
    assert editor.toPlainText() == "before = True\ndef first():\n    return 1\nafter = True"


def test_insert_from_mime_data_leaves_paste_literal_when_auto_repair_disabled(editor: CodeEditorWidget) -> None:
    mime = QMimeData()
    mime.setText("def first():\nreturn 1")

    editor.insertFromMimeData(mime)

    assert editor.toPlainText() == "def first():\nreturn 1"


def test_insert_from_mime_data_repairs_only_high_confidence_when_enabled(editor: CodeEditorWidget) -> None:
    editor.set_editor_preferences(
        tab_width=4,
        font_point_size=10,
        indent_style="spaces",
        indent_size=4,
        auto_reindent_flat_python_paste=True,
    )
    mime = QMimeData()
    mime.setText("def first():\nreturn 1")

    editor.insertFromMimeData(mime)

    assert editor.toPlainText() == "def first():\n    return 1"
