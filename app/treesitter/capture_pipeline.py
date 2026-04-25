from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterator, Protocol, cast

from app.core import constants
from app.treesitter.python_tokens import PYTHON_BUILTIN_FUNCTIONS, PYTHON_SPECIAL_VARIABLES

_QUERY_MARGIN_LINES = 220
_RANGE_EXPANSION_LINES = 3
_ESCAPE_SEQUENCE_PATTERN = re.compile(r"\\(?:[0-7]{1,3}|x[0-9A-Fa-f]{1,2}|u[0-9A-Fa-f]{1,4}|U[0-9A-Fa-f]{1,8}|N\{[^}\n]*\}|.)")


class _HighlighterHost(Protocol):
    _source_text: str
    _parser: Any
    _tree: Any | None
    _query: Any | None
    _query_supports_range_kwargs: bool | None
    _language_key: str
    _viewport_lines: tuple[int, int]

    def document(self) -> Any | None: ...
    def _effective_mode(self) -> str: ...
    def _query_capture_ranges(self, line_ranges: list[tuple[int, int]]) -> dict[int, list["_CaptureSpan"]]: ...
    def _query_window_for_large_modes(self, line_count: int) -> tuple[int, int] | None: ...
    def _resolve_token_name(self, capture_name: str) -> str | None: ...
    def _add_local_semantic_spans(
        self,
        *,
        lines: list[str],
        merged_ranges: list[tuple[int, int]],
        spans_by_line: dict[int, list["_CaptureSpan"]],
        seen_by_line: dict[int, dict[tuple[int, int], int]],
    ) -> None: ...
    def _add_markdown_lexical_spans(
        self,
        *,
        lines: list[str],
        merged_ranges: list[tuple[int, int]],
        spans_by_line: dict[int, list["_CaptureSpan"]],
        seen_by_line: dict[int, dict[tuple[int, int], int]],
    ) -> None: ...
    def _add_jsonc_comment_spans(
        self,
        *,
        lines: list[str],
        merged_ranges: list[tuple[int, int]],
        spans_by_line: dict[int, list["_CaptureSpan"]],
        seen_by_line: dict[int, dict[tuple[int, int], int]],
    ) -> None: ...
    def _add_injection_spans(
        self,
        *,
        lines: list[str],
        merged_ranges: list[tuple[int, int]],
        spans_by_line: dict[int, list["_CaptureSpan"]],
        seen_by_line: dict[int, dict[tuple[int, int], int]],
    ) -> None: ...


def _host(instance: object) -> _HighlighterHost:
    return cast(_HighlighterHost, instance)

_CAPTURE_TOKEN_MAP: dict[str, str] = {
    "keyword": "keyword",
    "keyword.control": "keyword_control",
    "keyword.import": "keyword_import",
    "keyword.operator": "keyword_operator",
    "escape": "escape",
    "comment": "comment",
    "string": "string",
    "number": "number",
    "boolean": "number",
    "constant": "semantic_constant",
    "constant.builtin": "semantic_constant",
    "constructor": "semantic_class",
    "type": "semantic_class",
    "function.def": "function",
    "function.call": "semantic_function",
    "function.builtin": "builtin",
    "method.call": "semantic_method",
    "class.def": "class",
    "import.symbol": "semantic_import",
    "import.module": "semantic_import",
    "parameter": "parameter",
    "variable": "semantic_variable",
    "variable.def": "semantic_variable",
    "variable.builtin": "builtin",
    "property": "semantic_property",
    "module": "semantic_import",
    "namespace": "semantic_import",
    "decorator": "decorator",
    "operator": "operator",
    "punctuation": "punctuation",
    "punctuation.bracket": "punctuation",
    "punctuation.delimiter": "punctuation",
    "json_key": "json_key",
    "json_literal": "json_literal",
    "markdown_heading": "markdown_heading",
    "markdown_emphasis": "markdown_emphasis",
    "markdown_strong": "markdown_strong",
    "markdown_code": "markdown_code",
    "tag": "class",
    "attribute": "semantic_property",
}


@dataclass(frozen=True)
class _PendingEdit:
    start_byte: int
    old_end_byte: int
    new_end_byte: int
    start_point: tuple[int, int]
    old_end_point: tuple[int, int]
    new_end_point: tuple[int, int]


@dataclass(frozen=True)
class _CaptureSpan:
    token_name: str
    start_col: int
    end_col: int
    capture_name: str = ""
    origin: str = "highlights"



@dataclass(frozen=True)
class _PointRange:
    start_point: tuple[int, int]
    end_point: tuple[int, int]



