"""Stateful Python syntax highlighting for code editor widget."""

from __future__ import annotations

import builtins
import keyword
import re
from dataclasses import dataclass
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
_STATE_SIGNATURE_DEF = 3
_STATE_SIGNATURE_ASYNC_DEF = 4
_SIGNATURE_STATES = {_STATE_SIGNATURE_DEF, _STATE_SIGNATURE_ASYNC_DEF}

_STRING_PREFIX_CHARS = frozenset("rRuUbBfF")
_BUILTIN_NAMES = frozenset(name for name in dir(builtins) if name and not name.startswith("_"))
_IDENTIFIER_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_FUNCTION_NAME_PATTERN = re.compile(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)")
_CLASS_NAME_PATTERN = re.compile(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)")
_DECORATOR_PATTERN = re.compile(r"^\s*@\s*[A-Za-z_][A-Za-z0-9_\.]*(?:\([^#]*\))?")
_PARAMETER_NAME_PATTERN = re.compile(r"(?P<stars>\*{0,2})(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?=[:=,)]|$)")
_SIGNATURE_START_PATTERN = re.compile(r"^\s*(?:async\s+)?def\s+[A-Za-z_][A-Za-z0-9_]*\s*\(")
_ASYNC_SIGNATURE_START_PATTERN = re.compile(r"^\s*async\s+def\s+[A-Za-z_][A-Za-z0-9_]*\s*\(")
_SIGNATURE_END_PATTERN = re.compile(r"\)\s*(?:->\s*[^:]+)?\s*:")
_ANNOTATION_NAME_PATTERN = re.compile(r"(?:(?<=:)|(?<=->)|(?<=\[)|(?<=\|)|(?<=,))\s*([A-Za-z_][A-Za-z0-9_\.]*)")
_NUMBER_PATTERN = re.compile(
    r"(?<![\w.])(?:0[bB][01_]+|0[oO][0-7_]+|0[xX][0-9A-Fa-f_]+|\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d[\d_]*)?)(?![\w.])"
)
_OPERATOR_PATTERN = re.compile(r"==|!=|<=|>=|:=|<<|>>|//|\*\*|[-+/*%&|^~<>]=?|=")
_PUNCTUATION_PATTERN = re.compile(r"[()\[\]{}:.,;]")
_IS_SOFT_KEYWORD = getattr(keyword, "issoftkeyword", lambda _value: False)


