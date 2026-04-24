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
    "keyword": "#0000FF",
    "keyword_control": "#AF00DB",
    "keyword_import": "#AF00DB",
    "keyword_operator": "#AF00DB",
    "builtin": "#267F99",
    "escape": "#EE0000",
    "string": "#A31515",
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

    def set_dark_mode(self, is_dark: bool, *, rehighlight: bool = True) -> None:
        """Compatibility API used by existing editor theme application."""
        self.set_theme_palette(None, is_dark=is_dark, rehighlight=rehighlight)

    def set_theme_palette(
        self,
        syntax_palette: Mapping[str, str] | None,
        *,
        is_dark: bool | None = None,
        rehighlight: bool = True,
    ) -> None:
        """Apply syntax palette overrides and trigger rehighlight when changed."""
        target_mode = self._is_dark if is_dark is None else is_dark
        palette = build_syntax_palette(is_dark=target_mode, overrides=syntax_palette)
        if target_mode == self._is_dark and palette == self._palette:
            return
        self._is_dark = target_mode
        self._palette = palette
        self._rebuild_formats()
        if rehighlight:
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
