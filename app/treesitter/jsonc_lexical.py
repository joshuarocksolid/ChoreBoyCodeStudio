from __future__ import annotations

from typing import Protocol, cast

from app.treesitter.capture_pipeline import _CaptureSpan


class _JsoncHost(Protocol):
    def _append_capture_span(
        self,
        *,
        spans_by_line: dict[int, list[_CaptureSpan]],
        seen_by_line: dict[int, dict[tuple[int, int], int]],
        line_number: int,
        span: _CaptureSpan,
    ) -> None: ...


def _host(instance: object) -> _JsoncHost:
    return cast(_JsoncHost, instance)


class TreeSitterJsoncLexicalMixin:
    def _add_jsonc_comment_spans(
        self,
        *,
        lines: list[str],
        merged_ranges: list[tuple[int, int]],
        spans_by_line: dict[int, list[_CaptureSpan]],
        seen_by_line: dict[int, dict[tuple[int, int], int]],
    ) -> None:
        """Color `//` and `/* */` comments in JSON5/JSONC files.

        Tree-sitter-json does not parse comments, so without this lexical pass
        commented JSONC/JSON5 files lose comment coloring entirely.
        """
        if not lines:
            return
        full_text = "\n".join(lines)
        line_starts: list[int] = []
        offset = 0
        for line in lines:
            line_starts.append(offset)
            offset += len(line) + 1

        def add_span(start_offset: int, end_offset: int) -> None:
            for line_number, line_text in enumerate(lines):
                line_start = line_starts[line_number]
                line_end = line_start + len(line_text)
                if end_offset <= line_start or start_offset >= line_end:
                    continue
                start_col = max(0, start_offset - line_start)
                end_col = min(len(line_text), end_offset - line_start)
                if end_col <= start_col:
                    continue
                _host(self)._append_capture_span(
                    spans_by_line=spans_by_line,
                    seen_by_line=seen_by_line,
                    line_number=line_number,
                    span=_CaptureSpan(
                        token_name="comment",
                        start_col=start_col,
                        end_col=end_col,
                        capture_name="comment",
                        origin="jsonc.lexical",
                    ),
                )

        for start_offset, end_offset in self._scan_jsonc_comment_ranges(full_text):
            add_span(start_offset, end_offset)

    @staticmethod
    def _scan_jsonc_comment_ranges(source: str) -> list[tuple[int, int]]:
        """Walk source character-by-character to find // and /* */ comments outside strings."""
        ranges: list[tuple[int, int]] = []
        index = 0
        length = len(source)
        while index < length:
            character = source[index]
            if character == '"':
                index += 1
                while index < length:
                    if source[index] == "\\" and index + 1 < length:
                        index += 2
                        continue
                    if source[index] == '"':
                        index += 1
                        break
                    index += 1
                continue
            if character == "/" and index + 1 < length:
                next_character = source[index + 1]
                if next_character == "/":
                    end = source.find("\n", index + 2)
                    if end == -1:
                        end = length
                    ranges.append((index, end))
                    index = end
                    continue
                if next_character == "*":
                    end = source.find("*/", index + 2)
                    if end == -1:
                        end = length
                    else:
                        end += 2
                    ranges.append((index, end))
                    index = end
                    continue
            index += 1
        return ranges
