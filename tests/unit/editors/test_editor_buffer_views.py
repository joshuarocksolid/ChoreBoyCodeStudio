"""Two views of one buffer: one document, one highlighter, one buffer state."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import QEvent  # noqa: E402
from PySide2.QtGui import QSyntaxHighlighter, QTextCursor  # noqa: E402

from app.editors.code_editor_widget import CodeEditorWidget  # noqa: E402
from app.intelligence.diagnostics_service import CodeDiagnostic, DiagnosticSeverity  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


def _split(text: str = "def f():\n    return 1\n" * 6) -> tuple[CodeEditorWidget, CodeEditorWidget]:
    first = CodeEditorWidget()
    first.setPlainText(text)
    first.set_language_for_path("/tmp/example.py")
    second = CodeEditorWidget()
    second.share_buffer_with(first)
    return first, second


def test_second_view_reuses_the_buffer_highlighter() -> None:
    first, second = _split()

    highlighters = first.document().findChildren(QSyntaxHighlighter)

    assert second.document() is first.document()
    assert second.viewportMargins().left() == first.viewportMargins().left()
    assert len(highlighters) <= 1
    assert second._highlighter is first._highlighter
    second.set_language_for_path("/tmp/example.py")
    assert len(first.document().findChildren(QSyntaxHighlighter)) == len(highlighters)


def test_views_share_text_undo_breakpoints_and_diagnostics() -> None:
    first, second = _split()

    cursor = second.textCursor()
    cursor.movePosition(QTextCursor.End)
    cursor.insertText("x = 2\n")
    second.setTextCursor(cursor)
    assert first.toPlainText().endswith("x = 2\n")
    first.undo()
    assert not second.toPlainText().endswith("x = 2\n")

    first.toggle_breakpoint(2)
    assert second.breakpoints() == {2}
    first.set_diagnostics([CodeDiagnostic(code="E1", severity=DiagnosticSeverity.ERROR, file_path="/tmp/example.py", line_number=1, message="bad")])
    assert len(second._diagnostic_selections) == 1
    second.clear_diagnostics()
    assert first._diagnostic_selections == []


def test_buffer_outlives_the_view_that_created_it(qapp) -> None:  # type: ignore[no-untyped-def]
    first, second = _split("kept\n")
    first.deleteLater()
    qapp.processEvents()
    qapp.sendPostedEvents(None, QEvent.DeferredDelete)

    assert second.toPlainText() == "kept\n"
    assert second.buffer_views() == [second]
