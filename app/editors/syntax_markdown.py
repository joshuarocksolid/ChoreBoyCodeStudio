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
_STATE_CODE_FENCE = 1
_HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s.+$")
_FENCE_PATTERN = re.compile(r"^\s*(```|~~~)")
_INLINE_CODE_PATTERN = re.compile(r"`[^`]+`")
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

        if previous_state == _STATE_CODE_FENCE:
            self._apply_token(0, len(text), "code")
            if _FENCE_PATTERN.match(text):
                self.setCurrentBlockState(_STATE_NORMAL)
            else:
                self.setCurrentBlockState(_STATE_CODE_FENCE)
            return

        if _FENCE_PATTERN.match(text):
            self._apply_token(0, len(text), "code")
            self.setCurrentBlockState(_STATE_CODE_FENCE)
            return

        if _HEADING_PATTERN.match(text):
            self._apply_token(0, len(text), "heading")

        code_spans = self._apply_pattern(_INLINE_CODE_PATTERN, text, [], "code")
        for pattern in _EMPHASIS_PATTERNS:
            self._apply_pattern(pattern, text, code_spans, "emphasis")

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
