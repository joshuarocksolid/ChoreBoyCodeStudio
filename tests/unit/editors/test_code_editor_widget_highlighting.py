"""Unit tests for editor highlighting integration helpers."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtGui import QTextCursor  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.core import constants  # noqa: E402
from app.editors.code_editor_widget import CodeEditorWidget  # noqa: E402
from app.intelligence.diagnostics_service import CodeDiagnostic, DiagnosticSeverity  # noqa: E402
from app.intelligence.semantic_tokens import MODIFIER_READONLY, SemanticTokenSpan  # noqa: E402

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


def test_reduced_highlighting_mode_suppresses_semantic_overlay() -> None:
    editor = CodeEditorWidget()
    editor.setPlainText("def build(value):\n    return value\n")
    editor.set_highlighting_policy(
        adaptive_mode=constants.HIGHLIGHTING_MODE_REDUCED,
        reduced_threshold_chars=250_000,
        lexical_only_threshold_chars=600_000,
    )
    editor.set_semantic_token_spans(
        [
            SemanticTokenSpan(start=4, end=9, token_type="function"),
            SemanticTokenSpan(start=10, end=15, token_type="parameter"),
        ]
    )
    assert editor._semantic_selections == []


def test_lexical_only_mode_skips_non_cursor_overlays() -> None:
    editor = CodeEditorWidget()
    editor.setPlainText("def build(value):\n    return value\n")
    editor.set_semantic_token_spans([SemanticTokenSpan(start=4, end=9, token_type="function")])
    editor.set_highlighting_policy(
        adaptive_mode=constants.HIGHLIGHTING_MODE_LEXICAL_ONLY,
        reduced_threshold_chars=10,
        lexical_only_threshold_chars=10,
    )
    assert editor._non_cursor_extra_selections() == []


def test_large_documents_cap_overlay_decorations_to_viewport_budget() -> None:
    editor = CodeEditorWidget()
    editor.setPlainText("value = 1\n" * 40_000)
    diagnostics = [
        CodeDiagnostic(
            code="T001",
            severity=DiagnosticSeverity.WARNING,
            file_path="/tmp/main.py",
            line_number=index + 1,
            message="warning",
        )
        for index in range(3_000)
    ]
    editor.set_diagnostics(diagnostics)
    # One line highlight + capped non-cursor overlays.
    assert len(editor.extraSelections()) <= 701


def test_readonly_semantic_modifier_uses_constant_semantic_color() -> None:
    editor = CodeEditorWidget()
    editor.setPlainText("APP_DIR = '/tmp'\n")
    editor.set_semantic_token_spans(
        [
            SemanticTokenSpan(
                start=0,
                end=7,
                token_type="variable",
                token_modifiers=(MODIFIER_READONLY,),
            )
        ]
    )
    colors = [selection.format.foreground().color().name().lower() for selection in editor.extraSelections()]
    assert editor._semantic_token_colors["constant"].name().lower() in colors


def test_semantic_signature_skips_rebuild_for_equivalent_spans() -> None:
    editor = CodeEditorWidget()
    editor.setPlainText("value = 1\n")
    spans_a = [SemanticTokenSpan(start=0, end=5, token_type="variable", token_modifiers=("readonly", "reference"))]
    spans_b = [SemanticTokenSpan(start=0, end=5, token_type="variable", token_modifiers=("reference", "readonly"))]
    editor.set_semantic_token_spans(spans_a)
    generation_after_first = editor._overlay_generation
    editor.set_semantic_token_spans(spans_b)
    assert editor._overlay_generation == generation_after_first
