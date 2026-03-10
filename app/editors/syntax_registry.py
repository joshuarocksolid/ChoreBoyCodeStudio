"""Language highlighter registry and factory helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide2.QtGui import QTextDocument

from app.editors.syntax_engine import SyntaxPalette
from app.treesitter.highlighter import TreeSitterHighlighter
from app.treesitter.language_registry import default_tree_sitter_language_registry

_DEFAULT_REGISTRY: SyntaxHighlighterRegistry | None = None


class SyntaxHighlighterRegistry:
    def __init__(self) -> None:
        self._language_registry = default_tree_sitter_language_registry()

    def create_for_path(
        self,
        *,
        file_path: str,
        document: QTextDocument,
        is_dark: bool,
        syntax_palette: Mapping[str, str] | None = None,
        sample_text: str = "",
    ) -> object | None:
        resolved = self._language_registry.resolve_for_path(file_path=file_path, sample_text=sample_text)
        if resolved is None:
            return None
        language_key, language, query_source = resolved
        return TreeSitterHighlighter(
            document,
            language=language,
            query_source=query_source,
            language_key=language_key,
            is_dark=is_dark,
            syntax_palette=dict(syntax_palette or {}),
        )

    @staticmethod
    def apply_theme(
        highlighter: object | None,
        *,
        is_dark: bool,
        syntax_palette: Mapping[str, str] | None = None,
    ) -> None:
        if highlighter is None:
            return
        if hasattr(highlighter, "set_theme_palette"):
            highlighter.set_theme_palette(syntax_palette, is_dark=is_dark)  # type: ignore[union-attr]
            return
        if hasattr(highlighter, "set_dark_mode"):
            highlighter.set_dark_mode(is_dark)  # type: ignore[union-attr]


def default_syntax_highlighter_registry() -> SyntaxHighlighterRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = SyntaxHighlighterRegistry()
    return _DEFAULT_REGISTRY


def syntax_palette_from_tokens(tokens: Any) -> SyntaxPalette:
    return {
        "keyword": tokens.syntax_keyword,
        "keyword_control": tokens.syntax_keyword_control,
        "keyword_import": tokens.syntax_keyword_import,
        "builtin": tokens.syntax_builtin,
        "escape": tokens.syntax_escape,
        "string": tokens.syntax_string,
        "comment": tokens.syntax_comment,
        "number": tokens.syntax_number,
        "function": tokens.syntax_function,
        "class": tokens.syntax_class,
        "decorator": tokens.syntax_decorator,
        "operator": tokens.syntax_operator,
        "punctuation": tokens.syntax_punctuation,
        "parameter": tokens.syntax_parameter,
        "json_key": tokens.syntax_json_key,
        "json_literal": tokens.syntax_json_literal,
        "markdown_heading": tokens.syntax_markdown_heading,
        "markdown_emphasis": tokens.syntax_markdown_emphasis,
        "markdown_strong": tokens.syntax_markdown_strong,
        "markdown_code": tokens.syntax_markdown_code,
        "semantic_function": tokens.syntax_semantic_function,
        "semantic_method": tokens.syntax_semantic_method,
        "semantic_class": tokens.syntax_semantic_class,
        "semantic_parameter": tokens.syntax_semantic_parameter,
        "semantic_import": tokens.syntax_semantic_import,
        "semantic_variable": tokens.syntax_semantic_variable,
        "semantic_property": tokens.syntax_semantic_property,
        "semantic_constant": tokens.syntax_semantic_constant,
    }
