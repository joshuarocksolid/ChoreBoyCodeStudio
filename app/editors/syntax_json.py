"""JSON syntax highlighter for code editor widget."""

from __future__ import annotations

import re

from PySide2.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat

_LIGHT_COLORS = {
    "key": "#1971C2",
    "string": "#C73E0A",
    "literal": "#2B8A3E",
    "number": "#6741D9",
}
_DARK_COLORS = {
    "key": "#6CB6FF",
    "string": "#FF8C5A",
    "literal": "#56D364",
    "number": "#B18CFF",
}


class JsonSyntaxHighlighter(QSyntaxHighlighter):
    """Lightweight JSON syntax highlighter."""

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

        key_format = QTextCharFormat()
        key_format.setForeground(QColor(colors["key"]))
        key_format.setFontWeight(75)
        self._rules.append((re.compile(r'"[^"]*"\s*:'), key_format))

        string_format = QTextCharFormat()
        string_format.setForeground(QColor(colors["string"]))
        self._rules.append((re.compile(r'"[^"]*"'), string_format))

        literal_format = QTextCharFormat()
        literal_format.setForeground(QColor(colors["literal"]))
        self._rules.append((re.compile(r"\b(true|false|null)\b"), literal_format))

        number_format = QTextCharFormat()
        number_format.setForeground(QColor(colors["number"]))
        self._rules.append((re.compile(r"\b-?\d+(\.\d+)?([eE][+-]?\d+)?\b"), number_format))

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt API
        for pattern, text_format in self._rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), text_format)
