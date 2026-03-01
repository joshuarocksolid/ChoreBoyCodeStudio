"""Markdown syntax highlighter for code editor widget."""

from __future__ import annotations

import re

from PySide2.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat


class MarkdownSyntaxHighlighter(QSyntaxHighlighter):
    """Lightweight Markdown syntax highlighter."""

    def __init__(self, document) -> None:  # type: ignore[no-untyped-def]
        super().__init__(document)
        self._rules: list[tuple[re.Pattern[str], QTextCharFormat]] = []
        self._build_rules()

    def _build_rules(self) -> None:
        heading_format = QTextCharFormat()
        heading_format.setForeground(QColor("#0B7285"))
        heading_format.setFontWeight(75)
        self._rules.append((re.compile(r"^\s{0,3}#{1,6}\s.+$"), heading_format))

        emphasis_format = QTextCharFormat()
        emphasis_format.setForeground(QColor("#5F3DC4"))
        self._rules.append((re.compile(r"\*\*[^*]+\*\*"), emphasis_format))
        self._rules.append((re.compile(r"_[^_]+_"), emphasis_format))

        code_format = QTextCharFormat()
        code_format.setForeground(QColor("#E8590C"))
        self._rules.append((re.compile(r"`[^`]+`"), code_format))
        self._rules.append((re.compile(r"^```.*$"), code_format))

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt API
        for pattern, text_format in self._rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), text_format)
