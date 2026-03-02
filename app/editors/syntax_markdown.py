"""Markdown syntax highlighter for code editor widget."""

from __future__ import annotations

import re

from PySide2.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat

_LIGHT_COLORS = {
    "heading": "#0B7285",
    "emphasis": "#5F3DC4",
    "code": "#C73E0A",
}
_DARK_COLORS = {
    "heading": "#3BC9DB",
    "emphasis": "#B197FC",
    "code": "#FF8C5A",
}


class MarkdownSyntaxHighlighter(QSyntaxHighlighter):
    """Lightweight Markdown syntax highlighter."""

    def __init__(self, document, *, is_dark: bool = False) -> None:  # type: ignore[no-untyped-def]
        super().__init__(document)
        self._is_dark = is_dark
        self._rules: list[tuple[re.Pattern[str], QTextCharFormat]] = []
        self._build_rules()

    def set_dark_mode(self, is_dark: bool) -> None:
        if is_dark == self._is_dark:
            return
        self._is_dark = is_dark
        self._rules.clear()
        self._build_rules()
        self.rehighlight()

    def _build_rules(self) -> None:
        colors = _DARK_COLORS if self._is_dark else _LIGHT_COLORS

        heading_format = QTextCharFormat()
        heading_format.setForeground(QColor(colors["heading"]))
        heading_format.setFontWeight(75)
        self._rules.append((re.compile(r"^\s{0,3}#{1,6}\s.+$"), heading_format))

        emphasis_format = QTextCharFormat()
        emphasis_format.setForeground(QColor(colors["emphasis"]))
        self._rules.append((re.compile(r"\*\*[^*]+\*\*"), emphasis_format))
        self._rules.append((re.compile(r"_[^_]+_"), emphasis_format))

        code_format = QTextCharFormat()
        code_format.setForeground(QColor(colors["code"]))
        self._rules.append((re.compile(r"`[^`]+`"), code_format))
        self._rules.append((re.compile(r"^```.*$"), code_format))

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt API
        for pattern, text_format in self._rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), text_format)
