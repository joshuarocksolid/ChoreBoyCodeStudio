"""Stateful Python syntax highlighting for code editor widget."""

from __future__ import annotations

import builtins
import keyword
import re
from collections.abc import Iterable, Mapping

from app.editors.syntax_engine import TokenStyle, ThemedSyntaxHighlighter

_LIGHT_COLORS = {
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
}
_DARK_COLORS = {
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
}

_STATE_NORMAL = 0
_STATE_TRIPLE_SINGLE = 1
_STATE_TRIPLE_DOUBLE = 2

_STRING_PREFIX_CHARS = frozenset("rRuUbBfF")
_BUILTIN_NAMES = frozenset(name for name in dir(builtins) if name and not name.startswith("_"))
_IDENTIFIER_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_FUNCTION_NAME_PATTERN = re.compile(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)")
_CLASS_NAME_PATTERN = re.compile(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)")
_DECORATOR_PATTERN = re.compile(r"^\s*@\s*[A-Za-z_][A-Za-z0-9_\.]*")
_PARAMETER_BLOCK_PATTERN = re.compile(r"\bdef\s+[A-Za-z_][A-Za-z0-9_]*\s*\((?P<params>[^)]*)\)")
_PARAMETER_NAME_PATTERN = re.compile(r"(?P<stars>\*{0,2})(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?=[:=,)]|$)")
_NUMBER_PATTERN = re.compile(
    r"(?<![\w.])(?:0[bB][01_]+|0[oO][0-7_]+|0[xX][0-9A-Fa-f_]+|\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d[\d_]*)?)(?![\w.])"
)
_OPERATOR_PATTERN = re.compile(r"==|!=|<=|>=|:=|<<|>>|//|\*\*|[-+/*%&|^~<>]=?|=")
_PUNCTUATION_PATTERN = re.compile(r"[()\[\]{}:.,;]")


