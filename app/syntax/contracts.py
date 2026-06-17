"""Shared syntax highlighter contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from PySide2.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat

from app.syntax.palette import SyntaxPalette, build_syntax_palette


@dataclass(frozen=True)
class TokenStyle:
    """Visual style for one token category."""

    palette_key: str
    bold: bool = False
    italic: bool = False


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


__all__ = ["TokenStyle", "ThemedSyntaxHighlighter"]
