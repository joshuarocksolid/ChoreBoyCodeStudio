"""Unit tests for syntax highlighter registry."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtGui", exc_type=ImportError)

from PySide2.QtGui import QPalette, QTextDocument  # noqa: E402

from app.editors.syntax_registry import default_syntax_highlighter_registry, syntax_palette_from_tokens  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402

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


def test_registry_supports_pyw_extension_for_python() -> None:
    registry = default_syntax_highlighter_registry()
    highlighter = registry.create_for_path(
        file_path="/tmp/gui.pyw",
        document=QTextDocument(),
        is_dark=False,
    )
    assert highlighter is not None
    assert highlighter.__class__.__name__ == "PythonSyntaxHighlighter"


def test_registry_sniffs_extensionless_markdown_files() -> None:
    registry = default_syntax_highlighter_registry()
    highlighter = registry.create_for_path(
        file_path="/tmp/CHANGELOG",
        document=QTextDocument(),
        is_dark=False,
        sample_text="## 1.0.0\n- Added feature\n",
    )
    assert highlighter is not None
    assert highlighter.__class__.__name__ == "MarkdownSyntaxHighlighter"


def test_registry_sniffs_extensionless_python_without_shebang() -> None:
    registry = default_syntax_highlighter_registry()
    highlighter = registry.create_for_path(
        file_path="/tmp/wscript",
        document=QTextDocument(),
        is_dark=False,
        sample_text="def configure(ctx):\n    pass\n",
    )
    assert highlighter is not None
    assert highlighter.__class__.__name__ == "PythonSyntaxHighlighter"


def test_syntax_palette_includes_extended_semantic_keys() -> None:
    tokens = tokens_from_palette(QPalette(), force_mode="dark")
    palette = syntax_palette_from_tokens(tokens)
    assert palette["semantic_function"] == tokens.syntax_semantic_function
    assert palette["semantic_method"] == tokens.syntax_semantic_method
    assert palette["semantic_class"] == tokens.syntax_semantic_class
    assert palette["semantic_parameter"] == tokens.syntax_semantic_parameter
    assert palette["semantic_import"] == tokens.syntax_semantic_import
    assert palette["semantic_variable"] == tokens.syntax_semantic_variable
    assert palette["semantic_property"] == tokens.syntax_semantic_property
