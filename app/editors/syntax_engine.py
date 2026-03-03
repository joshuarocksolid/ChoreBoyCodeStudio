"""Shared syntax-highlighting contracts and themed formatter helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from PySide2.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat

SyntaxPalette = dict[str, str]


@dataclass(frozen=True)
class TokenStyle:
    """Visual style for one token category."""

    palette_key: str
    bold: bool = False
    italic: bool = False


DEFAULT_LIGHT_PALETTE: SyntaxPalette = {
    "keyword": "#5B63FF",
    "builtin": "#0C8C64",
    "string": "#C73E0A",
    "comment": "#6C757D",
    "number": "#6741D9",
    "function": "#1C7ED6",
    "class": "#1864AB",
    "decorator": "#9C36B5",
    "operator": "#495057",
    "punctuation": "#495057",
    "parameter": "#2B8A3E",
    "json_key": "#1971C2",
    "json_literal": "#2B8A3E",
    "markdown_heading": "#0B7285",
    "markdown_emphasis": "#5F3DC4",
    "markdown_code": "#C73E0A",
    "semantic_function": "#1C7ED6",
    "semantic_class": "#1864AB",
    "semantic_parameter": "#2B8A3E",
    "semantic_import": "#9C36B5",
}
DEFAULT_DARK_PALETTE: SyntaxPalette = {
    "keyword": "#7EA8FF",
    "builtin": "#3CC68A",
    "string": "#FF8C5A",
    "comment": "#8B949E",
    "number": "#B18CFF",
    "function": "#79C0FF",
    "class": "#A5D6FF",
    "decorator": "#D2A8FF",
    "operator": "#C9D1D9",
    "punctuation": "#C9D1D9",
    "parameter": "#56D364",
    "json_key": "#6CB6FF",
    "json_literal": "#56D364",
    "markdown_heading": "#3BC9DB",
    "markdown_emphasis": "#B197FC",
    "markdown_code": "#FF8C5A",
    "semantic_function": "#79C0FF",
    "semantic_class": "#A5D6FF",
    "semantic_parameter": "#56D364",
    "semantic_import": "#D2A8FF",
}


def build_syntax_palette(*, is_dark: bool, overrides: Mapping[str, str] | None = None) -> SyntaxPalette:
    """Return merged syntax palette for the selected mode."""
    palette = dict(DEFAULT_DARK_PALETTE if is_dark else DEFAULT_LIGHT_PALETTE)
    if overrides:
        for key, value in overrides.items():
            if value:
                palette[key] = value
    return palette


class ThemedSyntaxHighlighter(QSyntaxHighlighter):
    """QSyntaxHighlighter with palette-aware token format management."""

    TOKEN_STYLES: Mapping[str, TokenStyle] = {}

    def __init__(
        self,
        document,  # type: ignore[no-untyped-def]
        *,
        is_dark: bool = False,
        syntax_palette: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(document)
        self._is_dark = is_dark
        self._palette: SyntaxPalette = build_syntax_palette(is_dark=is_dark, overrides=syntax_palette)
        self._formats: dict[str, QTextCharFormat] = {}
        self._rebuild_formats()

    def set_dark_mode(self, is_dark: bool) -> None:
        """Compatibility API used by existing editor theme application."""
        self.set_theme_palette(None, is_dark=is_dark)

    def set_theme_palette(
        self,
        syntax_palette: Mapping[str, str] | None,
        *,
        is_dark: bool | None = None,
    ) -> None:
        """Apply syntax palette overrides and trigger rehighlight when changed."""
        target_mode = self._is_dark if is_dark is None else is_dark
        palette = build_syntax_palette(is_dark=target_mode, overrides=syntax_palette)
        if target_mode == self._is_dark and palette == self._palette:
            return
        self._is_dark = target_mode
        self._palette = palette
        self._rebuild_formats()
        self.rehighlight()

    def _rebuild_formats(self) -> None:
        self._formats.clear()
        for token_name, style in self.TOKEN_STYLES.items():
            color_value = self._palette.get(style.palette_key)
            if color_value is None:
                continue
            text_format = QTextCharFormat()
            text_format.setForeground(QColor(color_value))
            if style.bold:
                text_format.setFontWeight(75)
            if style.italic:
                text_format.setFontItalic(True)
            self._formats[token_name] = text_format

    def _format(self, token_name: str) -> QTextCharFormat | None:
        return self._formats.get(token_name)
