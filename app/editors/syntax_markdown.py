"""Markdown syntax highlighter for code editor widget."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from app.editors.syntax_engine import TokenStyle, ThemedSyntaxHighlighter

_LIGHT_COLORS = {
    "markdown_heading": "#0B7285",
    "markdown_emphasis": "#5F3DC4",
    "markdown_code": "#C73E0A",
}
_DARK_COLORS = {
    "markdown_heading": "#3BC9DB",
    "markdown_emphasis": "#B197FC",
    "markdown_code": "#FF8C5A",
}

_STATE_NORMAL = 0
_STATE_FENCE_BACKTICK_BASE = 1000
_STATE_FENCE_TILDE_BASE = 2000
_MAX_FENCE_LENGTH = 120
_HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s+.+$")
_SETEXT_UNDERLINE_PATTERN = re.compile(r"^\s{0,3}(=+|-+)\s*$")
_FENCE_OPEN_PATTERN = re.compile(r"^\s{0,3}(?P<marker>`{3,}|~{3,})(?P<info>.*)$")
_LIST_PREFIX_PATTERN = re.compile(r"^\s{0,3}(?:>\s?|[-+*]\s+|\d+[.)]\s+|\[[ xX]\]\s+)")
_LINK_PATTERN = re.compile(r"\[[^\]\n]+\]\([^) \n]+(?:\s+\"[^\"]*\")?\)")
_STRIKETHROUGH_PATTERN = re.compile(r"~~[^~\n][^~\n]*~~")
_EMPHASIS_PATTERNS = [
    re.compile(r"\*\*[^*\n]+\*\*"),
    re.compile(r"__[^_\n]+__"),
    re.compile(r"\*[^*\n]+\*"),
    re.compile(r"_[^_\n]+_"),
]


class MarkdownSyntaxHighlighter(ThemedSyntaxHighlighter):
    """Markdown highlighter with fenced-code block state support."""

    TOKEN_STYLES = {
        "heading": TokenStyle("markdown_heading", bold=True),
        "emphasis": TokenStyle("markdown_emphasis"),
        "code": TokenStyle("markdown_code"),
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
        self.setCurrentBlockState(_STATE_NORMAL)
        previous_state = self.previousBlockState()

        previous_fence = self._decode_fence_state(previous_state)
        if previous_fence is not None:
            self._apply_token(0, len(text), "code")
            if self._is_matching_closing_fence(
                text,
                marker_char=previous_fence[0],
                minimum_length=previous_fence[1],
            ):
                self.setCurrentBlockState(_STATE_NORMAL)
            else:
                self.setCurrentBlockState(previous_state)
            return

        opening_fence = self._match_opening_fence(text)
        if opening_fence is not None:
            self._apply_token(0, len(text), "code")
            marker_char, marker_length, info_text = opening_fence
            info_match = re.search(r"[A-Za-z0-9_+-]+", info_text)
            if info_match is not None:
                info_offset = len(text) - len(info_text)
                self._apply_token(
                    info_offset + info_match.start(),
                    info_offset + info_match.end(),
                    "emphasis",
                )
            self.setCurrentBlockState(self._encode_fence_state(marker_char=marker_char, marker_length=marker_length))
            return

        if _HEADING_PATTERN.match(text) or _SETEXT_UNDERLINE_PATTERN.match(text):
            self._apply_token(0, len(text), "heading")

        list_prefix_match = _LIST_PREFIX_PATTERN.match(text)
        if list_prefix_match is not None:
            self._apply_token(0, list_prefix_match.end(), "heading")

        code_spans = self._highlight_inline_code_spans(text)
        protected_spans = list(code_spans)

        link_spans = self._apply_pattern(_LINK_PATTERN, text, protected_spans, "emphasis")
        protected_spans.extend(link_spans)
        strike_spans = self._apply_pattern(_STRIKETHROUGH_PATTERN, text, protected_spans, "emphasis")
        protected_spans.extend(strike_spans)
        for pattern in _EMPHASIS_PATTERNS:
            pattern_spans = self._apply_pattern(pattern, text, protected_spans, "emphasis")
            protected_spans.extend(pattern_spans)

    def _apply_pattern(
        self,
        pattern: re.Pattern[str],
        text: str,
        protected_spans: Iterable[tuple[int, int]],
        token_name: str,
    ) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        for match in pattern.finditer(text):
            start, end = match.span()
            if self._intersects_protected(start, end, protected_spans):
                continue
            self._apply_token(start, end, token_name)
            spans.append((start, end))
        return spans

    def _highlight_inline_code_spans(self, text: str) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        cursor = 0
        while cursor < len(text):
            if text[cursor] != "`":
                cursor += 1
                continue
            marker_start = cursor
            while cursor < len(text) and text[cursor] == "`":
                cursor += 1
            marker_length = cursor - marker_start
            if marker_length <= 0:
                continue
            close_start = self._find_matching_backtick_run(text, start=cursor, marker_length=marker_length)
            if close_start is None:
                continue
            close_end = close_start + marker_length
            self._apply_token(marker_start, close_end, "code")
            spans.append((marker_start, close_end))
            cursor = close_end
        return spans

    @staticmethod
    def _find_matching_backtick_run(text: str, *, start: int, marker_length: int) -> int | None:
        cursor = start
        while cursor < len(text):
            if text[cursor] != "`":
                cursor += 1
                continue
            run_start = cursor
            while cursor < len(text) and text[cursor] == "`":
                cursor += 1
            if cursor - run_start == marker_length:
                return run_start
        return None

    def _match_opening_fence(self, text: str) -> tuple[str, int, str] | None:
        match = _FENCE_OPEN_PATTERN.match(text)
        if match is None:
            return None
        marker = match.group("marker")
        marker_char = marker[0]
        marker_length = len(marker)
        if marker_char == "`" and "`" in match.group("info"):
            return None
        return (marker_char, marker_length, match.group("info"))

    @staticmethod
    def _encode_fence_state(*, marker_char: str, marker_length: int) -> int:
        length = min(_MAX_FENCE_LENGTH, max(3, marker_length))
        if marker_char == "~":
            return _STATE_FENCE_TILDE_BASE + length
        return _STATE_FENCE_BACKTICK_BASE + length

    @staticmethod
    def _decode_fence_state(state: int) -> tuple[str, int] | None:
        if _STATE_FENCE_BACKTICK_BASE <= state < _STATE_FENCE_BACKTICK_BASE + _MAX_FENCE_LENGTH + 1:
            return ("`", state - _STATE_FENCE_BACKTICK_BASE)
        if _STATE_FENCE_TILDE_BASE <= state < _STATE_FENCE_TILDE_BASE + _MAX_FENCE_LENGTH + 1:
            return ("~", state - _STATE_FENCE_TILDE_BASE)
        return None

    @staticmethod
    def _is_matching_closing_fence(text: str, *, marker_char: str, minimum_length: int) -> bool:
        stripped = text.strip()
        if len(stripped) < minimum_length:
            return False
        if not stripped or any(ch != marker_char for ch in stripped):
            return False
        return len(stripped) >= minimum_length

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
