"""Unit tests for editor highlighting integration helpers."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtGui import QTextCursor  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.editors.code_editor_widget import CodeEditorWidget  # noqa: E402
from app.intelligence.semantic_tokens import SemanticTokenSpan  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_language_detection_supports_shebang_without_extension() -> None:
    editor = CodeEditorWidget()
    editor.setPlainText("#!/usr/bin/env python\nprint('ok')\n")
    editor.set_language_for_path("/tmp/script")
    assert editor._highlighter is not None
    assert editor._highlighter.__class__.__name__ == "PythonSyntaxHighlighter"


def test_semantic_spans_are_applied_as_extra_selections() -> None:
    editor = CodeEditorWidget()
    editor.setPlainText("def build(value):\n    return value\n")
    spans = [
        SemanticTokenSpan(start=4, end=9, token_type="function"),
        SemanticTokenSpan(start=10, end=15, token_type="parameter"),
    ]
    editor.set_semantic_token_spans(spans)
    colors = [selection.format.foreground().color().name().lower() for selection in editor.extraSelections()]
    assert editor._semantic_token_colors["function"].name().lower() in colors
    assert editor._semantic_token_colors["parameter"].name().lower() in colors


def test_large_documents_skip_bracket_matching_scan() -> None:
    editor = CodeEditorWidget()
    editor.setPlainText("(\n" + ("line = 1\n" * 30_000) + ")\n")
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.End)
    editor.setTextCursor(cursor)
    assert editor._is_large_document() is True
    assert editor._build_bracket_match_selections() == []
