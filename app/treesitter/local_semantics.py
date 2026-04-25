from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, cast

from app.bootstrap.logging_setup import get_subsystem_logger
from app.treesitter.capture_pipeline import _CaptureSpan, _PointRange
from app.treesitter.python_tokens import PYTHON_SPECIAL_VARIABLES, SCREAMING_SNAKE_PATTERN

_LOGGER = get_subsystem_logger("treesitter")


class _LocalSemanticsHost(Protocol):
    TOKEN_STYLES: dict[str, Any]
    _tree: Any | None
    _locals_query: Any | None
    _source_text: str
    _language_key: str

    def _node_text(self, *, node: Any, lines: list[str]) -> str: ...
    def _build_spans_for_node(
        self,
        *,
        node: Any,
        token_name: str,
        lines: list[str],
        capture_name: str,
        origin: str,
    ) -> Any: ...
    def _append_capture_span(
        self,
        *,
        spans_by_line: dict[int, list[_CaptureSpan]],
        seen_by_line: dict[int, dict[tuple[int, int], int]],
        line_number: int,
        span: _CaptureSpan,
    ) -> None: ...


def _host(instance: object) -> _LocalSemanticsHost:
    return cast(_LocalSemanticsHost, instance)

@dataclass(frozen=True)
class _ScopeRecord:
    start_byte: int
    end_byte: int
    parent_index: int


@dataclass(frozen=True)
class _LocalDefinition:
    name: str
    token_name: str
    scope_index: int
    color_definition: bool
    start_point: tuple[int, int]
    end_point: tuple[int, int]
    start_byte: int
    end_byte: int


@dataclass(frozen=True)
class _LocalReference:
    name: str
    scope_index: int
    start_point: tuple[int, int]
    end_point: tuple[int, int]
    start_byte: int
    end_byte: int




