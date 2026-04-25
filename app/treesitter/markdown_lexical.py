from __future__ import annotations

import re
from typing import Protocol, cast

from app.treesitter.capture_pipeline import _CaptureSpan

_MARKDOWN_ATX_HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s+.*$")
_MARKDOWN_LIST_MARKER_PATTERN = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")
_MARKDOWN_STRONG_PATTERN = re.compile(r"(?<!\*)\*\*([^*\n]+)\*\*(?!\*)")
_MARKDOWN_EMPHASIS_PATTERN = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_MARKDOWN_CODE_SPAN_PATTERN = re.compile(r"`[^`\n]+`")


class _MarkdownHost(Protocol):
    def _append_capture_span(
        self,
        *,
        spans_by_line: dict[int, list[_CaptureSpan]],
        seen_by_line: dict[int, dict[tuple[int, int], int]],
        line_number: int,
        span: _CaptureSpan,
    ) -> None: ...


def _host(instance: object) -> _MarkdownHost:
    return cast(_MarkdownHost, instance)


class TreeSitterMarkdownLexicalMixin:
    def _add_markdown_lexical_spans(
        self,
        *,
        lines: list[str],
        merged_ranges: list[tuple[int, int]],
        spans_by_line: dict[int, list[_CaptureSpan]],
        seen_by_line: dict[int, dict[tuple[int, int], int]],
    ) -> None:
        for start_line, end_line in merged_ranges:
            for line_number in range(start_line, end_line + 1):
                if line_number < 0 or line_number >= len(lines):
                    continue
                line_text = lines[line_number]
                if not line_text:
                    continue
                if _MARKDOWN_ATX_HEADING_PATTERN.match(line_text):
                    _host(self)._append_capture_span(
                        spans_by_line=spans_by_line,
                        seen_by_line=seen_by_line,
                        line_number=line_number,
                        span=_CaptureSpan(
                            token_name="markdown_heading",
                            start_col=0,
                            end_col=len(line_text),
                            capture_name="markdown.heading",
                            origin="markdown.lexical",
                        ),
                    )
                list_marker_match = _MARKDOWN_LIST_MARKER_PATTERN.match(line_text)
                if list_marker_match is not None:
                    marker_text = list_marker_match.group(0).rstrip()
                    marker_start = list_marker_match.start()
                    marker_end = marker_start + len(marker_text)
                    _host(self)._append_capture_span(
                        spans_by_line=spans_by_line,
                        seen_by_line=seen_by_line,
                        line_number=line_number,
                        span=_CaptureSpan(
                            token_name="punctuation",
                            start_col=marker_start,
                            end_col=marker_end,
                            capture_name="markdown.list_marker",
                            origin="markdown.lexical",
                        ),
                    )
                for pattern, token_name in (
                    (_MARKDOWN_CODE_SPAN_PATTERN, "markdown_code"),
                    (_MARKDOWN_STRONG_PATTERN, "markdown_strong"),
                    (_MARKDOWN_EMPHASIS_PATTERN, "markdown_emphasis"),
                ):
                    for match in pattern.finditer(line_text):
                        _host(self)._append_capture_span(
                            spans_by_line=spans_by_line,
                            seen_by_line=seen_by_line,
                            line_number=line_number,
                            span=_CaptureSpan(
                                token_name=token_name,
                                start_col=match.start(),
                                end_col=match.end(),
                                capture_name=token_name,
                                origin="markdown.lexical",
                            ),
                        )

