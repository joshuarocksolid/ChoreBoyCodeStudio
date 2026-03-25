"""Syntax color override preference contracts."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from app.core import constants

THEME_LIGHT = constants.UI_SYNTAX_COLORS_LIGHT_KEY
THEME_DARK = constants.UI_SYNTAX_COLORS_DARK_KEY
SYNTAX_THEMES: tuple[str, str] = (THEME_LIGHT, THEME_DARK)
_HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


@dataclass(frozen=True)
class SyntaxColorToken:
    """One customizable syntax color token."""

    key: str
    label: str
    category: str


SYNTAX_COLOR_TOKENS: tuple[SyntaxColorToken, ...] = (
    SyntaxColorToken("keyword", "Keyword", "Lexical"),
    SyntaxColorToken("builtin", "Builtin", "Lexical"),
    SyntaxColorToken("string", "String", "Lexical"),
    SyntaxColorToken("comment", "Comment", "Lexical"),
    SyntaxColorToken("number", "Number", "Lexical"),
    SyntaxColorToken("function", "Function", "Lexical"),
    SyntaxColorToken("class", "Class", "Lexical"),
    SyntaxColorToken("decorator", "Decorator", "Lexical"),
    SyntaxColorToken("operator", "Operator", "Lexical"),
    SyntaxColorToken("punctuation", "Punctuation", "Lexical"),
    SyntaxColorToken("parameter", "Parameter", "Lexical"),
    SyntaxColorToken("json_key", "JSON Key", "Lexical"),
    SyntaxColorToken("json_literal", "JSON Literal", "Lexical"),
    SyntaxColorToken("markdown_heading", "Markdown Heading", "Lexical"),
    SyntaxColorToken("markdown_emphasis", "Markdown Emphasis", "Lexical"),
    SyntaxColorToken("markdown_code", "Markdown Code", "Lexical"),
    SyntaxColorToken("semantic_function", "Semantic Function", "Semantic"),
    SyntaxColorToken("semantic_method", "Semantic Method", "Semantic"),
    SyntaxColorToken("semantic_class", "Semantic Class", "Semantic"),
    SyntaxColorToken("semantic_parameter", "Semantic Parameter", "Semantic"),
    SyntaxColorToken("semantic_import", "Semantic Import", "Semantic"),
    SyntaxColorToken("semantic_variable", "Semantic Variable", "Semantic"),
    SyntaxColorToken("semantic_property", "Semantic Property", "Semantic"),
    SyntaxColorToken("semantic_constant", "Semantic Constant", "Semantic"),
)

_KNOWN_TOKEN_KEYS: frozenset[str] = frozenset(token.key for token in SYNTAX_COLOR_TOKENS)


def parse_syntax_color_overrides(settings_payload: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """Parse persisted syntax color overrides for light/dark themes."""
    section = settings_payload.get(constants.UI_SYNTAX_COLORS_SETTINGS_KEY, {})
    if not isinstance(section, dict):
        return {THEME_LIGHT: {}, THEME_DARK: {}}
    parsed: dict[str, dict[str, str]] = {THEME_LIGHT: {}, THEME_DARK: {}}
    for theme_name in SYNTAX_THEMES:
        theme_payload = section.get(theme_name, {})
        if not isinstance(theme_payload, dict):
            continue
        parsed[theme_name] = _normalize_theme_token_map(theme_payload)
    return parsed


def _normalize_theme_token_map(theme_payload: Mapping[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for token_key, color_value in theme_payload.items():
        if token_key not in _KNOWN_TOKEN_KEYS or not isinstance(color_value, str):
            continue
        normalized_color = normalize_hex_color(color_value)
        if normalized_color is None:
            continue
        normalized[token_key] = normalized_color
    return normalized


def normalize_hex_color(value: str) -> str | None:
    """Normalize and validate user-provided hex color."""
    candidate = value.strip()
    if not candidate.startswith("#"):
        candidate = f"#{candidate}"
    if not _HEX_COLOR_PATTERN.match(candidate):
        return None
    return candidate.upper()
