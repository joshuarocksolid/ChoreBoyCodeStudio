from __future__ import annotations

from typing import Any, Iterator, Protocol, cast

from PySide2.QtGui import QTextDocument

from app.bootstrap.logging_setup import get_subsystem_logger
from app.treesitter.capture_pipeline import _CaptureSpan
from app.treesitter.language_registry import TreeSitterResolvedLanguage

_MAX_INJECTION_DEPTH = 2
_LOGGER = get_subsystem_logger("treesitter")


class _InjectionHost(Protocol):
    _tree: Any | None
    _injections_query: Any | None
    _injection_depth: int
    _language_key: str
    _registry: Any
    _source_text: str

    def _append_capture_span(
        self,
        *,
        spans_by_line: dict[int, list[_CaptureSpan]],
        seen_by_line: dict[int, dict[tuple[int, int], int]],
        line_number: int,
        span: _CaptureSpan,
    ) -> None: ...
    def _node_text(self, *, node: Any, lines: list[str]) -> str: ...
    def _query_settings(self, query: Any, pattern_index: int) -> dict[str, str]: ...
    def _create_embedded_highlighter(
        self,
        document: QTextDocument,
        *,
        resolved_language: TreeSitterResolvedLanguage,
        injection_depth: int,
    ) -> Any: ...
    def _byte_col_to_char_col(self, line_text: str, byte_col: int) -> int: ...


def _host(instance: object) -> _InjectionHost:
    return cast(_InjectionHost, instance)


class TreeSitterInjectionMixin:
    def _add_injection_spans(
        self,
        *,
        lines: list[str],
        merged_ranges: list[tuple[int, int]],
        spans_by_line: dict[int, list[_CaptureSpan]],
        seen_by_line: dict[int, dict[tuple[int, int], int]],
    ) -> None:
        host = _host(self)
        if host._tree is None or host._injections_query is None or host._injection_depth >= _MAX_INJECTION_DEPTH:
            return
        try:
            matches = host._injections_query.matches(host._tree.root_node)
        except Exception:  # pragma: no cover - defensive path
            _LOGGER.warning("Failed to evaluate injections query for %s.", host._language_key, exc_info=True)
            return
        for pattern_index, capture_map in matches:
            language_name = self._resolve_injection_language(pattern_index=pattern_index, capture_map=capture_map, lines=lines)
            if language_name is None:
                continue
            resolved_language = host._registry.resolve_for_injection_name(language_name)
            if resolved_language is None:
                continue
            content_nodes = capture_map.get("injection.content", [])
            for content_node in content_nodes:
                if not self._node_intersects_any_range(content_node, merged_ranges):
                    continue
                for line_number, span in self._embedded_spans_for_node(
                    content_node=content_node,
                    resolved_language=resolved_language,
                    lines=lines,
                ):
                    if not any(range_start <= line_number <= range_end for range_start, range_end in merged_ranges):
                        continue
                    host._append_capture_span(
                        spans_by_line=spans_by_line,
                        seen_by_line=seen_by_line,
                        line_number=line_number,
                        span=span,
                    )

    def _resolve_injection_language(
        self,
        *,
        pattern_index: int,
        capture_map: dict[str, list[Any]],
        lines: list[str],
    ) -> str | None:
        language_nodes = capture_map.get("injection.language", [])
        if language_nodes:
            language_name = _host(self)._node_text(node=language_nodes[0], lines=lines).strip()
            if language_name:
                return language_name
        host = _host(self)
        settings = host._query_settings(host._injections_query, pattern_index)
        configured_language = settings.get("injection.language", "").strip()
        return configured_language or None

    @staticmethod
    def _node_intersects_any_range(node: Any, merged_ranges: list[tuple[int, int]]) -> bool:
        start_line = int(node.start_point[0])
        end_line = int(node.end_point[0])
        return any(not (end_line < range_start or start_line > range_end) for range_start, range_end in merged_ranges)

    def _embedded_spans_for_node(
        self,
        *,
        content_node: Any,
        resolved_language: TreeSitterResolvedLanguage,
        lines: list[str],
    ) -> Iterator[tuple[int, _CaptureSpan]]:
        host = _host(self)
        embedded_source = host._source_text.encode("utf-8")[int(content_node.start_byte) : int(content_node.end_byte)].decode(
            "utf-8",
            errors="replace",
        )
        if not embedded_source.strip():
            return
        temp_document = QTextDocument()
        temp_document.setPlainText(embedded_source)
        embedded_highlighter = host._create_embedded_highlighter(
            temp_document,
            resolved_language=resolved_language,
            injection_depth=host._injection_depth + 1,
        )
        embedded_highlighter.rehighlight()
        embedded_highlighter._ensure_tree_and_cache()
        parent_line = int(content_node.start_point[0])
        parent_col = host._byte_col_to_char_col(lines[parent_line], int(content_node.start_point[1])) if lines else 0
        for relative_line, relative_spans in embedded_highlighter._capture_cache.items():
            for relative_span in relative_spans:
                start_col = relative_span.start_col + (parent_col if relative_line == 0 else 0)
                end_col = relative_span.end_col + (parent_col if relative_line == 0 else 0)
                yield (
                    parent_line + relative_line,
                    _CaptureSpan(
                        token_name=relative_span.token_name,
                        start_col=start_col,
                        end_col=end_col,
                        capture_name=relative_span.capture_name,
                        origin=f"injection:{resolved_language.language_key}",
                    ),
                )

