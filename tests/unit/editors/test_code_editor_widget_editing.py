"""Unit tests for CodeEditorWidget editing behavior."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import QEvent, Qt  # noqa: E402
from PySide2.QtGui import QKeyEvent, QTextCursor  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.editors.code_editor_widget import CodeEditorWidget  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(request: pytest.FixtureRequest):  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


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
