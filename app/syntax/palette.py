"""Syntax palette defaults and shell token field mapping."""

from __future__ import annotations

from typing import Any, Mapping

SyntaxPalette = dict[str, str]

DEFAULT_LIGHT_PALETTE: SyntaxPalette = {
    "keyword": "#0000FF",
    "keyword_control": "#AF00DB",
    "keyword_import": "#AF00DB",
    "keyword_operator": "#AF00DB",
    "builtin": "#267F99",
    "escape": "#EE0000",
    "string": "#A31515",
    "string_prefix": "#AF00DB",
    "comment": "#008000",
    "number": "#098658",
    "function": "#795E26",
    "class": "#267F99",
    "decorator": "#795E26",
    "operator": "#000000",
    "punctuation": "#000000",
    "parameter": "#001080",
    "json_key": "#0451A5",
    "json_literal": "#0000FF",
    "markdown_heading": "#800000",
    "markdown_emphasis": "#800000",
    "markdown_strong": "#800000",
    "markdown_code": "#800000",
    "semantic_function": "#795E26",
    "semantic_method": "#795E26",
    "semantic_class": "#267F99",
    "semantic_parameter": "#001080",
    "semantic_import": "#001080",
    "semantic_variable": "#001080",
    "semantic_property": "#001080",
    "semantic_constant": "#0070C1",
}
DEFAULT_DARK_PALETTE: SyntaxPalette = {
    "keyword": "#569CD6",
    "keyword_control": "#C586C0",
    "keyword_import": "#C586C0",
    "keyword_operator": "#C586C0",
    "builtin": "#4EC9B0",
    "escape": "#D7BA7D",
    "string": "#CE9178",
    "string_prefix": "#C586C0",
    "comment": "#6A9955",
    "number": "#B5CEA8",
    "function": "#DCDCAA",
    "class": "#4EC9B0",
    "decorator": "#DCDCAA",
    "operator": "#D4D4D4",
    "punctuation": "#D4D4D4",
    "parameter": "#9CDCFE",
    "json_key": "#9CDCFE",
    "json_literal": "#569CD6",
    "markdown_heading": "#569CD6",
    "markdown_emphasis": "#569CD6",
    "markdown_strong": "#569CD6",
    "markdown_code": "#CE9178",
    "semantic_function": "#DCDCAA",
    "semantic_method": "#DCDCAA",
    "semantic_class": "#4EC9B0",
    "semantic_parameter": "#9CDCFE",
    "semantic_import": "#9CDCFE",
    "semantic_variable": "#9CDCFE",
    "semantic_property": "#9CDCFE",
    "semantic_constant": "#4FC1FF",
}
DEFAULT_HC_LIGHT_PALETTE: SyntaxPalette = {
    "keyword": "#0000C0",
    "keyword_control": "#7B1FA2",
    "keyword_import": "#7B1FA2",
    "keyword_operator": "#7B1FA2",
    "builtin": "#005A5A",
    "escape": "#A03000",
    "string": "#9C0000",
    "string_prefix": "#7B1FA2",
    "comment": "#005000",
    "number": "#005000",
    "function": "#5A3500",
    "class": "#005A5A",
    "decorator": "#5A3500",
    "operator": "#000000",
    "punctuation": "#000000",
    "parameter": "#000080",
    "json_key": "#003C8F",
    "json_literal": "#0000C0",
    "markdown_heading": "#5A0000",
    "markdown_emphasis": "#5A0000",
    "markdown_strong": "#5A0000",
    "markdown_code": "#5A0000",
    "semantic_function": "#5A3500",
    "semantic_method": "#5A3500",
    "semantic_class": "#005A5A",
    "semantic_parameter": "#000080",
    "semantic_import": "#000080",
    "semantic_variable": "#000080",
    "semantic_property": "#000080",
    "semantic_constant": "#003C8F",
}
DEFAULT_HC_DARK_PALETTE: SyntaxPalette = {
    "keyword": "#7CB7FF",
    "keyword_control": "#FF9CFF",
    "keyword_import": "#FF9CFF",
    "keyword_operator": "#FF9CFF",
    "builtin": "#5FE3C2",
    "escape": "#FFD787",
    "string": "#FFB088",
    "string_prefix": "#FF9CFF",
    "comment": "#7FCB66",
    "number": "#D5F0AE",
    "function": "#FFFF87",
    "class": "#5FE3C2",
    "decorator": "#FFFF87",
    "operator": "#FFFFFF",
    "punctuation": "#FFFFFF",
    "parameter": "#B8E4FF",
    "json_key": "#B8E4FF",
    "json_literal": "#7CB7FF",
    "markdown_heading": "#7CB7FF",
    "markdown_emphasis": "#7CB7FF",
    "markdown_strong": "#7CB7FF",
    "markdown_code": "#FFB088",
    "semantic_function": "#FFFF87",
    "semantic_method": "#FFFF87",
    "semantic_class": "#5FE3C2",
    "semantic_parameter": "#B8E4FF",
    "semantic_import": "#B8E4FF",
    "semantic_variable": "#B8E4FF",
    "semantic_property": "#B8E4FF",
    "semantic_constant": "#7FD2FF",
}

