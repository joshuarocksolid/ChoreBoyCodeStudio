"""JSON syntax highlighter for code editor widget."""

from __future__ import annotations

import re

from PySide2.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat


class JsonSyntaxHighlighter(QSyntaxHighlighter):
    """Lightweight JSON syntax highlighter."""

    def __init__(self, document) -> None:  # type: ignore[no-untyped-def]
        super().__init__(document)
        self._rules: list[tuple[re.Pattern[str], QTextCharFormat]] = []
        self._build_rules()

    def _build_rules(self) -> None:
        key_format = QTextCharFormat()
        key_format.setForeground(QColor("#1971C2"))
        key_format.setFontWeight(75)
        self._rules.append((re.compile(r'"[^"]*"\s*:'), key_format))

        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#D9480F"))
        self._rules.append((re.compile(r'"[^"]*"'), string_format))

        literal_format = QTextCharFormat()
        literal_format.setForeground(QColor("#2B8A3E"))
        self._rules.append((re.compile(r"\b(true|false|null)\b"), literal_format))

        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#6741D9"))
        self._rules.append((re.compile(r"\b-?\d+(\.\d+)?([eE][+-]?\d+)?\b"), number_format))

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt API
        for pattern, text_format in self._rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), text_format)
