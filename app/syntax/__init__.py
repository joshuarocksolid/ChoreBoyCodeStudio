"""Neutral syntax highlighting contracts shared by editors and tree-sitter."""

from app.syntax.contracts import TokenStyle, ThemedSyntaxHighlighter
from app.syntax.palette import (
    DEFAULT_DARK_PALETTE,
    DEFAULT_HC_DARK_PALETTE,
    DEFAULT_HC_LIGHT_PALETTE,
    DEFAULT_LIGHT_PALETTE,
    SYNTAX_PALETTE_FIELD_MAP,
    SyntaxPalette,
    build_syntax_palette,
    syntax_palette_from_tokens,
)

__all__ = [
    "DEFAULT_DARK_PALETTE",
    "DEFAULT_LIGHT_PALETTE",
    "SYNTAX_PALETTE_FIELD_MAP",
    "SyntaxPalette",
    "TokenStyle",
    "ThemedSyntaxHighlighter",
    "build_syntax_palette",
    "syntax_palette_from_tokens",
]
