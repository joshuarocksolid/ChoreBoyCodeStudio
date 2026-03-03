"""JSON syntax highlighter for code editor widget."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from app.editors.syntax_engine import TokenStyle, ThemedSyntaxHighlighter

_LIGHT_COLORS = {
    "json_key": "#1971C2",
    "string": "#C73E0A",
    "json_literal": "#2B8A3E",
    "number": "#6741D9",
    "punctuation": "#495057",
}
_DARK_COLORS = {
    "json_key": "#6CB6FF",
    "string": "#FF8C5A",
    "json_literal": "#56D364",
    "number": "#B18CFF",
    "punctuation": "#C9D1D9",
}

_LITERAL_PATTERN = re.compile(r"\b(?:true|false|null)\b")
_NUMBER_PATTERN = re.compile(r"(?<![\w.])-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?(?![\w.])")
_PUNCTUATION_PATTERN = re.compile(r"[{}\[\]:,]")


class JsonSyntaxHighlighter(ThemedSyntaxHighlighter):
    """JSON highlighter with key/value precedence and escaped-string handling."""

    TOKEN_STYLES = {
        "key": TokenStyle("json_key", bold=True),
        "string": TokenStyle("string"),
        "literal": TokenStyle("json_literal"),
        "number": TokenStyle("number"),
        "punctuation": TokenStyle("punctuation"),
    }

    def __init__(
        self,
        document,  # type: ignore[no-untyped-def]
        *,
        is_dark: bool = False,
        syntax_palette: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(document, is_dark=is_dark, syntax_palette=self._build_palette_overrides(syntax_palette, is_dark))

    def set_theme_palette(
        self,
        syntax_palette: Mapping[str, str] | None,
        *,
        is_dark: bool | None = None,
    ) -> None:
        target_mode = self._is_dark if is_dark is None else is_dark
        super().set_theme_palette(self._build_palette_overrides(syntax_palette, target_mode), is_dark=target_mode)

    def _build_palette_overrides(self, syntax_palette: Mapping[str, str] | None, is_dark: bool) -> dict[str, str]:
        base = dict(_DARK_COLORS if is_dark else _LIGHT_COLORS)
        if syntax_palette:
            for key in base:
                override = syntax_palette.get(key)
                if override:
                    base[key] = override
        return base

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt API
        string_spans = self._highlight_string_tokens(text)
        self._apply_pattern(_PUNCTUATION_PATTERN, text, string_spans, "punctuation")
        self._apply_pattern(_LITERAL_PATTERN, text, string_spans, "literal")
        self._apply_pattern(_NUMBER_PATTERN, text, string_spans, "number")

    def _highlight_string_tokens(self, text: str) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        index = 0
        while index < len(text):
            if text[index] != '"':
                index += 1
                continue
            start = index
            index += 1
            escaped = False
            while index < len(text):
                current = text[index]
                if current == '"' and not escaped:
                    index += 1
                    break
                if current == "\\" and not escaped:
                    escaped = True
                else:
                    escaped = False
                index += 1
            end = index
            spans.append((start, end))
            token_name = "key" if self._is_key_token(text, end) else "string"
            self._apply_token(start, end, token_name)
        return spans

    def _is_key_token(self, text: str, token_end: int) -> bool:
        cursor = token_end
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        return cursor < len(text) and text[cursor] == ":"

    def _apply_pattern(
        self,
        pattern: re.Pattern[str],
        text: str,
        protected_spans: Iterable[tuple[int, int]],
        token_name: str,
    ) -> None:
        for match in pattern.finditer(text):
            start, end = match.span()
            if self._intersects_protected(start, end, protected_spans):
                continue
            self._apply_token(start, end, token_name)

    def _apply_token(self, start: int, end: int, token_name: str) -> None:
        if end <= start:
            return
        fmt = self._format(token_name)
        if fmt is None:
            return
        self.setFormat(start, end - start, fmt)

    @staticmethod
    def _intersects_protected(start: int, end: int, protected_spans: Iterable[tuple[int, int]]) -> bool:
        return any(start < protected_end and end > protected_start for protected_start, protected_end in protected_spans)
