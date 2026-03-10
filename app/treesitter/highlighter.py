from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterator

from app.core import constants
from app.editors.editor_overlay_policy import effective_highlighting_mode
from app.editors.syntax_engine import TokenStyle, ThemedSyntaxHighlighter

_QUERY_MARGIN_LINES = 220
_RANGE_EXPANSION_LINES = 3
_ESCAPE_SEQUENCE_PATTERN = re.compile(r"\\(?:[0-7]{1,3}|x[0-9A-Fa-f]{1,2}|u[0-9A-Fa-f]{1,4}|U[0-9A-Fa-f]{1,8}|N\{[^}\n]*\}|.)")
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

_CAPTURE_TOKEN_MAP: dict[str, str] = {
    "keyword": "keyword",
    "keyword.control": "keyword_control",
    "keyword.import": "keyword_import",
    "escape": "escape",
    "comment": "comment",
    "string": "string",
    "number": "number",
    "boolean": "number",
    "constant": "semantic_constant",
    "constant.builtin": "semantic_constant",
    "type": "class",
    "function.def": "function",
    "function.call": "semantic_function",
    "method.call": "semantic_method",
    "class.def": "class",
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


class TreeSitterHighlighter(ThemedSyntaxHighlighter):
    TOKEN_STYLES = {
        "keyword": TokenStyle("keyword", bold=True),
        "keyword_control": TokenStyle("keyword_control", bold=True),
        "keyword_import": TokenStyle("keyword_import"),
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
        language: object,
        query_source: str,
        language_key: str,
        is_dark: bool = False,
        syntax_palette: dict[str, str] | None = None,
    ) -> None:
        super().__init__(document, is_dark=is_dark, syntax_palette=syntax_palette)
        import tree_sitter

        self._language_key = language_key
        self._language = language
        self._parser: Any = tree_sitter.Parser()
        self._parser.set_language(language)
        self._query: Any | None
        try:
            self._query = language.query(query_source)
        except Exception:
            self._query = None
        self._tree: Any | None = None
        self._source_text = document.toPlainText() if document is not None else ""
        self._pending_edits: list[_PendingEdit] = []
        self._capture_cache: dict[int, list[_CaptureSpan]] = {}
        self._highlighting_adaptive_mode = constants.HIGHLIGHTING_MODE_NORMAL
        self._highlighting_reduced_threshold_chars = constants.UI_INTELLIGENCE_HIGHLIGHTING_REDUCED_THRESHOLD_CHARS_DEFAULT
        self._highlighting_lexical_only_threshold_chars = constants.UI_INTELLIGENCE_HIGHLIGHTING_LEXICAL_ONLY_THRESHOLD_CHARS_DEFAULT
        self._viewport_lines = (0, 0)
        self._dirty = True
        self._viewport_dirty = True
        self._last_synced_revision: int = document.revision() if document is not None else -1
        if document is not None:
            document.contentsChange.connect(self._on_contents_change)

    def setDocument(self, document) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        previous_document = self.document()
        if previous_document is not None:
            try:
                previous_document.contentsChange.disconnect(self._on_contents_change)
            except Exception:
                pass
        super().setDocument(document)
        self._tree = None
        self._pending_edits.clear()
        self._capture_cache.clear()
        self._source_text = document.toPlainText() if document is not None else ""
        self._dirty = True
        self._viewport_dirty = True
        self._last_synced_revision = document.revision() if document is not None else -1
        if document is not None:
            document.contentsChange.connect(self._on_contents_change)

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
        document = self.document()
        if document is None:
            return
        new_source = document.toPlainText()
        old_source = self._source_text
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
        start_line = pending_edit.start_point[0]
        end_line = pending_edit.new_end_point[0]
        rehighlight_start = max(0, start_line - _RANGE_EXPANSION_LINES)
        rehighlight_end = max(rehighlight_start, end_line + _RANGE_EXPANSION_LINES)
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
        full_rebuild = old_tree is None
        if self._dirty:
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
            full_rebuild = not used_old_tree
            if used_old_tree and old_tree is not None:
                changed_ranges = old_tree.changed_ranges(new_tree)
        elif self._tree is None:
            self._tree, _ = self._parse_with_optional_tree(None)
            if self._tree is None:
                return
            full_rebuild = True

        self._update_capture_cache(changed_ranges=changed_ranges, full_rebuild=full_rebuild)
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

    def _update_capture_cache(self, *, changed_ranges: list[Any], full_rebuild: bool) -> None:
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
        seen_by_line: dict[int, set[tuple[int, int]]] = {}

        for start_line, end_line in merged_ranges:
            bounded_start = max(0, min(start_line, max_line))
            bounded_end = max(bounded_start, min(end_line, max_line))
            captures = self._query.captures(
                self._tree.root_node,
                start_point=(bounded_start, 0),
                end_point=(bounded_end + 1, 0),
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
                for line_number, span in self._build_spans_for_node(node=node, token_name=token_name, lines=lines):
                    if line_number < bounded_start or line_number > bounded_end:
                        continue
                    if line_number not in spans_by_line:
                        spans_by_line[line_number] = []
                        seen_by_line[line_number] = set()
                    span_key = (span.start_col, span.end_col)
                    if span_key in seen_by_line[line_number]:
                        continue
                    seen_by_line[line_number].add(span_key)
                    spans_by_line[line_number].append(span)
                    if token_name == "string":
                        line_text = lines[line_number]
                        for escape_span in self._lex_escape_spans(
                            line_text=line_text,
                            start_col=span.start_col,
                            end_col=span.end_col,
                        ):
                            escape_key = (escape_span.start_col, escape_span.end_col)
                            if escape_key in seen_by_line[line_number]:
                                continue
                            seen_by_line[line_number].add(escape_key)
                            spans_by_line[line_number].append(escape_span)

        for line_number in list(spans_by_line.keys()):
            spans_by_line[line_number].sort(key=lambda value: (value.start_col, value.end_col, value.token_name))
        return spans_by_line

    def _build_spans_for_node(
        self,
        *,
        node: Any,
        token_name: str,
        lines: list[str],
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
                yield (start_line, _CaptureSpan(token_name=token_name, start_col=start_col, end_col=end_col))
            return

        first_line_text = lines[start_line]
        first_start = self._byte_col_to_char_col(first_line_text, start_byte_col)
        first_end = len(first_line_text)
        if first_end > first_start:
            yield (start_line, _CaptureSpan(token_name=token_name, start_col=first_start, end_col=first_end))

        for line_number in range(start_line + 1, end_line):
            middle_line_text = lines[line_number]
            middle_end = len(middle_line_text)
            if middle_end > 0:
                yield (line_number, _CaptureSpan(token_name=token_name, start_col=0, end_col=middle_end))

        last_line_text = lines[end_line]
        last_end = self._byte_col_to_char_col(last_line_text, end_byte_col)
        if last_end > 0:
            yield (end_line, _CaptureSpan(token_name=token_name, start_col=0, end_col=last_end))

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
            yield _CaptureSpan(token_name="escape", start_col=escape_start, end_col=escape_end)

    def _resolve_token_name(self, capture_name: str) -> str | None:
        direct = _CAPTURE_TOKEN_MAP.get(capture_name)
        if direct is not None:
            return direct
        root_name = capture_name.split(".", 1)[0]
        return _CAPTURE_TOKEN_MAP.get(root_name)

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
