"""Unit tests for tree-sitter syntax highlighter registry."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtGui", exc_type=ImportError)

from PySide2.QtGui import QPalette, QTextDocument  # noqa: E402

from app.editors.syntax_registry import default_syntax_highlighter_registry, syntax_palette_from_tokens  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402
from app.treesitter.loader import initialize_tree_sitter_runtime  # noqa: E402

pytestmark = pytest.mark.unit
_TREE_SITTER_AVAILABLE = initialize_tree_sitter_runtime().is_available


def _assert_python_highlighter_shape(highlighter: object | None) -> None:
    if _TREE_SITTER_AVAILABLE:
        assert highlighter is not None
        assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
        return
    assert highlighter is None


def test_registry_returns_python_highlighter_for_py_extension() -> None:
    registry = default_syntax_highlighter_registry()
    highlighter = registry.create_for_path(
        file_path="/tmp/example.py",
        document=QTextDocument(),
        is_dark=False,
    )
    _assert_python_highlighter_shape(highlighter)


def test_registry_sniffs_shebang_for_python_without_extension() -> None:
    registry = default_syntax_highlighter_registry()
    highlighter = registry.create_for_path(
        file_path="/tmp/script",
        document=QTextDocument(),
        is_dark=False,
        sample_text="#!/usr/bin/env python\nprint('ok')\n",
    )
    _assert_python_highlighter_shape(highlighter)


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
    _assert_python_highlighter_shape(highlighter)


def test_registry_sniffs_extensionless_markdown_files() -> None:
    registry = default_syntax_highlighter_registry()
    highlighter = registry.create_for_path(
        file_path="/tmp/CHANGELOG",
        document=QTextDocument(),
        is_dark=False,
        sample_text="## 1.0.0\n- Added feature\n",
    )
    if _TREE_SITTER_AVAILABLE:
        assert highlighter is not None
        assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
        return
    assert highlighter is None


def test_registry_sniffs_extensionless_python_without_shebang() -> None:
    registry = default_syntax_highlighter_registry()
    highlighter = registry.create_for_path(
        file_path="/tmp/wscript",
        document=QTextDocument(),
        is_dark=False,
        sample_text="def configure(ctx):\n    pass\n",
    )
    _assert_python_highlighter_shape(highlighter)


def test_registry_supports_ui_extension_via_xml_grammar() -> None:
    registry = default_syntax_highlighter_registry()
    highlighter = registry.create_for_path(
        file_path="/tmp/form.ui",
        document=QTextDocument(),
        is_dark=False,
        sample_text="<ui version=\"4.0\"></ui>\n",
    )
    if _TREE_SITTER_AVAILABLE:
        assert highlighter is not None
        assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
        return
    assert highlighter is None


def test_registry_uses_ini_fallback_for_desktop_entries() -> None:
    registry = default_syntax_highlighter_registry()
    highlighter = registry.create_for_path(
        file_path="/tmp/choreboy_code_studio.desktop",
        document=QTextDocument(),
        is_dark=False,
        sample_text="[Desktop Entry]\nName=Code Studio\n",
    )
    assert highlighter is not None
    assert highlighter.__class__.__name__ == "IniSyntaxHighlighter"


def test_syntax_palette_includes_extended_semantic_keys() -> None:
    tokens = tokens_from_palette(QPalette(), force_mode="dark")
    palette = syntax_palette_from_tokens(tokens)
    assert palette["keyword_control"] == tokens.syntax_keyword_control
    assert palette["keyword_import"] == tokens.syntax_keyword_import
    assert palette["keyword_operator"] == tokens.syntax_keyword_operator
    assert palette["escape"] == tokens.syntax_escape
    assert palette["markdown_strong"] == tokens.syntax_markdown_strong
    assert palette["semantic_function"] == tokens.syntax_semantic_function
    assert palette["semantic_method"] == tokens.syntax_semantic_method
    assert palette["semantic_class"] == tokens.syntax_semantic_class
    assert palette["semantic_parameter"] == tokens.syntax_semantic_parameter
    assert palette["semantic_import"] == tokens.syntax_semantic_import
    assert palette["semantic_variable"] == tokens.syntax_semantic_variable
    assert palette["semantic_property"] == tokens.syntax_semantic_property
    assert palette["semantic_constant"] == tokens.syntax_semantic_constant


def test_syntax_palette_keyword_operator_override_propagates() -> None:
    """Custom keyword_operator color set by the user must reach the highlighter palette."""
    custom_color = "#123456"
    base_tokens = tokens_from_palette(QPalette(), force_mode="dark")
    from dataclasses import replace

    overridden_tokens = replace(base_tokens, syntax_keyword_operator=custom_color)
    palette = syntax_palette_from_tokens(overridden_tokens)
    assert palette["keyword_operator"] == custom_color


def test_registry_returns_tree_sitter_for_multiple_languages() -> None:
    registry = default_syntax_highlighter_registry()
    for file_path in ("/tmp/example.py", "/tmp/settings.json", "/tmp/readme.md"):
        highlighter = registry.create_for_path(
            file_path=file_path,
            document=QTextDocument(),
            is_dark=False,
            sample_text="placeholder",
        )
        if _TREE_SITTER_AVAILABLE:
            assert highlighter is not None
            assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
            continue
        assert highlighter is None