SYNTAX_PALETTE_FIELD_MAP: dict[str, str] = {
    "keyword": "syntax_keyword",
    "keyword_control": "syntax_keyword_control",
    "keyword_import": "syntax_keyword_import",
    "keyword_operator": "syntax_keyword_operator",
    "builtin": "syntax_builtin",
    "escape": "syntax_escape",
    "string": "syntax_string",
    "string_prefix": "syntax_string_prefix",
    "comment": "syntax_comment",
    "number": "syntax_number",
    "function": "syntax_function",
    "class": "syntax_class",
    "decorator": "syntax_decorator",
    "operator": "syntax_operator",
    "punctuation": "syntax_punctuation",
    "parameter": "syntax_parameter",
    "json_key": "syntax_json_key",
    "json_literal": "syntax_json_literal",
    "markdown_heading": "syntax_markdown_heading",
    "markdown_emphasis": "syntax_markdown_emphasis",
    "markdown_strong": "syntax_markdown_strong",
    "markdown_code": "syntax_markdown_code",
    "semantic_function": "syntax_semantic_function",
    "semantic_method": "syntax_semantic_method",
    "semantic_class": "syntax_semantic_class",
    "semantic_parameter": "syntax_semantic_parameter",
    "semantic_import": "syntax_semantic_import",
    "semantic_variable": "syntax_semantic_variable",
    "semantic_property": "syntax_semantic_property",
    "semantic_constant": "syntax_semantic_constant",
}


def build_syntax_palette(
    *,
    is_dark: bool,
    overrides: Mapping[str, str] | None = None,
) -> SyntaxPalette:
    """Return merged syntax palette for light/dark base mode."""
    palette = dict(DEFAULT_DARK_PALETTE if is_dark else DEFAULT_LIGHT_PALETTE)
    if overrides:
        for key, value in overrides.items():
            if value:
                palette[key] = value
    return palette


def syntax_palette_from_tokens(tokens: Any) -> SyntaxPalette:
    """Build a syntax palette dict from shell theme token fields."""
    return {
        token_key: getattr(tokens, field_name)
        for token_key, field_name in SYNTAX_PALETTE_FIELD_MAP.items()
    }


__all__ = [
    "DEFAULT_DARK_PALETTE",
    "DEFAULT_HC_DARK_PALETTE",
    "DEFAULT_HC_LIGHT_PALETTE",
    "DEFAULT_LIGHT_PALETTE",
    "SYNTAX_PALETTE_FIELD_MAP",
    "SyntaxPalette",
    "build_syntax_palette",
    "syntax_palette_from_tokens",
]
