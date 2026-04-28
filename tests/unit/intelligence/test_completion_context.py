"""Unit tests for completion context classification."""

from __future__ import annotations

import pytest

from app.intelligence.completion_context import (
    CompletionSyntacticContext,
    build_completion_context,
)

pytestmark = pytest.mark.unit


def test_completion_context_detects_import_from_member() -> None:
    source = "from PySide2 import QtWi"

    context = build_completion_context(
        source_text=source,
        cursor_position=len(source),
        current_file_path="/tmp/main.py",
        project_root=None,
        trigger_is_manual=False,
        min_prefix_chars=2,
        max_results=100,
    )

    assert context.syntactic_context == CompletionSyntacticContext.IMPORT_FROM_MEMBER
    assert context.module_name == "PySide2"
    assert context.prefix == "QtWi"
    assert context.replacement_range.start == len("from PySide2 import ")
    assert context.trusted_runtime_module == "PySide2"


def test_completion_context_detects_import_module_member() -> None:
    source = "import PySide2.QtW"

    context = build_completion_context(
        source_text=source,
        cursor_position=len(source),
        current_file_path="/tmp/main.py",
        project_root=None,
        trigger_is_manual=False,
        min_prefix_chars=2,
        max_results=100,
    )

    assert context.syntactic_context == CompletionSyntacticContext.IMPORT_MODULE
    assert context.module_name == "PySide2"
    assert context.prefix == "QtW"


def test_completion_context_marks_comment_as_no_completion_zone() -> None:
    source = "# PySide2."

    context = build_completion_context(
        source_text=source,
        cursor_position=len(source),
        current_file_path="/tmp/main.py",
        project_root=None,
        trigger_is_manual=False,
        min_prefix_chars=2,
        max_results=100,
    )

    assert context.syntactic_context == CompletionSyntacticContext.STRING_OR_COMMENT
    assert context.should_offer_automatic_results is False
