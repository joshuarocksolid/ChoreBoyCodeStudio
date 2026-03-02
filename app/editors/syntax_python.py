"""Basic Python syntax highlighting for code editor widget."""

from __future__ import annotations

import keyword
import re

from PySide2.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat

_LIGHT_COLORS = {
    "keyword": "#5B63FF",
    "builtin": "#0C8C64",
    "string": "#C73E0A",
    "comment": "#6C757D",
    "number": "#6741D9",
}
_DARK_COLORS = {
    "keyword": "#7EA8FF",
    "builtin": "#3CC68A",
    "string": "#FF8C5A",
    "comment": "#8B949E",
    "number": "#B18CFF",
}


class PythonSyntaxHighlighter(QSyntaxHighlighter):
    """Lightweight Python syntax highlighter."""

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

        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor(colors["keyword"]))
        keyword_format.setFontWeight(75)
        keywords_pattern = r"\b(" + "|".join(re.escape(word) for word in keyword.kwlist) + r")\b"
        self._rules.append((re.compile(keywords_pattern), keyword_format))

        builtin_format = QTextCharFormat()
        builtin_format.setForeground(QColor(colors["builtin"]))
        self._rules.append((re.compile(r"\b(print|len|range|dict|list|set|tuple|str|int|float|bool|Exception)\b"), builtin_format))

        string_format = QTextCharFormat()
        string_format.setForeground(QColor(colors["string"]))
        self._rules.append((re.compile(r"'[^'\\]*(?:\\.[^'\\]*)*'"), string_format))
        self._rules.append((re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"'), string_format))

        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor(colors["comment"]))
        self._rules.append((re.compile(r"#.*$"), comment_format))

        number_format = QTextCharFormat()
        number_format.setForeground(QColor(colors["number"]))
        self._rules.append((re.compile(r"\b\d+(\.\d+)?\b"), number_format))

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt API
        for pattern, text_format in self._rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), text_format)
