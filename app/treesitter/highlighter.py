from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterator, cast

from PySide2.QtGui import QTextDocument

from app.bootstrap.logging_setup import get_subsystem_logger
from app.core import constants
from app.editors.editor_overlay_policy import effective_highlighting_mode
from app.editors.syntax_engine import TokenStyle, ThemedSyntaxHighlighter
from app.treesitter.language_registry import TreeSitterResolvedLanguage, default_tree_sitter_language_registry

_QUERY_MARGIN_LINES = 220
_RANGE_EXPANSION_LINES = 3
_MAX_INJECTION_DEPTH = 2
_ESCAPE_SEQUENCE_PATTERN = re.compile(r"\\(?:[0-7]{1,3}|x[0-9A-Fa-f]{1,2}|u[0-9A-Fa-f]{1,4}|U[0-9A-Fa-f]{1,8}|N\{[^}\n]*\}|.)")
_MARKDOWN_ATX_HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s+.*$")
_MARKDOWN_LIST_MARKER_PATTERN = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")
_MARKDOWN_STRONG_PATTERN = re.compile(r"(?<!\*)\*\*([^*\n]+)\*\*(?!\*)")
_MARKDOWN_EMPHASIS_PATTERN = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_MARKDOWN_CODE_SPAN_PATTERN = re.compile(r"`[^`\n]+`")
_SCREAMING_SNAKE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
_PYTHON_SPECIAL_VARIABLES = frozenset({"self", "cls"})
_PYTHON_BUILTIN_FUNCTIONS = frozenset(
    {
        "abs",
        "all",
        "any",
        "ascii",
        "bin",
        "bool",
        "breakpoint",
        "bytearray",
        "bytes",
        "callable",
        "chr",
        "classmethod",
        "compile",
        "complex",
        "delattr",
        "dict",
        "dir",
        "divmod",
        "enumerate",
        "eval",
        "exec",
        "filter",
        "float",
        "format",
        "frozenset",
        "getattr",
        "globals",
        "hasattr",
        "hash",
        "help",
        "hex",
        "id",
        "input",
        "int",
        "isinstance",
        "issubclass",
        "iter",
        "len",
        "list",
        "locals",
        "map",
        "max",
        "memoryview",
        "min",
        "next",
        "object",
        "oct",
        "open",
        "ord",
        "pow",
        "print",
        "property",
        "range",
        "repr",
        "reversed",
        "round",
        "set",
        "setattr",
        "slice",
        "sorted",
        "staticmethod",
        "str",
        "sum",
        "super",
        "tuple",
        "type",
        "vars",
        "zip",
        "__import__",
    }
)
_LOGGER = get_subsystem_logger("treesitter")

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
class TreeSitterQueryDiagnostic:
    language_key: str
    query_kind: str
    message: str
    traceback: str


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


@dataclass(frozen=True)
class _PointRange:
    start_point: tuple[int, int]
    end_point: tuple[int, int]


