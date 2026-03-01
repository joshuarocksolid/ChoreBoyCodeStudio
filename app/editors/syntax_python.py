"""Basic Python syntax highlighting for code editor widget."""

from __future__ import annotations

import keyword
import re

from PySide2.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat


class PythonSyntaxHighlighter(QSyntaxHighlighter):
    """Lightweight Python syntax highlighter."""

    def __init__(self, document) -> None:  # type: ignore[no-untyped-def]
        super().__init__(document)
        self._rules: list[tuple[re.Pattern[str], QTextCharFormat]] = []
        self._build_rules()

    def _build_rules(self) -> None:
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#5B8CFF"))
        keyword_format.setFontWeight(75)
        keywords_pattern = r"\b(" + "|".join(re.escape(word) for word in keyword.kwlist) + r")\b"
        self._rules.append((re.compile(keywords_pattern), keyword_format))

        builtin_format = QTextCharFormat()
        builtin_format.setForeground(QColor("#0CA678"))
        self._rules.append((re.compile(r"\b(print|len|range|dict|list|set|tuple|str|int|float|bool|Exception)\b"), builtin_format))

        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#D9480F"))
        self._rules.append((re.compile(r"'[^'\\]*(?:\\.[^'\\]*)*'"), string_format))
        self._rules.append((re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"'), string_format))

        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#868E96"))
        self._rules.append((re.compile(r"#.*$"), comment_format))

        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#6741D9"))
        self._rules.append((re.compile(r"\b\d+(\.\d+)?\b"), number_format))

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt API
        for pattern, text_format in self._rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), text_format)
