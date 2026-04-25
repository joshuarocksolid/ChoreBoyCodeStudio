from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from app.bootstrap.logging_setup import get_subsystem_logger
from app.core import constants
from app.editors.editor_overlay_policy import effective_highlighting_mode
from app.editors.syntax_engine import TokenStyle, ThemedSyntaxHighlighter
from app.treesitter.capture_pipeline import (
    _CAPTURE_TOKEN_MAP,
    _CaptureSpan,
    _PendingEdit,
    TreeSitterCapturePipelineMixin,
)
from app.treesitter.injection_highlights import TreeSitterInjectionMixin
from app.treesitter.jsonc_lexical import TreeSitterJsoncLexicalMixin
from app.treesitter.language_registry import TreeSitterResolvedLanguage, default_tree_sitter_language_registry
from app.treesitter.local_semantics import _LocalDefinition, _LocalReference, TreeSitterLocalSemanticsMixin
from app.treesitter.markdown_lexical import TreeSitterMarkdownLexicalMixin

_LOGGER = get_subsystem_logger("treesitter")


@dataclass(frozen=True)
class TreeSitterQueryDiagnostic:
    language_key: str
    query_kind: str
    message: str
    traceback: str


class TreeSitterHighlighter(
    TreeSitterCapturePipelineMixin,
    TreeSitterLocalSemanticsMixin,
    TreeSitterInjectionMixin,
    TreeSitterJsoncLexicalMixin,
    TreeSitterMarkdownLexicalMixin,
    ThemedSyntaxHighlighter,
):
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
        self._is_disposed = False
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
        if document is None:
            self._is_disposed = True
        previous_document = self.document()
        if previous_document is not None:
            try:
                previous_document.contentsChange.disconnect(self._on_contents_change)
            except RuntimeError:
                _LOGGER.debug("contentsChange signal was already disconnected")
            try:
                previous_document.contentsChanged.disconnect(self._on_contents_changed)
            except RuntimeError:
                _LOGGER.debug("contentsChanged signal was already disconnected")
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
            self._is_disposed = False
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
        if self._is_disposed:
            return
        self._ensure_tree_and_cache()
        try:
            block_line = self.currentBlock().blockNumber()
        except RuntimeError:
            self._is_disposed = True
            return
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


    def _create_embedded_highlighter(
        self,
        document,  # type: ignore[no-untyped-def]
        *,
        resolved_language: TreeSitterResolvedLanguage,
        injection_depth: int,
    ) -> "TreeSitterHighlighter":
        return TreeSitterHighlighter(
            document,
            resolved_language=resolved_language,
            is_dark=self._is_dark,
            syntax_palette=dict(self._palette),
            injection_depth=injection_depth,
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

    def _effective_mode(self) -> str:
        return effective_highlighting_mode(
            adaptive_mode=self._highlighting_adaptive_mode,
            document_size=len(self._source_text),
            reduced_threshold_chars=self._highlighting_reduced_threshold_chars,
            lexical_only_threshold_chars=self._highlighting_lexical_only_threshold_chars,
        )

    def _rehighlight_line_window(self, start_line: int, end_line: int) -> None:
        document = self.document()
        if document is None:
            return
        block = document.findBlockByNumber(start_line)
        while block.isValid() and block.blockNumber() <= end_line:
            self.rehighlightBlock(block)
            block = block.next()