class TreeSitterHighlighter(ThemedSyntaxHighlighter):
    TOKEN_STYLES = {
        "keyword": TokenStyle("keyword", bold=True),
        "keyword_control": TokenStyle("keyword_control", bold=True),
        "keyword_import": TokenStyle("keyword_import"),
        "keyword_operator": TokenStyle("keyword_operator", bold=True),
        "builtin": TokenStyle("builtin"),
        "escape": TokenStyle("escape"),
        "string": TokenStyle("string"),
        "comment": TokenStyle("comment", italic=True),
        "number": TokenStyle("number"),
        "function": TokenStyle("function", bold=True),
        "class": TokenStyle("class", bold=True),
        "decorator": TokenStyle("decorator"),
        "operator": TokenStyle("operator"),
        "punctuation": TokenStyle("punctuation"),
        "parameter": TokenStyle("parameter"),
        "json_key": TokenStyle("json_key"),
        "json_literal": TokenStyle("json_literal"),
        "markdown_heading": TokenStyle("markdown_heading", bold=True),
        "markdown_emphasis": TokenStyle("markdown_emphasis"),
        "markdown_strong": TokenStyle("markdown_strong", bold=True),
        "markdown_code": TokenStyle("markdown_code"),
        "semantic_function": TokenStyle("semantic_function"),
        "semantic_method": TokenStyle("semantic_method"),
        "semantic_class": TokenStyle("semantic_class"),
        "semantic_parameter": TokenStyle("semantic_parameter"),
        "semantic_import": TokenStyle("semantic_import"),
        "semantic_variable": TokenStyle("semantic_variable"),
        "semantic_property": TokenStyle("semantic_property"),
        "semantic_constant": TokenStyle("semantic_constant"),
    }

    def __init__(
        self,
        document,  # type: ignore[no-untyped-def]
        *,
        resolved_language: TreeSitterResolvedLanguage,
        is_dark: bool = False,
        syntax_palette: dict[str, str] | None = None,
        injection_depth: int = 0,
    ) -> None:
        super().__init__(document, is_dark=is_dark, syntax_palette=syntax_palette)
        import tree_sitter

        self._language_key = resolved_language.language_key
        self._language_display_name = resolved_language.display_name
        self._language = resolved_language.language
        self._parser: Any = tree_sitter.Parser()
        if hasattr(self._parser, "set_language"):
            self._parser.set_language(self._language)
        else:
            self._parser.language = self._language
        self._query_diagnostics: list[TreeSitterQueryDiagnostic] = []
        self._query = self._compile_query(
            query_source=resolved_language.highlights_query_source,
            query_kind="highlights",
        )
        self._locals_query = self._compile_query(
            query_source=resolved_language.locals_query_source,
            query_kind="locals",
        )
        self._injections_query = self._compile_query(
            query_source=resolved_language.injections_query_source,
            query_kind="injections",
        )
        self._query_supports_range_kwargs: bool | None = None
        self._registry = default_tree_sitter_language_registry()
        self._injection_depth = max(0, injection_depth)
        self._tree: Any | None = None
        self._source_text = document.toPlainText() if document is not None else ""
        self._pending_edits: list[_PendingEdit] = []
        self._queued_contents_changes: list[tuple[int, int, int, str]] = []
        self._capture_cache: dict[int, list[_CaptureSpan]] = {}
        self._local_tokens: list[_LocalDefinition | _LocalReference] = []
        self._resolved_local_tokens: list[tuple[_LocalDefinition | _LocalReference, str]] = []
        self._highlighting_adaptive_mode = constants.HIGHLIGHTING_MODE_NORMAL
        self._highlighting_reduced_threshold_chars = constants.UI_INTELLIGENCE_HIGHLIGHTING_REDUCED_THRESHOLD_CHARS_DEFAULT
        self._highlighting_lexical_only_threshold_chars = constants.UI_INTELLIGENCE_HIGHLIGHTING_LEXICAL_ONLY_THRESHOLD_CHARS_DEFAULT
        self._viewport_lines = (0, 0)
        self._dirty = True
        self._viewport_dirty = True
        self._last_synced_revision: int = document.revision() if document is not None else -1
        if document is not None:
            document.contentsChange.connect(self._on_contents_change)
            document.contentsChanged.connect(self._on_contents_changed)

    def language_key(self) -> str:
        return self._language_key

    def language_display_name(self) -> str:
        return self._language_display_name

    def query_diagnostics(self) -> tuple[TreeSitterQueryDiagnostic, ...]:
        return tuple(self._query_diagnostics)

    def setDocument(self, document) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        previous_document = self.document()
        if previous_document is not None:
            try:
                previous_document.contentsChange.disconnect(self._on_contents_change)
            except Exception:
                pass
            try:
                previous_document.contentsChanged.disconnect(self._on_contents_changed)
            except Exception:
                pass
        super().setDocument(document)
        self._tree = None
        self._pending_edits.clear()
        self._queued_contents_changes.clear()
        self._capture_cache.clear()
        self._local_tokens = []
        self._resolved_local_tokens = []
        self._source_text = document.toPlainText() if document is not None else ""
        self._dirty = True
        self._viewport_dirty = True
        self._last_synced_revision = document.revision() if document is not None else -1
        if document is not None:
            document.contentsChange.connect(self._on_contents_change)
            document.contentsChanged.connect(self._on_contents_changed)

    def _compile_query(self, *, query_source: str, query_kind: str) -> Any | None:
        if not query_source.strip():
            return None
        try:
            return cast(Any, self._language).query(query_source)
        except Exception:  # pragma: no cover - exercised through diagnostics-facing tests
            import traceback

            failure_traceback = traceback.format_exc()
            message = f"Failed to compile {query_kind} query for {self._language_key}"
            self._query_diagnostics.append(
                TreeSitterQueryDiagnostic(
                    language_key=self._language_key,
                    query_kind=query_kind,
                    message=message,
                    traceback=failure_traceback,
                )
            )
            _LOGGER.warning("%s:\n%s", message, failure_traceback)
            return None

    def set_highlighting_policy(
        self,
        *,
        adaptive_mode: str,
        reduced_threshold_chars: int,
        lexical_only_threshold_chars: int,
    ) -> None:
        valid_modes = {
            constants.HIGHLIGHTING_MODE_NORMAL,
            constants.HIGHLIGHTING_MODE_REDUCED,
            constants.HIGHLIGHTING_MODE_LEXICAL_ONLY,
        }
        resolved_mode = adaptive_mode if adaptive_mode in valid_modes else constants.HIGHLIGHTING_MODE_NORMAL
        resolved_reduced = max(1, int(reduced_threshold_chars))
        resolved_lexical_only = max(resolved_reduced, int(lexical_only_threshold_chars))
        if (
            resolved_mode == self._highlighting_adaptive_mode
            and resolved_reduced == self._highlighting_reduced_threshold_chars
            and resolved_lexical_only == self._highlighting_lexical_only_threshold_chars
        ):
            return
        self._highlighting_adaptive_mode = resolved_mode
        self._highlighting_reduced_threshold_chars = resolved_reduced
        self._highlighting_lexical_only_threshold_chars = resolved_lexical_only
        self._viewport_dirty = True
        self.rehighlight()

    def set_viewport_lines(self, start_line: int, end_line: int) -> None:
        start = max(0, min(start_line, end_line))
        end = max(start, max(start_line, end_line))
        if (start, end) == self._viewport_lines:
            return
        self._viewport_lines = (start, end)
        if self._effective_mode() == constants.HIGHLIGHTING_MODE_NORMAL:
            return
        self._viewport_dirty = True
        self._rehighlight_line_window(start, end)

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        self._ensure_tree_and_cache()
        block_line = self.currentBlock().blockNumber()
        spans = self._capture_cache.get(block_line)
        if not spans:
            return
        for span in spans:
            if span.end_col <= span.start_col:
                continue
            token_format = self._format(span.token_name)
            if token_format is None:
                continue
            self.setFormat(span.start_col, span.end_col - span.start_col, token_format)

    def _on_contents_change(self, position: int, chars_removed: int, chars_added: int) -> None:
        self._queued_contents_changes.append((position, chars_removed, chars_added, self._source_text))

    def _on_contents_changed(self) -> None:
        document = self.document()
        if document is None:
            return
        new_source = document.toPlainText()
        if not self._queued_contents_changes:
            if new_source != self._source_text:
                self._source_text = new_source
                self._tree = None
                self._pending_edits.clear()
                self._dirty = True
                self._rehighlight_line_window(0, max(0, document.blockCount() - 1))
            return
        position, chars_removed, chars_added, old_source = self._queued_contents_changes.pop(0)
        start_char_old = max(0, min(position, len(old_source)))
        old_end_char = max(start_char_old, min(position + chars_removed, len(old_source)))
        start_char_new = max(0, min(position, len(new_source)))
        new_end_char = max(start_char_new, min(position + chars_added, len(new_source)))
        pending_edit = _PendingEdit(
            start_byte=self._char_to_byte_offset(old_source, start_char_old),
            old_end_byte=self._char_to_byte_offset(old_source, old_end_char),
            new_end_byte=self._char_to_byte_offset(new_source, new_end_char),
            start_point=self._char_to_point(old_source, start_char_old),
            old_end_point=self._char_to_point(old_source, old_end_char),
            new_end_point=self._char_to_point(new_source, new_end_char),
        )
        self._pending_edits.append(pending_edit)
        self._source_text = new_source
        self._dirty = True
        line_delta = int(pending_edit.new_end_point[0]) - int(pending_edit.old_end_point[0])
        if line_delta != 0:
            self._shift_capture_cache_for_line_delta(pending_edit=pending_edit)
        rehighlight_start, rehighlight_end = self._rehighlight_window_for_edit(
            pending_edit=pending_edit,
            line_delta=line_delta,
        )
        self._rehighlight_line_window(rehighlight_start, rehighlight_end)

    def rehighlight(self) -> None:  # noqa: N802
        self._sync_source_from_document()
        super().rehighlight()

    def _sync_source_from_document(self) -> None:
        document = self.document()
        if document is None:
            return
        rev = document.revision()
        if rev == self._last_synced_revision:
            return
        current_text = document.toPlainText()
        if current_text != self._source_text:
            self._source_text = current_text
            self._dirty = True
            self._tree = None
            self._pending_edits.clear()
            self._local_tokens = []
            self._resolved_local_tokens = []
        self._last_synced_revision = rev

    def _ensure_tree_and_cache(self) -> None:
        if not self._dirty and not self._viewport_dirty and self._capture_cache:
            return
        if self._query is None:
            self._capture_cache.clear()
            self._dirty = False
            self._viewport_dirty = False
            return

        old_tree = self._tree
        changed_ranges: list[Any] = []
        pending_line_ranges: list[tuple[int, int]] = []
        full_rebuild = old_tree is None
        if self._dirty:
            if self._pending_edits:
                for edit in self._pending_edits:
                    line_delta = int(edit.new_end_point[0]) - int(edit.old_end_point[0])
                    pending_line_ranges.append(
                        self._rehighlight_window_for_edit(
                            pending_edit=edit,
                            line_delta=line_delta,
                        )
                    )
            if old_tree is not None and self._pending_edits:
                for edit in self._pending_edits:
                    old_tree.edit(
                        edit.start_byte,
                        edit.old_end_byte,
                        edit.new_end_byte,
                        edit.start_point,
                        edit.old_end_point,
                        edit.new_end_point,
                    )
            new_tree, used_old_tree = self._parse_with_optional_tree(old_tree)
            self._pending_edits.clear()
            self._dirty = False
            if new_tree is None:
                return
            self._tree = new_tree
            self._rebuild_local_tokens()
            full_rebuild = not used_old_tree
            if used_old_tree and old_tree is not None:
                changed_ranges = old_tree.changed_ranges(new_tree)
        elif self._tree is None:
            self._tree, _ = self._parse_with_optional_tree(None)
            if self._tree is None:
                return
            self._rebuild_local_tokens()
            full_rebuild = True

        self._update_capture_cache(
            changed_ranges=changed_ranges,
            full_rebuild=full_rebuild,
            fallback_line_ranges=pending_line_ranges,
        )
        self._viewport_dirty = False

    def _parse_with_optional_tree(self, old_tree: Any | None) -> tuple[Any | None, bool]:
        source_bytes = self._source_text.encode("utf-8")
        if old_tree is None:
            return self._parser.parse(source_bytes), False
        try:
            return self._parser.parse(source_bytes, old_tree), True
        except TypeError as exc:
            if "Second argument to parse must be a Tree" not in str(exc):
                raise
            return self._parser.parse(source_bytes), False

    def _rebuild_local_tokens(self) -> None:
        self._local_tokens = []
        self._resolved_local_tokens = []
        if self._tree is None or self._locals_query is None:
            return
        lines = self._source_text.split("\n")
        source_bytes = self._source_text.encode("utf-8")
        try:
            matches = self._locals_query.matches(self._tree.root_node)
        except Exception:  # pragma: no cover - defensive path
            _LOGGER.warning("Failed to evaluate locals query for %s.", self._language_key, exc_info=True)
            return

        scope_ranges: list[tuple[int, int]] = [(0, len(source_bytes))]
        pending_definitions: list[tuple[Any, str, bool, bool]] = []
        pending_references: list[Any] = []

        for pattern_index, capture_map in matches:
            settings = self._query_settings(self._locals_query, pattern_index)
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
            name = self._node_text(node=definition_node, lines=lines)
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
            name = self._node_text(node=reference_node, lines=lines)
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
        if name in _PYTHON_SPECIAL_VARIABLES:
            return "builtin"
        normalized = role if role in self.TOKEN_STYLES else "semantic_variable"
        if normalized == "semantic_variable" and _SCREAMING_SNAKE_PATTERN.match(name):
            return "semantic_constant"
        return normalized

    def _update_capture_cache(
        self,
        *,
        changed_ranges: list[Any],
        full_rebuild: bool,
        fallback_line_ranges: list[tuple[int, int]],
    ) -> None:
        if self._tree is None or self._query is None:
            self._capture_cache.clear()
            return
        line_count = max(1, self._source_text.count("\n") + 1)
        mode = self._effective_mode()

        if mode == constants.HIGHLIGHTING_MODE_NORMAL:
            if full_rebuild:
                self._capture_cache = self._query_capture_ranges([(0, line_count - 1)])
                return
            line_ranges = self._line_ranges_from_changed_ranges(changed_ranges, line_count)
            if fallback_line_ranges:
                line_ranges = self._merge_line_ranges([*line_ranges, *fallback_line_ranges])
            if not line_ranges:
                return
            for start_line, end_line in line_ranges:
                for line_number in range(start_line, end_line + 1):
                    self._capture_cache.pop(line_number, None)
            refreshed = self._query_capture_ranges(line_ranges)
            for line_number, spans in refreshed.items():
                self._capture_cache[line_number] = spans
            return

        window = self._query_window_for_large_modes(line_count)
        if window is None:
            self._capture_cache.clear()
            return
        self._capture_cache = self._query_capture_ranges([window])

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
        document = self.document()
        start_line = int(pending_edit.start_point[0])
        end_line = int(pending_edit.new_end_point[0])
        rehighlight_start = max(0, start_line - _RANGE_EXPANSION_LINES)
        rehighlight_end = max(rehighlight_start, end_line + _RANGE_EXPANSION_LINES)
        if line_delta == 0 or document is None:
            return (rehighlight_start, rehighlight_end)

        viewport_start, viewport_end = self._viewport_lines
        if viewport_start != 0 or viewport_end != 0:
            rehighlight_start = min(rehighlight_start, viewport_start)
            rehighlight_end = max(rehighlight_end, viewport_end + _RANGE_EXPANSION_LINES)
        else:
            rehighlight_end = max(rehighlight_end, max(0, document.blockCount() - 1))
        return (rehighlight_start, max(rehighlight_start, rehighlight_end))

    def _query_window_for_large_modes(self, line_count: int) -> tuple[int, int] | None:
        start_line, end_line = self._viewport_lines
        if start_line == 0 and end_line == 0:
            return None
        window_start = max(0, start_line - _QUERY_MARGIN_LINES)
        window_end = min(line_count - 1, end_line + _QUERY_MARGIN_LINES)
        return (window_start, window_end)

    def _query_capture_ranges(self, line_ranges: list[tuple[int, int]]) -> dict[int, list[_CaptureSpan]]:
        if self._tree is None or self._query is None:
            return {}
        lines = self._source_text.split("\n")
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
                token_name = self._resolve_token_name(capture_name)
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

        self._add_local_semantic_spans(
            lines=lines,
            merged_ranges=merged_ranges,
            spans_by_line=spans_by_line,
            seen_by_line=seen_by_line,
        )

        if self._language_key == "markdown":
            self._add_markdown_lexical_spans(
                lines=lines,
                merged_ranges=merged_ranges,
                spans_by_line=spans_by_line,
                seen_by_line=seen_by_line,
            )

        if self._language_key == "jsonc":
            self._add_jsonc_comment_spans(
                lines=lines,
                merged_ranges=merged_ranges,
                spans_by_line=spans_by_line,
                seen_by_line=seen_by_line,
            )

        self._add_injection_spans(
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
            if TreeSitterHighlighter._capture_priority(span) <= TreeSitterHighlighter._capture_priority(existing_span):
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
        if self._tree is None or self._query is None:
            return []
        raw_captures: Any
        if self._query_supports_range_kwargs is not False:
            try:
                raw_captures = self._query.captures(
                    self._tree.root_node,
                    start_point=(start_line, 0),
                    end_point=(end_line + 1, 0),
                )
                self._query_supports_range_kwargs = True
            except TypeError:
                self._query_supports_range_kwargs = False
                raw_captures = self._query.captures(self._tree.root_node)
        else:
            raw_captures = self._query.captures(self._tree.root_node)
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
                    if TreeSitterHighlighter._node_intersects_line_range(node, start_line, end_line):
                        normalized.append((node, capture_name))
            return normalized
        for node, capture_name in raw_captures:
            if TreeSitterHighlighter._node_intersects_line_range(node, start_line, end_line):
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
        if self._language_key != "python":
            return token_name
        node_text = self._node_text(node=node, lines=lines)
        if not node_text:
            return token_name
        if capture_name in {"variable", "variable.def", "parameter"} and node_text in _PYTHON_SPECIAL_VARIABLES:
            return "builtin"
        if capture_name == "function.call" and node_text in _PYTHON_BUILTIN_FUNCTIONS:
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
                    self._append_capture_span(
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
                    self._append_capture_span(
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
                        self._append_capture_span(
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
                self._append_capture_span(
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
            for line_number, span in self._build_spans_for_node(
                node=point_node,
                token_name=token_name,
                lines=lines,
                capture_name=token_name,
                origin="locals",
            ):
                self._append_capture_span(
                    spans_by_line=spans_by_line,
                    seen_by_line=seen_by_line,
                    line_number=line_number,
                    span=span,
                )

    def _add_injection_spans(
        self,
        *,
        lines: list[str],
        merged_ranges: list[tuple[int, int]],
        spans_by_line: dict[int, list[_CaptureSpan]],
        seen_by_line: dict[int, dict[tuple[int, int], int]],
    ) -> None:
        if self._tree is None or self._injections_query is None or self._injection_depth >= _MAX_INJECTION_DEPTH:
            return
        try:
            matches = self._injections_query.matches(self._tree.root_node)
        except Exception:  # pragma: no cover - defensive path
            _LOGGER.warning("Failed to evaluate injections query for %s.", self._language_key, exc_info=True)
            return
        for pattern_index, capture_map in matches:
            language_name = self._resolve_injection_language(pattern_index=pattern_index, capture_map=capture_map, lines=lines)
            if language_name is None:
                continue
            resolved_language = self._registry.resolve_for_injection_name(language_name)
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
                    self._append_capture_span(
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
            language_name = self._node_text(node=language_nodes[0], lines=lines).strip()
            if language_name:
                return language_name
        settings = self._query_settings(self._injections_query, pattern_index)
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
        embedded_source = self._source_text.encode("utf-8")[int(content_node.start_byte) : int(content_node.end_byte)].decode(
            "utf-8",
            errors="ignore",
        )
        if not embedded_source.strip():
            return
        temp_document = QTextDocument()
        temp_document.setPlainText(embedded_source)
        embedded_highlighter = TreeSitterHighlighter(
            temp_document,
            resolved_language=resolved_language,
            is_dark=self._is_dark,
            syntax_palette=dict(self._palette),
            injection_depth=self._injection_depth + 1,
        )
        embedded_highlighter.rehighlight()
        embedded_highlighter._ensure_tree_and_cache()
        parent_line = int(content_node.start_point[0])
        parent_col = self._byte_col_to_char_col(lines[parent_line], int(content_node.start_point[1])) if lines else 0
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

    def _resolve_token_name(self, capture_name: str) -> str | None:
        direct = _CAPTURE_TOKEN_MAP.get(capture_name)
        if direct is not None:
            return direct
        root_name = capture_name.split(".", 1)[0]
        return _CAPTURE_TOKEN_MAP.get(root_name)

    def describe_position(self, line_number: int, column: int) -> str:
        self._ensure_tree_and_cache()
        lines = self._source_text.split("\n")
        bounded_line = max(0, min(line_number, max(0, len(lines) - 1)))
        line_text = lines[bounded_line] if lines else ""
        bounded_column = max(0, min(column, len(line_text)))
        byte_col = self._char_to_byte_offset(line_text, bounded_column)
        active_spans = [
            span
            for span in self._capture_cache.get(bounded_line, [])
            if span.start_col <= bounded_column < span.end_col
        ]
        active_span = max(active_spans, key=self._capture_priority) if active_spans else None
        node = self._descendant_node_at_point(line_number=bounded_line, byte_col=byte_col)
        lines_out = [
            f"Language: {self._language_display_name} ({self._language_key})",
            "Engine: tree-sitter",
            f"Mode: {self._effective_mode()}",
            f"Line: {bounded_line + 1}",
            f"Column: {bounded_column + 1}",
        ]
        if node is not None:
            lines_out.append(f"Node: {node.type}")
        if active_span is not None:
            lines_out.append(f"Token: {active_span.token_name}")
            if active_span.capture_name:
                lines_out.append(f"Capture: {active_span.capture_name}")
            lines_out.append(f"Origin: {active_span.origin}")
            token_format = self._format(active_span.token_name)
            if token_format is not None:
                color_name = token_format.foreground().color().name().lower()
                if color_name:
                    lines_out.append(f"Color: {color_name}")
        else:
            lines_out.append("Token: plain_text")
        capture_details = self._capture_descriptions_at_point(line_number=bounded_line, byte_col=byte_col, lines=lines)
        if capture_details:
            lines_out.append("Matches:")
            lines_out.extend(f"- {detail}" for detail in capture_details)
        diagnostics = self.query_diagnostics()
        if diagnostics:
            lines_out.append("Diagnostics:")
            lines_out.extend(f"- {diagnostic.query_kind}: {diagnostic.message}" for diagnostic in diagnostics)
        return "\n".join(lines_out)

    def _descendant_node_at_point(self, *, line_number: int, byte_col: int) -> Any | None:
        if self._tree is None:
            return None
        root_node = self._tree.root_node
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
            token_name = self._resolve_token_name(capture_name)
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

    def _effective_mode(self) -> str:
        return effective_highlighting_mode(
            adaptive_mode=self._highlighting_adaptive_mode,
            document_size=len(self._source_text),
            reduced_threshold_chars=self._highlighting_reduced_threshold_chars,
            lexical_only_threshold_chars=self._highlighting_lexical_only_threshold_chars,
        )

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

    def _rehighlight_line_window(self, start_line: int, end_line: int) -> None:
        document = self.document()
        if document is None:
            return
        block = document.findBlockByNumber(start_line)
        while block.isValid() and block.blockNumber() <= end_line:
            self.rehighlightBlock(block)
            block = block.next()