class TreeSitterLocalSemanticsMixin:
    def _rebuild_local_tokens(self) -> None:
        self._local_tokens = []
        self._resolved_local_tokens = []
        host = _host(self)
        if host._tree is None or host._locals_query is None:
            return
        lines = host._source_text.split("\n")
        source_bytes = host._source_text.encode("utf-8")
        try:
            matches = host._locals_query.matches(host._tree.root_node)
        except Exception:  # pragma: no cover - defensive path
            _LOGGER.warning("Failed to evaluate locals query for %s.", host._language_key, exc_info=True)
            return

        scope_ranges: list[tuple[int, int]] = [(0, len(source_bytes))]
        pending_definitions: list[tuple[Any, str, bool, bool]] = []
        pending_references: list[Any] = []

        for pattern_index, capture_map in matches:
            settings = self._query_settings(host._locals_query, pattern_index)
            role = str(settings.get("local.role", "semantic_variable"))
            color_definition = str(settings.get("local.color_definition", "")).lower() == "true"
            scope_lift = str(settings.get("local.scope_lift", "")).lower() == "true"
            for scope_node in capture_map.get("local.scope", []):
                scope_ranges.append((int(scope_node.start_byte), int(scope_node.end_byte)))
            for definition_node in capture_map.get("local.definition", []):
                pending_definitions.append((definition_node, role, color_definition, scope_lift))
            for reference_node in capture_map.get("local.reference", []):
                pending_references.append(reference_node)

        scopes = self._build_scope_records(scope_ranges)
        definitions_by_scope: dict[int, list[_LocalDefinition]] = {}
        for definition_node, role, color_definition, scope_lift in pending_definitions:
            name = host._node_text(node=definition_node, lines=lines)
            if not name:
                continue
            scope_index = self._scope_index_for_range(
                scopes,
                start_byte=int(definition_node.start_byte),
                end_byte=int(definition_node.end_byte),
            )
            if scope_lift:
                scope_index = scopes[scope_index].parent_index
            token_name = self._normalize_local_role(name=name, role=role)
            definition = _LocalDefinition(
                name=name,
                token_name=token_name,
                scope_index=scope_index,
                color_definition=color_definition,
                start_point=(int(definition_node.start_point[0]), int(definition_node.start_point[1])),
                end_point=(int(definition_node.end_point[0]), int(definition_node.end_point[1])),
                start_byte=int(definition_node.start_byte),
                end_byte=int(definition_node.end_byte),
            )
            definitions_by_scope.setdefault(scope_index, []).append(definition)
            self._local_tokens.append(definition)
            if color_definition:
                self._resolved_local_tokens.append((definition, token_name))

        for reference_node in pending_references:
            name = host._node_text(node=reference_node, lines=lines)
            if not name:
                continue
            scope_index = self._scope_index_for_range(
                scopes,
                start_byte=int(reference_node.start_byte),
                end_byte=int(reference_node.end_byte),
            )
            resolved_definition = self._lookup_local_definition(
                definitions_by_scope=definitions_by_scope,
                scopes=scopes,
                scope_index=scope_index,
                name=name,
                reference_start_byte=int(reference_node.start_byte),
            )
            if resolved_definition is None:
                continue
            reference = _LocalReference(
                name=name,
                scope_index=scope_index,
                start_point=(int(reference_node.start_point[0]), int(reference_node.start_point[1])),
                end_point=(int(reference_node.end_point[0]), int(reference_node.end_point[1])),
                start_byte=int(reference_node.start_byte),
                end_byte=int(reference_node.end_byte),
            )
            self._local_tokens.append(reference)
            self._resolved_local_tokens.append((reference, resolved_definition.token_name))

    @staticmethod
    def _query_settings(query: Any, pattern_index: int) -> dict[str, str]:
        try:
            settings = query.pattern_settings(pattern_index)
        except Exception:
            return {}
        if not isinstance(settings, dict):
            return {}
        return {str(key): str(value) for key, value in settings.items()}

    @staticmethod
    def _build_scope_records(scope_ranges: list[tuple[int, int]]) -> list[_ScopeRecord]:
        ordered_ranges = sorted(set(scope_ranges), key=lambda value: (value[0], -(value[1] - value[0])))
        if not ordered_ranges:
            return [_ScopeRecord(0, 0, 0)]
        root_start, root_end = ordered_ranges[0]
        records = [_ScopeRecord(root_start, root_end, 0)]
        for start_byte, end_byte in ordered_ranges[1:]:
            parent_index = 0
            for candidate_index in range(len(records) - 1, -1, -1):
                candidate = records[candidate_index]
                if candidate.start_byte <= start_byte and end_byte <= candidate.end_byte:
                    parent_index = candidate_index
                    break
            records.append(_ScopeRecord(start_byte, end_byte, parent_index))
        return records

    @staticmethod
    def _scope_index_for_range(scopes: list[_ScopeRecord], *, start_byte: int, end_byte: int) -> int:
        for index in range(len(scopes) - 1, -1, -1):
            scope = scopes[index]
            if scope.start_byte <= start_byte and end_byte <= scope.end_byte:
                return index
        return 0

    @staticmethod
    def _lookup_local_definition(
        *,
        definitions_by_scope: dict[int, list[_LocalDefinition]],
        scopes: list[_ScopeRecord],
        scope_index: int,
        name: str,
        reference_start_byte: int,
    ) -> _LocalDefinition | None:
        search_scope = scope_index
        while True:
            definitions = definitions_by_scope.get(search_scope, [])
            matching = [
                definition
                for definition in definitions
                if definition.name == name and definition.start_byte < reference_start_byte
            ]
            if matching:
                return matching[-1]
            if search_scope == 0:
                return None
            search_scope = scopes[search_scope].parent_index

    def _normalize_local_role(self, *, name: str, role: str) -> str:
        if name in PYTHON_SPECIAL_VARIABLES:
            return "builtin"
        normalized = role if role in _host(self).TOKEN_STYLES else "semantic_variable"
        if normalized == "semantic_variable" and SCREAMING_SNAKE_PATTERN.match(name):
            return "semantic_constant"
        return normalized

    def _add_local_semantic_spans(
        self,
        *,
        lines: list[str],
        merged_ranges: list[tuple[int, int]],
        spans_by_line: dict[int, list[_CaptureSpan]],
        seen_by_line: dict[int, dict[tuple[int, int], int]],
    ) -> None:
        for entry, token_name in self._resolved_local_tokens:
            start_line = int(entry.start_point[0])
            end_line = int(entry.end_point[0])
            if not any(not (end_line < range_start or start_line > range_end) for range_start, range_end in merged_ranges):
                continue
            point_node = _PointRange(start_point=entry.start_point, end_point=entry.end_point)
            for line_number, span in _host(self)._build_spans_for_node(
                node=point_node,
                token_name=token_name,
                lines=lines,
                capture_name=token_name,
                origin="locals",
            ):
                _host(self)._append_capture_span(
                    spans_by_line=spans_by_line,
                    seen_by_line=seen_by_line,
                    line_number=line_number,
                    span=span,
                )
