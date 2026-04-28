"""Kind -> visual style (glyph + accent color) mapping for completion items.

Pure module: no Qt widget construction here. Colors are resolved against a
:class:`ShellThemeTokens` instance so the same mapping works for light and
dark themes.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.intelligence.completion_models import CompletionKind
from app.shell.theme_tokens import ShellThemeTokens


@dataclass(frozen=True)
class KindGlyphStyle:
    """Visual presentation for a single :class:`CompletionKind`."""

    glyph: str
    accent_color: str
    label: str


# Token field names on ShellThemeTokens. We resolve at runtime so per-theme
# overrides flow through automatically. Kept as field names (not values) so
# the table is theme-agnostic.
_KIND_TABLE: dict[CompletionKind, tuple[str, str, str]] = {
    # kind: (glyph, theme_token_field, human_label)
    CompletionKind.KEYWORD: ("K", "syntax_keyword", "keyword"),
    CompletionKind.BUILTIN: ("B", "syntax_builtin", "builtin"),
    CompletionKind.SYMBOL: ("S", "syntax_semantic_variable", "symbol"),
    CompletionKind.MODULE: ("m", "syntax_keyword_import", "module"),
    CompletionKind.FUNCTION: ("ƒ", "syntax_function", "function"),
    CompletionKind.METHOD: ("M", "syntax_semantic_method", "method"),
    CompletionKind.PROPERTY: ("P", "syntax_semantic_property", "property"),
    CompletionKind.ATTRIBUTE: ("a", "syntax_semantic_variable", "attribute"),
    CompletionKind.CLASS: ("C", "syntax_class", "class"),
    CompletionKind.SNIPPET: ("\u03bb", "accent", "snippet"),  # lambda
    CompletionKind.TEXT: ("T", "text_muted", "text"),
}


_DEFAULT_GLYPH = "?"
_DEFAULT_LABEL = "symbol"


def kind_style_for(kind: CompletionKind, tokens: ShellThemeTokens) -> KindGlyphStyle:
    """Return the visual presentation for a completion kind under ``tokens``.

    Falls back to ``accent`` if a theme leaves a syntax slot empty so the row
    never renders with an empty color string.
    """

    glyph, token_field, label = _KIND_TABLE.get(
        kind, (_DEFAULT_GLYPH, "accent", _DEFAULT_LABEL)
    )
    color = _resolve_color(tokens, token_field)
    return KindGlyphStyle(glyph=glyph, accent_color=color, label=label)


def kind_styles_for_tokens(tokens: ShellThemeTokens) -> dict[CompletionKind, KindGlyphStyle]:
    """Pre-compute the full kind -> style mapping for a tokens snapshot."""

    return {kind: kind_style_for(kind, tokens) for kind in CompletionKind}


def _resolve_color(tokens: ShellThemeTokens, token_field: str) -> str:
    value = getattr(tokens, token_field, "") or ""
    if value:
        return value
    # Syntax tokens may be unset on minimal theme variants; fall back to the
    # generic accent so the kind chip still renders with a visible color.
    fallback = tokens.accent or tokens.text_primary or "#888888"
    return fallback
