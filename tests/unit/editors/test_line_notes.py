"""Gutter notes follow the text they were anchored to."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.editors.code_editor_chrome_mixin import LineNote  # noqa: E402
from app.editors.code_editor_widget import CodeEditorWidget  # noqa: E402
from app.qt.QtGui import QTextCursor  # noqa: E402
from app.qt.QtWidgets import QApplication  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402

pytestmark = pytest.mark.unit

_THEMES = (
    "light",
    "dark",
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


@pytest.fixture()
def editor():  # type: ignore[no-untyped-def]
    widget = CodeEditorWidget()
    widget.setPlainText("alpha\nbeta\ngamma\n")
    yield widget
    widget.close()
    widget.deleteLater()
    QApplication.processEvents()


def test_line_note_moves_when_a_line_is_inserted_above(editor: CodeEditorWidget) -> None:
    editor.set_line_notes((LineNote(2, 3, "Kept as is", "kept the node"),))
    assert editor.line_note_tooltip(2) == "kept the node"
    assert editor.line_note_tooltip(4) is None

    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.Start)
    cursor.insertText("head\n")

    assert editor.line_note_tooltip(2) is None
    assert editor.line_note_tooltip(3) == "kept the node"
    assert editor.line_note_tooltip(4) == "kept the node"


def test_clearing_line_notes_removes_the_mark(editor: CodeEditorWidget) -> None:
    editor.set_line_notes((LineNote(1, 1, "Kept as is", "because"),))
    editor.set_line_notes(())
    assert editor.line_note_tooltip(1) is None


def test_gutter_click_still_toggles_the_breakpoint_on_a_noted_line(editor: CodeEditorWidget) -> None:
    editor.resize(420, 200)
    editor.show()
    editor.set_line_notes((LineNote(1, 2, "Kept as is", "because"),))
    block = editor.document().findBlockByNumber(0)
    top = int(editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top())
    editor.toggle_breakpoint_at_y(top + 1)
    assert editor.breakpoints() == {1}


def test_gutter_paints_notes_in_each_theme(editor: CodeEditorWidget, qapp) -> None:  # type: ignore[no-untyped-def]
    editor.resize(420, 200)
    editor.show()
    editor.set_breakpoints({1})
    editor.set_debug_execution_line(2)
    editor.set_line_notes((LineNote(1, 2, "Kept as is", "kept the node"),))
    for mode in _THEMES:
        editor.apply_theme(tokens_from_palette(qapp.palette(), force_mode=mode))
        editor.repaint()
        assert editor.line_note_tooltip(1) == "kept the node"
        assert editor.line_note_tooltip(2) == "kept the node"
    assert editor.breakpoints() == {1}
