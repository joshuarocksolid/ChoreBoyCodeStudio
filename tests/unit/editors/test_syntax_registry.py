"""Unit tests for syntax highlighter registry."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtGui", exc_type=ImportError)

from PySide2.QtGui import QTextDocument  # noqa: E402

from app.editors.syntax_registry import default_syntax_highlighter_registry  # noqa: E402

pytestmark = pytest.mark.unit


def test_registry_returns_python_highlighter_for_py_extension() -> None:
    registry = default_syntax_highlighter_registry()
    highlighter = registry.create_for_path(
        file_path="/tmp/example.py",
        document=QTextDocument(),
        is_dark=False,
    )
    assert highlighter is not None
    assert highlighter.__class__.__name__ == "PythonSyntaxHighlighter"


def test_registry_sniffs_shebang_for_python_without_extension() -> None:
    registry = default_syntax_highlighter_registry()
    highlighter = registry.create_for_path(
        file_path="/tmp/script",
        document=QTextDocument(),
        is_dark=False,
        sample_text="#!/usr/bin/env python\nprint('ok')\n",
    )
    assert highlighter is not None
    assert highlighter.__class__.__name__ == "PythonSyntaxHighlighter"


def test_registry_returns_none_for_unknown_text_without_sniff_match() -> None:
    registry = default_syntax_highlighter_registry()
    highlighter = registry.create_for_path(
        file_path="/tmp/notes.bin",
        document=QTextDocument(),
        is_dark=False,
        sample_text="plain text",
    )
    assert highlighter is None