class PythonSyntaxHighlighter(ThemedSyntaxHighlighter):
    """Stateful Python syntax highlighter with multiline string support."""

    TOKEN_STYLES = {
        "keyword": TokenStyle("keyword", bold=True),
        "builtin": TokenStyle("builtin"),
        "string": TokenStyle("string"),
        "comment": TokenStyle("comment", italic=True),
        "number": TokenStyle("number"),
        "function": TokenStyle("function", bold=True),
        "class": TokenStyle("class", bold=True),
        "decorator": TokenStyle("decorator"),
        "operator": TokenStyle("operator"),
        "punctuation": TokenStyle("punctuation"),
        "parameter": TokenStyle("parameter"),
    }

    def __init__(
        self,
        document,  # type: ignore[no-untyped-def]
        *,
        is_dark: bool = False,
        syntax_palette: Mapping[str, str] | None = None,
    ) -> None:
        overrides = self._build_palette_overrides(syntax_palette, is_dark)
        super().__init__(document, is_dark=is_dark, syntax_palette=overrides)

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
        self.setCurrentBlockState(_STATE_NORMAL)
        protected_spans: list[tuple[int, int]] = []
        scan_start = 0

        previous_state = self.previousBlockState()
        if previous_state in {_STATE_TRIPLE_SINGLE, _STATE_TRIPLE_DOUBLE}:
            delimiter = "'''" if previous_state == _STATE_TRIPLE_SINGLE else '"""'
            closing_index = text.find(delimiter)
            if closing_index < 0:
                self._apply_token(0, len(text), "string")
                self.setCurrentBlockState(previous_state)
                return
            segment_end = closing_index + len(delimiter)
            self._apply_token(0, segment_end, "string")
            protected_spans.append((0, segment_end))
            scan_start = segment_end

        scan_index = scan_start
        while scan_index < len(text):
            if text[scan_index] == "#":
                self._apply_token(scan_index, len(text), "comment")
                protected_spans.append((scan_index, len(text)))
                break

            literal_start = self._locate_string_start(text, scan_index)
            if literal_start is None:
                scan_index += 1
                continue

            literal_end, next_state = self._consume_string_literal(text, literal_start)
            self._apply_token(literal_start, literal_end, "string")
            protected_spans.append((literal_start, literal_end))
            if next_state is not None:
                self.setCurrentBlockState(next_state)
                break
            scan_index = max(literal_end, literal_start + 1)

        self._apply_simple_pattern(_PUNCTUATION_PATTERN, text, protected_spans, "punctuation")
        self._apply_simple_pattern(_OPERATOR_PATTERN, text, protected_spans, "operator")
        self._apply_simple_pattern(_NUMBER_PATTERN, text, protected_spans, "number")
        self._apply_identifier_tokens(text, protected_spans)
        self._apply_named_definition_tokens(_FUNCTION_NAME_PATTERN, text, protected_spans, "function")
        self._apply_named_definition_tokens(_CLASS_NAME_PATTERN, text, protected_spans, "class")
        self._apply_decorator_tokens(text, protected_spans)
        self._apply_parameter_tokens(text, protected_spans)

    def _apply_identifier_tokens(self, text: str, protected_spans: Iterable[tuple[int, int]]) -> None:
        for match in _IDENTIFIER_PATTERN.finditer(text):
            start, end = match.span()
            if self._intersects_protected(start, end, protected_spans):
                continue
            token_text = match.group(0)
            if keyword.iskeyword(token_text):
                self._apply_token(start, end, "keyword")
            elif token_text in _BUILTIN_NAMES:
                self._apply_token(start, end, "builtin")

    def _apply_named_definition_tokens(
        self,
        pattern: re.Pattern[str],
        text: str,
        protected_spans: Iterable[tuple[int, int]],
        token_name: str,
    ) -> None:
        for match in pattern.finditer(text):
            span = match.span(1)
            if self._intersects_protected(span[0], span[1], protected_spans):
                continue
            self._apply_token(span[0], span[1], token_name)

    def _apply_decorator_tokens(self, text: str, protected_spans: Iterable[tuple[int, int]]) -> None:
        match = _DECORATOR_PATTERN.search(text)
        if match is None:
            return
        start, end = match.span()
        if self._intersects_protected(start, end, protected_spans):
            return
        self._apply_token(start, end, "decorator")

    def _apply_parameter_tokens(self, text: str, protected_spans: Iterable[tuple[int, int]]) -> None:
        for block in _PARAMETER_BLOCK_PATTERN.finditer(text):
            params_text = block.group("params")
            params_start = block.start("params")
            for match in _PARAMETER_NAME_PATTERN.finditer(params_text):
                name = match.group("name")
                if name in {"self", "cls"} or keyword.iskeyword(name):
                    continue
                abs_start = params_start + match.start("name")
                abs_end = params_start + match.end("name")
                if self._intersects_protected(abs_start, abs_end, protected_spans):
                    continue
                self._apply_token(abs_start, abs_end, "parameter")

    def _apply_simple_pattern(
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

    def _locate_string_start(self, text: str, index: int) -> int | None:
        if index >= len(text):
            return None
        character = text[index]
        if character in {"'", '"'}:
            return index
        if character not in _STRING_PREFIX_CHARS:
            return None
        for prefix_length in range(1, 4):
            quote_index = index + prefix_length
            if quote_index >= len(text):
                return None
            prefix_text = text[index:quote_index]
            if any(ch not in _STRING_PREFIX_CHARS for ch in prefix_text):
                return None
            if text[quote_index] in {"'", '"'}:
                return index
        return None

    def _consume_string_literal(self, text: str, literal_start: int) -> tuple[int, int | None]:
        quote_index = literal_start
        while quote_index < len(text) and text[quote_index] in _STRING_PREFIX_CHARS:
            quote_index += 1
            if quote_index - literal_start >= 3:
                break

        if quote_index >= len(text) or text[quote_index] not in {"'", '"'}:
            quote_index = literal_start
            if quote_index >= len(text) or text[quote_index] not in {"'", '"'}:
                return (literal_start + 1, None)

        quote_char = text[quote_index]
        triple_delimiter = quote_char * 3
        if text[quote_index : quote_index + 3] == triple_delimiter:
            closing_index = text.find(triple_delimiter, quote_index + 3)
            if closing_index < 0:
                block_state = _STATE_TRIPLE_SINGLE if quote_char == "'" else _STATE_TRIPLE_DOUBLE
                return (len(text), block_state)
            return (closing_index + 3, None)

        cursor = quote_index + 1
        escaped = False
        while cursor < len(text):
            current = text[cursor]
            if current == quote_char and not escaped:
                return (cursor + 1, None)
            if current == "\\" and not escaped:
                escaped = True
            else:
                escaped = False
            cursor += 1
        return (len(text), None)

    @staticmethod
    def _intersects_protected(start: int, end: int, protected_spans: Iterable[tuple[int, int]]) -> bool:
        return any(start < protected_end and end > protected_start for protected_start, protected_end in protected_spans)
