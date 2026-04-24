"""Unit tests for code editor highlighting integration helpers."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtGui import QTextCursor  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.core import constants  # noqa: E402
from app.editors.code_editor_widget import CodeEditorWidget  # noqa: E402
from app.editors.find_replace_bar import FindOptions  # noqa: E402
from app.intelligence.diagnostics_service import CodeDiagnostic, DiagnosticSeverity  # noqa: E402
from app.treesitter.loader import initialize_tree_sitter_runtime  # noqa: E402

pytestmark = pytest.mark.unit
_TREE_SITTER_AVAILABLE = initialize_tree_sitter_runtime().is_available


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


def test_language_detection_supports_shebang_without_extension() -> None:
    editor = CodeEditorWidget()
    editor.setPlainText("#!/usr/bin/env python\nprint('ok')\n")
    editor.set_language_for_path("/tmp/script")
    if _TREE_SITTER_AVAILABLE:
        assert editor._highlighter is not None
        assert editor._highlighter.__class__.__name__ == "TreeSitterHighlighter"
        return
    assert editor._highlighter is None


def test_language_detection_uses_tree_sitter_for_json() -> None:
    editor = CodeEditorWidget()
    editor.setPlainText('{"ok": true}\n')
    editor.set_language_for_path("/tmp/config.json")
    if _TREE_SITTER_AVAILABLE:
        assert editor._highlighter is not None
        assert editor._highlighter.__class__.__name__ == "TreeSitterHighlighter"
        return
    assert editor._highlighter is None


def test_large_documents_skip_bracket_matching_scan() -> None:
    editor = CodeEditorWidget()
    editor.set_highlighting_policy(
        adaptive_mode=constants.HIGHLIGHTING_MODE_NORMAL,
        reduced_threshold_chars=10_000,
        lexical_only_threshold_chars=500_000,
    )
    editor.setPlainText("(\n" + ("line = 1\n" * 1_200) + ")\n")
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.End)
    editor.setTextCursor(cursor)
    assert editor._is_large_document() is True
    assert editor._build_bracket_match_selections() == []


def test_reduced_mode_activates_when_document_crosses_threshold() -> None:
    editor = CodeEditorWidget()
    editor.set_highlighting_policy(
        adaptive_mode=constants.HIGHLIGHTING_MODE_NORMAL,
        reduced_threshold_chars=10_000,
        lexical_only_threshold_chars=500_000,
    )
    editor.setPlainText("value = 1\n" * 1_100)
    assert editor._effective_highlighting_mode() == constants.HIGHLIGHTING_MODE_REDUCED


def test_lexical_only_mode_can_be_forced() -> None:
    editor = CodeEditorWidget()
    editor.setPlainText("def build(value):\n    return value\n")
    editor.set_highlighting_policy(
        adaptive_mode=constants.HIGHLIGHTING_MODE_LEXICAL_ONLY,
        reduced_threshold_chars=250_000,
        lexical_only_threshold_chars=600_000,
    )
    assert editor._effective_highlighting_mode() == constants.HIGHLIGHTING_MODE_LEXICAL_ONLY
    assert editor._build_bracket_match_selections() == []


def test_large_documents_cap_overlay_decorations_to_viewport_budget() -> None:
    editor = CodeEditorWidget()
    editor.set_highlighting_policy(
        adaptive_mode=constants.HIGHLIGHTING_MODE_NORMAL,
        reduced_threshold_chars=10_000,
        lexical_only_threshold_chars=500_000,
    )
    editor.setPlainText("value = 1\n" * 1_100)
    assert editor._is_large_document() is True
    diagnostics = [
        CodeDiagnostic(
            code="T001",
            severity=DiagnosticSeverity.WARNING,
            file_path="/tmp/main.py",
            line_number=index + 1,
            message="warning",
        )
        for index in range(1_100)
    ]
    editor.set_diagnostics(diagnostics)
    editor.highlight_all_matches("value", FindOptions())
    # One line highlight + capped non-cursor overlays.
    assert len(editor.extraSelections()) <= 701


def test_notify_highlighter_viewport_lines_updates_window_for_large_modes() -> None:
    if not _TREE_SITTER_AVAILABLE:
        pytest.skip("Tree-sitter runtime unavailable in this environment.")
    editor = CodeEditorWidget()
    editor.resize(800, 500)
    editor.set_highlighting_policy(
        adaptive_mode=constants.HIGHLIGHTING_MODE_REDUCED,
        reduced_threshold_chars=10_000,
        lexical_only_threshold_chars=500_000,
    )
    editor.setPlainText("line\n" * 400)
    editor.set_language_for_path("/tmp/main.py")
    editor._notify_highlighter_viewport_lines()
    assert editor._highlighter is not None
    viewport_lines = getattr(editor._highlighter, "_viewport_lines", (0, 0))
    assert viewport_lines[1] >= viewport_lines[0]
    assert viewport_lines != (0, 0)


def test_language_override_can_force_xml_and_plain_text_modes() -> None:
    if not _TREE_SITTER_AVAILABLE:
        pytest.skip("Tree-sitter runtime unavailable in this environment.")
    editor = CodeEditorWidget()
    editor.setPlainText("<ui version=\"4.0\"></ui>\n")
    editor.set_language_for_path("/tmp/layout.txt")
    assert editor._highlighter is None

    editor.set_language_override("xml")
    assert editor._highlighter is not None
    assert editor._highlighter.__class__.__name__ == "TreeSitterHighlighter"

    editor.set_language_override("plain_text")
    assert editor._highlighter is None

    editor.clear_language_override()
    assert editor._highlighter is None


def test_describe_token_under_cursor_reports_semantic_token_details() -> None:
    if not _TREE_SITTER_AVAILABLE:
        pytest.skip("Tree-sitter runtime unavailable in this environment.")
    editor = CodeEditorWidget()
    editor.setPlainText("def build(value):\n    return value\n")
    editor.set_language_for_path("/tmp/main.py")
    cursor = editor.textCursor()
    cursor.setPosition(editor.toPlainText().index("value", editor.toPlainText().index("return")))
    editor.setTextCursor(cursor)

    description = editor.describe_token_under_cursor()

    assert "Language: Python (python)" in description
    assert "Token: semantic_parameter" in description
    assert "Origin: locals" in description