class TreeSitterCapturePipelineMixin:
    def _parse_with_optional_tree(self, old_tree: Any | None) -> tuple[Any | None, bool]:
        host = _host(self)
        source_bytes = host._source_text.encode("utf-8")
        if old_tree is None:
            return host._parser.parse(source_bytes), False
        try:
            return host._parser.parse(source_bytes, old_tree), True
        except TypeError as exc:
            if "Second argument to parse must be a Tree" not in str(exc):
                raise
            return host._parser.parse(source_bytes), False


    def _update_capture_cache(
        self,
        *,
        changed_ranges: list[Any],
        full_rebuild: bool,
        fallback_line_ranges: list[tuple[int, int]],
    ) -> None:
        if _host(self)._tree is None or _host(self)._query is None:
            self._capture_cache.clear()
            return
        line_count = max(1, _host(self)._source_text.count("\n") + 1)
        mode = _host(self)._effective_mode()

        if mode == constants.HIGHLIGHTING_MODE_NORMAL:
            if full_rebuild:
                self._capture_cache = _host(self)._query_capture_ranges([(0, line_count - 1)])
                return
            line_ranges = self._line_ranges_from_changed_ranges(changed_ranges, line_count)
            if fallback_line_ranges:
                line_ranges = self._merge_line_ranges([*line_ranges, *fallback_line_ranges])
            if not line_ranges:
                return
            for start_line, end_line in line_ranges:
                for line_number in range(start_line, end_line + 1):
                    self._capture_cache.pop(line_number, None)
            refreshed = _host(self)._query_capture_ranges(line_ranges)
            for line_number, spans in refreshed.items():
                self._capture_cache[line_number] = spans
            return

        window = _host(self)._query_window_for_large_modes(line_count)
        if window is None:
            self._capture_cache.clear()
            return
        self._capture_cache = _host(self)._query_capture_ranges([window])

    def _line_ranges_from_changed_ranges(self, changed_ranges: list[Any], line_count: int) -> list[tuple[int, int]]:
        if not changed_ranges:
            return []
        ranges: list[tuple[int, int]] = []
        for change_range in changed_ranges:
            start_line = max(0, int(change_range.start_point[0]) - _RANGE_EXPANSION_LINES)
            end_line = min(line_count - 1, int(change_range.end_point[0]) + _RANGE_EXPANSION_LINES)
            ranges.append((start_line, max(start_line, end_line)))
        return self._merge_line_ranges(ranges)

    @staticmethod
    def _first_reusable_line_after_edit(*, pending_edit: _PendingEdit) -> tuple[int, int]:
        old_line = int(pending_edit.old_end_point[0])
        new_line = int(pending_edit.new_end_point[0])
        if int(pending_edit.old_end_point[1]) != 0:
            return (old_line + 1, new_line + 1)
        return (old_line, new_line)

    def _shift_capture_cache_for_line_delta(self, *, pending_edit: _PendingEdit) -> None:
        if not self._capture_cache:
            return
        start_line = int(pending_edit.start_point[0])
        reusable_old_line, reusable_new_line = self._first_reusable_line_after_edit(pending_edit=pending_edit)
        shifted_cache: dict[int, list[_CaptureSpan]] = {}
        for line_number, spans in self._capture_cache.items():
            if line_number < start_line:
                shifted_cache[line_number] = spans
                continue
            if line_number < reusable_old_line:
                continue
            shifted_line = reusable_new_line + (line_number - reusable_old_line)
            if shifted_line < 0:
                continue
            shifted_cache[shifted_line] = spans
        self._capture_cache = shifted_cache

    def _rehighlight_window_for_edit(self, *, pending_edit: _PendingEdit, line_delta: int) -> tuple[int, int]:
        document = _host(self).document()
        start_line = int(pending_edit.start_point[0])
        end_line = int(pending_edit.new_end_point[0])
        rehighlight_start = max(0, start_line - _RANGE_EXPANSION_LINES)
        rehighlight_end = max(rehighlight_start, end_line + _RANGE_EXPANSION_LINES)
        if line_delta == 0 or document is None:
            return (rehighlight_start, rehighlight_end)

        viewport_start, viewport_end = _host(self)._viewport_lines
        if viewport_start != 0 or viewport_end != 0:
            rehighlight_start = min(rehighlight_start, viewport_start)
            rehighlight_end = max(rehighlight_end, viewport_end + _RANGE_EXPANSION_LINES)
        else:
            rehighlight_end = max(rehighlight_end, max(0, document.blockCount() - 1))
        return (rehighlight_start, max(rehighlight_start, rehighlight_end))

    def _query_window_for_large_modes(self, line_count: int) -> tuple[int, int] | None:
        start_line, end_line = _host(self)._viewport_lines
        if start_line == 0 and end_line == 0:
            return None
        window_start = max(0, start_line - _QUERY_MARGIN_LINES)
        window_end = min(line_count - 1, end_line + _QUERY_MARGIN_LINES)
        return (window_start, window_end)

    def _query_capture_ranges(self, line_ranges: list[tuple[int, int]]) -> dict[int, list[_CaptureSpan]]:
        if _host(self)._tree is None or _host(self)._query is None:
            return {}
        lines = _host(self)._source_text.split("\n")
        max_line = max(0, len(lines) - 1)
        merged_ranges = self._merge_line_ranges(line_ranges)
        spans_by_line: dict[int, list[_CaptureSpan]] = {}
        seen_by_line: dict[int, dict[tuple[int, int], int]] = {}

        for start_line, end_line in merged_ranges:
            bounded_start = max(0, min(start_line, max_line))
            bounded_end = max(bounded_start, min(end_line, max_line))
            captures = self._captures_for_range(
                start_line=bounded_start,
                end_line=bounded_end,
            )
            for node, capture_name in captures:
                token_name = _host(self)._resolve_token_name(capture_name)
                if token_name is None:
                    continue
                token_name = self._apply_capture_overrides(
                    capture_name=capture_name,
                    token_name=token_name,
                    node=node,
                    lines=lines,
                )
                if token_name is None:
                    continue
                for line_number, span in self._build_spans_for_node(
                    node=node,
                    token_name=token_name,
                    lines=lines,
                    capture_name=capture_name,
                    origin="highlights",
                ):
                    if line_number < bounded_start or line_number > bounded_end:
                        continue
                    if self._append_capture_span(
                        spans_by_line=spans_by_line,
                        seen_by_line=seen_by_line,
                        line_number=line_number,
                        span=span,
                    ) and token_name == "string":
                        line_text = lines[line_number]
                        for escape_span in self._lex_escape_spans(
                            line_text=line_text,
                            start_col=span.start_col,
                            end_col=span.end_col,
                        ):
                            self._append_capture_span(
                                spans_by_line=spans_by_line,
                                seen_by_line=seen_by_line,
                                line_number=line_number,
                                span=escape_span,
                            )

        _host(self)._add_local_semantic_spans(
            lines=lines,
            merged_ranges=merged_ranges,
            spans_by_line=spans_by_line,
            seen_by_line=seen_by_line,
        )

        if _host(self)._language_key == "markdown":
            _host(self)._add_markdown_lexical_spans(
                lines=lines,
                merged_ranges=merged_ranges,
                spans_by_line=spans_by_line,
                seen_by_line=seen_by_line,
            )

        if _host(self)._language_key == "jsonc":
            _host(self)._add_jsonc_comment_spans(
                lines=lines,
                merged_ranges=merged_ranges,
                spans_by_line=spans_by_line,
                seen_by_line=seen_by_line,
            )

        _host(self)._add_injection_spans(
            lines=lines,
            merged_ranges=merged_ranges,
            spans_by_line=spans_by_line,
            seen_by_line=seen_by_line,
        )

        for line_number in list(spans_by_line.keys()):
            spans_by_line[line_number].sort(
                key=lambda value: (
                    value.start_col,
                    self._capture_priority(value),
                    -(value.end_col - value.start_col),
                    value.token_name,
                )
            )
        return spans_by_line

    @staticmethod
    def _append_capture_span(
        *,
        spans_by_line: dict[int, list[_CaptureSpan]],
        seen_by_line: dict[int, dict[tuple[int, int], int]],
        line_number: int,
        span: _CaptureSpan,
    ) -> bool:
        if line_number not in spans_by_line:
            spans_by_line[line_number] = []
            seen_by_line[line_number] = {}
        span_key = (span.start_col, span.end_col)
        existing_index = seen_by_line[line_number].get(span_key)
        if existing_index is not None:
            existing_span = spans_by_line[line_number][existing_index]
            if TreeSitterCapturePipelineMixin._capture_priority(span) <= TreeSitterCapturePipelineMixin._capture_priority(existing_span):
                return False
            spans_by_line[line_number][existing_index] = span
            return True
        seen_by_line[line_number][span_key] = len(spans_by_line[line_number])
        spans_by_line[line_number].append(span)
        return True

    @staticmethod
    def _capture_priority(span: _CaptureSpan) -> int:
        if span.origin.startswith("injection:"):
            return 90
        if span.token_name == "escape":
            return 95
        if span.token_name == "builtin":
            return 88
        if span.token_name.startswith("semantic_"):
            return 85
        if span.token_name in {"markdown_code", "string", "comment"}:
            return 40
        return 60

    def _captures_for_range(self, *, start_line: int, end_line: int) -> list[tuple[Any, str]]:
        host = _host(self)
        tree = host._tree
        query = host._query
        if tree is None or query is None:
            return []
        raw_captures: Any
        if host._query_supports_range_kwargs is not False:
            try:
                raw_captures = query.captures(
                    tree.root_node,
                    start_point=(start_line, 0),
                    end_point=(end_line + 1, 0),
                )
                host._query_supports_range_kwargs = True
            except TypeError:
                host._query_supports_range_kwargs = False
                raw_captures = query.captures(tree.root_node)
        else:
            raw_captures = query.captures(tree.root_node)
        return self._normalize_captures(
            raw_captures,
            start_line=start_line,
            end_line=end_line,
        )

    @staticmethod
    def _normalize_captures(
        raw_captures: Any,
        *,
        start_line: int,
        end_line: int,
    ) -> list[tuple[Any, str]]:
        normalized: list[tuple[Any, str]] = []
        if isinstance(raw_captures, dict):
            for capture_name, nodes in raw_captures.items():
                for node in nodes:
                    if TreeSitterCapturePipelineMixin._node_intersects_line_range(node, start_line, end_line):
                        normalized.append((node, capture_name))
            return normalized
        for node, capture_name in raw_captures:
            if TreeSitterCapturePipelineMixin._node_intersects_line_range(node, start_line, end_line):
                normalized.append((node, capture_name))
        return normalized

    @staticmethod
    def _node_intersects_line_range(node: Any, start_line: int, end_line: int) -> bool:
        node_start = int(node.start_point[0])
        node_end = int(node.end_point[0])
        return not (node_end < start_line or node_start > end_line)

    def _build_spans_for_node(
        self,
        *,
        node: Any,
        token_name: str,
        lines: list[str],
        capture_name: str = "",
        origin: str = "highlights",
    ) -> Iterator[tuple[int, _CaptureSpan]]:
        if not lines:
            lines = [""]
        max_line = len(lines) - 1
        start_line = max(0, min(int(node.start_point[0]), max_line))
        end_line = max(0, min(int(node.end_point[0]), max_line))
        start_byte_col = max(0, int(node.start_point[1]))
        end_byte_col = max(0, int(node.end_point[1]))

        if start_line == end_line:
            line_text = lines[start_line]
            start_col = self._byte_col_to_char_col(line_text, start_byte_col)
            end_col = self._byte_col_to_char_col(line_text, end_byte_col)
            if end_col > start_col:
                yield (
                    start_line,
                    _CaptureSpan(
                        token_name=token_name,
                        start_col=start_col,
                        end_col=end_col,
                        capture_name=capture_name,
                        origin=origin,
                    ),
                )
            return

        first_line_text = lines[start_line]
        first_start = self._byte_col_to_char_col(first_line_text, start_byte_col)
        first_end = len(first_line_text)
        if first_end > first_start:
            yield (
                start_line,
                _CaptureSpan(
                    token_name=token_name,
                    start_col=first_start,
                    end_col=first_end,
                    capture_name=capture_name,
                    origin=origin,
                ),
            )

        for line_number in range(start_line + 1, end_line):
            middle_line_text = lines[line_number]
            middle_end = len(middle_line_text)
            if middle_end > 0:
                yield (
                    line_number,
                    _CaptureSpan(
                        token_name=token_name,
                        start_col=0,
                        end_col=middle_end,
                        capture_name=capture_name,
                        origin=origin,
                    ),
                )

        last_line_text = lines[end_line]
        last_end = self._byte_col_to_char_col(last_line_text, end_byte_col)
        if last_end > 0:
            yield (
                end_line,
                _CaptureSpan(
                    token_name=token_name,
                    start_col=0,
                    end_col=last_end,
                    capture_name=capture_name,
                    origin=origin,
                ),
            )

    def _apply_capture_overrides(
        self,
        *,
        capture_name: str,
        token_name: str,
        node: Any,
        lines: list[str],
    ) -> str | None:
        if _host(self)._language_key != "python":
            return token_name
        node_text = self._node_text(node=node, lines=lines)
        if not node_text:
            return token_name
        if capture_name in {"variable", "variable.def", "parameter"} and node_text in PYTHON_SPECIAL_VARIABLES:
            return "builtin"
        if capture_name == "function.call" and node_text in PYTHON_BUILTIN_FUNCTIONS:
            return "builtin"
        return token_name

    def _node_text(self, *, node: Any, lines: list[str]) -> str:
        if not lines:
            return ""
        max_line = len(lines) - 1
        start_line = max(0, min(int(node.start_point[0]), max_line))
        end_line = max(0, min(int(node.end_point[0]), max_line))
        if start_line != end_line:
            return ""
        line_text = lines[start_line]
        start_col = self._byte_col_to_char_col(line_text, max(0, int(node.start_point[1])))
        end_col = self._byte_col_to_char_col(line_text, max(0, int(node.end_point[1])))
        if end_col <= start_col:
            return ""
        return line_text[start_col:end_col]

    @staticmethod
    def _lex_escape_spans(*, line_text: str, start_col: int, end_col: int) -> Iterator[_CaptureSpan]:
        segment_start = max(0, min(start_col, len(line_text)))
        segment_end = max(segment_start, min(end_col, len(line_text)))
        if segment_end <= segment_start:
            return
        segment = line_text[segment_start:segment_end]
        for match in _ESCAPE_SEQUENCE_PATTERN.finditer(segment):
            escape_start = segment_start + match.start()
            escape_end = segment_start + match.end()
            if escape_end <= escape_start:
                continue
            yield _CaptureSpan(
                token_name="escape",
                start_col=escape_start,
                end_col=escape_end,
                capture_name="escape",
                origin="escapes",
            )

    def _descendant_node_at_point(self, *, line_number: int, byte_col: int) -> Any | None:
        tree = _host(self)._tree
        if tree is None:
            return None
        root_node = tree.root_node
        for method_name in ("named_descendant_for_point_range", "descendant_for_point_range"):
            method = getattr(root_node, method_name, None)
            if callable(method):
                try:
                    return method((line_number, byte_col), (line_number, byte_col))
                except Exception:
                    continue
        return root_node

    def _capture_descriptions_at_point(self, *, line_number: int, byte_col: int, lines: list[str]) -> list[str]:
        descriptions: list[str] = []
        seen: set[str] = set()
        for node, capture_name in self._captures_for_range(start_line=line_number, end_line=line_number):
            if not self._point_in_node(node=node, line_number=line_number, byte_col=byte_col):
                continue
            token_name = _host(self)._resolve_token_name(capture_name)
            if token_name is None:
                continue
            token_name = self._apply_capture_overrides(
                capture_name=capture_name,
                token_name=token_name,
                node=node,
                lines=lines,
            )
            if token_name is None:
                continue
            detail = f"{capture_name} -> {token_name}"
            if detail in seen:
                continue
            seen.add(detail)
            descriptions.append(detail)
        return descriptions

    @staticmethod
    def _point_in_node(*, node: Any, line_number: int, byte_col: int) -> bool:
        start_line = int(node.start_point[0])
        end_line = int(node.end_point[0])
        if line_number < start_line or line_number > end_line:
            return False
        if line_number == start_line and byte_col < int(node.start_point[1]):
            return False
        if line_number == end_line and byte_col >= int(node.end_point[1]):
            return False
        return True

    @staticmethod
    def _merge_line_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if not ranges:
            return []
        ordered = sorted((max(0, start), max(0, end)) for start, end in ranges)
        merged: list[tuple[int, int]] = []
        current_start, current_end = ordered[0]
        if current_end < current_start:
            current_end = current_start
        for start, end in ordered[1:]:
            if end < start:
                end = start
            if start <= current_end + 1:
                current_end = max(current_end, end)
                continue
            merged.append((current_start, current_end))
            current_start, current_end = start, end
        merged.append((current_start, current_end))
        return merged

    @staticmethod
    def _byte_col_to_char_col(line_text: str, byte_col: int) -> int:
        if line_text.isascii():
            return min(byte_col, len(line_text))
        encoded = line_text.encode("utf-8")
        clamped = max(0, min(byte_col, len(encoded)))
        return len(encoded[:clamped].decode("utf-8", errors="ignore"))

    @staticmethod
    def _char_to_byte_offset(text: str, offset: int) -> int:
        clamped = max(0, min(offset, len(text)))
        if text.isascii():
            return clamped
        return len(text[:clamped].encode("utf-8"))

    @staticmethod
    def _char_to_point(text: str, offset: int) -> tuple[int, int]:
        clamped = max(0, min(offset, len(text)))
        line = text.count("\n", 0, clamped)
        line_start = text.rfind("\n", 0, clamped)
        segment_start = 0 if line_start < 0 else line_start + 1
        col = clamped - segment_start
        if text.isascii():
            return (line, col)
        segment = text[segment_start:clamped]
        return (line, len(segment.encode("utf-8")))