@dataclass(frozen=True)
class _StringLiteralSpan:
    end: int
    next_state: int | None
    quote_index: int
    is_triple: bool
    is_fstring: bool


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

            literal = self._consume_string_literal(text, literal_start)
            self._apply_token(literal_start, literal.end, "string")
            if literal.is_fstring and literal.next_state is None:
                self._apply_fstring_expression_tokens(text, literal)
            protected_spans.append((literal_start, literal.end))
            if literal.next_state is not None:
                self.setCurrentBlockState(literal.next_state)
                break
            scan_index = max(literal.end, literal_start + 1)

        if self.currentBlockState() in {_STATE_TRIPLE_SINGLE, _STATE_TRIPLE_DOUBLE}:
            return

        self._apply_simple_pattern(_PUNCTUATION_PATTERN, text, protected_spans, "punctuation")
        self._apply_simple_pattern(_OPERATOR_PATTERN, text, protected_spans, "operator")
        self._apply_simple_pattern(_NUMBER_PATTERN, text, protected_spans, "number")
        self._apply_identifier_tokens(text, protected_spans)
        self._apply_named_definition_tokens(_FUNCTION_NAME_PATTERN, text, protected_spans, "function")
        self._apply_named_definition_tokens(_CLASS_NAME_PATTERN, text, protected_spans, "class")
        self._apply_decorator_tokens(text, protected_spans)
        self._apply_parameter_tokens(text, protected_spans, previous_state=previous_state)
        self._apply_annotation_tokens(text, protected_spans)

        if previous_state in _SIGNATURE_STATES:
            if not _SIGNATURE_END_PATTERN.search(text):
                self.setCurrentBlockState(previous_state)
            return
        if _SIGNATURE_START_PATTERN.search(text) and not _SIGNATURE_END_PATTERN.search(text):
            if _ASYNC_SIGNATURE_START_PATTERN.search(text):
                self.setCurrentBlockState(_STATE_SIGNATURE_ASYNC_DEF)
            else:
                self.setCurrentBlockState(_STATE_SIGNATURE_DEF)

    def _apply_identifier_tokens(self, text: str, protected_spans: Iterable[tuple[int, int]]) -> None:
        for match in _IDENTIFIER_PATTERN.finditer(text):
            start, end = match.span()
            if self._intersects_protected(start, end, protected_spans):
                continue
            token_text = match.group(0)
            if keyword.iskeyword(token_text) or _IS_SOFT_KEYWORD(token_text):
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

    def _apply_parameter_tokens(
        self,
        text: str,
        protected_spans: Iterable[tuple[int, int]],
        *,
        previous_state: int,
    ) -> None:
        for segment_start, segment_end in self._iter_parameter_segments(text, previous_state=previous_state):
            if segment_end <= segment_start:
                continue
            params_text = text[segment_start:segment_end]
            for match in _PARAMETER_NAME_PATTERN.finditer(params_text):
                name = match.group("name")
                if name in {"self", "cls"} or keyword.iskeyword(name) or _IS_SOFT_KEYWORD(name):
                    continue
                abs_start = segment_start + match.start("name")
                abs_end = segment_start + match.end("name")
                if self._intersects_protected(abs_start, abs_end, protected_spans):
                    continue
                self._apply_token(abs_start, abs_end, "parameter")

    def _apply_annotation_tokens(self, text: str, protected_spans: Iterable[tuple[int, int]]) -> None:
        for match in _ANNOTATION_NAME_PATTERN.finditer(text):
            start, end = match.span(1)
            if self._intersects_protected(start, end, protected_spans):
                continue
            self._apply_token(start, end, "class")

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

    def _consume_string_literal(self, text: str, literal_start: int) -> _StringLiteralSpan:
        quote_index = literal_start
        while quote_index < len(text) and text[quote_index] in _STRING_PREFIX_CHARS:
            quote_index += 1
            if quote_index - literal_start >= 3:
                break

        prefix_text = text[literal_start:quote_index]
        is_fstring = "f" in prefix_text.lower()

        if quote_index >= len(text) or text[quote_index] not in {"'", '"'}:
            quote_index = literal_start
            if quote_index >= len(text) or text[quote_index] not in {"'", '"'}:
                return _StringLiteralSpan(
                    end=literal_start + 1,
                    next_state=None,
                    quote_index=literal_start,
                    is_triple=False,
                    is_fstring=False,
                )

        quote_char = text[quote_index]
        triple_delimiter = quote_char * 3
        if text[quote_index : quote_index + 3] == triple_delimiter:
            closing_index = text.find(triple_delimiter, quote_index + 3)
            if closing_index < 0:
                block_state = _STATE_TRIPLE_SINGLE if quote_char == "'" else _STATE_TRIPLE_DOUBLE
                return _StringLiteralSpan(
                    end=len(text),
                    next_state=block_state,
                    quote_index=quote_index,
                    is_triple=True,
                    is_fstring=is_fstring,
                )
            return _StringLiteralSpan(
                end=closing_index + 3,
                next_state=None,
                quote_index=quote_index,
                is_triple=True,
                is_fstring=is_fstring,
            )

        cursor = quote_index + 1
        escaped = False
        while cursor < len(text):
            current = text[cursor]
            if current == quote_char and not escaped:
                return _StringLiteralSpan(
                    end=cursor + 1,
                    next_state=None,
                    quote_index=quote_index,
                    is_triple=False,
                    is_fstring=is_fstring,
                )
            if current == "\\" and not escaped:
                escaped = True
            else:
                escaped = False
            cursor += 1
        return _StringLiteralSpan(
            end=len(text),
            next_state=None,
            quote_index=quote_index,
            is_triple=False,
            is_fstring=is_fstring,
        )

    def _iter_parameter_segments(self, text: str, *, previous_state: int) -> list[tuple[int, int]]:
        if "(" not in text and previous_state not in _SIGNATURE_STATES:
            return []

        segments: list[tuple[int, int]] = []
        if _SIGNATURE_START_PATTERN.search(text):
            start_index = text.find("(")
            if start_index < 0:
                return []
            end_index = text.find(")", start_index + 1)
            if end_index < 0:
                segments.append((start_index + 1, len(text)))
            else:
                segments.append((start_index + 1, end_index))
            return segments

        if previous_state in _SIGNATURE_STATES:
            end_index = text.find(")")
            if end_index < 0:
                segments.append((0, len(text)))
            else:
                segments.append((0, end_index))
        return segments

    def _apply_fstring_expression_tokens(self, text: str, literal: _StringLiteralSpan) -> None:
        if literal.end <= literal.quote_index:
            return
        quote_width = 3 if literal.is_triple else 1
        content_start = literal.quote_index + quote_width
        content_end = literal.end - quote_width
        if content_end <= content_start:
            return

        cursor = content_start
        while cursor < content_end:
            char = text[cursor]
            if char == "{":
                if cursor + 1 < content_end and text[cursor + 1] == "{":
                    cursor += 2
                    continue
                end_index = self._find_fstring_expression_end(text, cursor + 1, content_end)
                if end_index is None:
                    break
                self._apply_token(cursor, cursor + 1, "punctuation")
                self._apply_token(end_index, end_index + 1, "punctuation")
                self._apply_expression_segment_tokens(text, cursor + 1, end_index)
                cursor = end_index + 1
                continue
            if char == "}" and cursor + 1 < content_end and text[cursor + 1] == "}":
                cursor += 2
                continue
            cursor += 1

    def _find_fstring_expression_end(self, text: str, start: int, limit: int) -> int | None:
        depth = 0
        index = start
        while index < limit:
            current = text[index]
            if current == "{":
                depth += 1
            elif current == "}":
                if depth == 0:
                    return index
                depth -= 1
            index += 1
        return None

    def _apply_expression_segment_tokens(self, text: str, start: int, end: int) -> None:
        if end <= start:
            return
        segment = text[start:end]
        for pattern, token_name in (
            (_PUNCTUATION_PATTERN, "punctuation"),
            (_OPERATOR_PATTERN, "operator"),
            (_NUMBER_PATTERN, "number"),
        ):
            for match in pattern.finditer(segment):
                abs_start = start + match.start()
                abs_end = start + match.end()
                self._apply_token(abs_start, abs_end, token_name)

        for match in _IDENTIFIER_PATTERN.finditer(segment):
            token_text = match.group(0)
            abs_start = start + match.start()
            abs_end = start + match.end()
            if keyword.iskeyword(token_text) or _IS_SOFT_KEYWORD(token_text):
                self._apply_token(abs_start, abs_end, "keyword")
            elif token_text in _BUILTIN_NAMES:
                self._apply_token(abs_start, abs_end, "builtin")

    @staticmethod
    def _intersects_protected(start: int, end: int, protected_spans: Iterable[tuple[int, int]]) -> bool:
        return any(start < protected_end and end > protected_start for protected_start, protected_end in protected_spans)
