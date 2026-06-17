"""Custom code editor widget with gutter, breakpoints, and syntax highlighting."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from PySide2.QtCore import QPoint, Qt
from PySide2.QtGui import QColor, QTextCursor
from PySide2.QtWidgets import QPlainTextEdit, QWidget

from app.bootstrap.logging_setup import get_subsystem_logger
from app.core import constants
from app.editors.code_editor_bracket_overlay_mixin import CodeEditorBracketOverlayMixin
from app.editors.code_editor_chrome_mixin import CodeEditorChromeMixin
from app.editors.code_editor_diagnostics import CodeEditorDiagnosticsMixin
from app.editors.code_editor_editing import CodeEditorEditingMixin
from app.editors.code_editor_extra_selections_overlay_mixin import CodeEditorExtraSelectionsOverlayMixin
from app.editors.code_editor_paste_hint_mixin import CodeEditorPasteHintMixin
from app.editors.code_editor_search import CodeEditorSearchMixin
from app.editors.code_editor_semantics import CodeEditorSemanticsMixin
from app.editors.completion_popup import CompletionController
from app.editors.syntax_engine import syntax_palette_from_tokens
from app.editors.syntax_registry import default_syntax_highlighter_registry
from app.intelligence.completion_models import CompletionItem
from app.intelligence.diagnostics_service import DiagnosticSeverity
from app.shell.theme_tokens import ShellThemeTokens

DEFAULT_TAB_WIDTH = 4
DEFAULT_FONT_POINT_SIZE = 10
DEFAULT_FONT_FAMILY = "monospace"
DEFAULT_COMPLETION_MIN_CHARS = 2
LARGE_FILE_CHAR_THRESHOLD = constants.UI_INTELLIGENCE_HIGHLIGHTING_REDUCED_THRESHOLD_CHARS_DEFAULT


class CodeEditorWidget(
    CodeEditorChromeMixin,
    CodeEditorBracketOverlayMixin,
    CodeEditorDiagnosticsMixin,
    CodeEditorSemanticsMixin,
    CodeEditorSearchMixin,
    CodeEditorEditingMixin,
    CodeEditorPasteHintMixin,
    CodeEditorExtraSelectionsOverlayMixin,
    QPlainTextEdit,
):
    """QPlainTextEdit extension with common developer QoL affordances."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._logger = get_subsystem_logger("editors")
        self._active_file_path: str | None = None
        self._language_override_key: str | None = None
        self._highlighting_adaptive_mode = constants.HIGHLIGHTING_MODE_NORMAL
        self._highlighting_reduced_threshold_chars = constants.UI_INTELLIGENCE_HIGHLIGHTING_REDUCED_THRESHOLD_CHARS_DEFAULT
        self._highlighting_lexical_only_threshold_chars = (
            constants.UI_INTELLIGENCE_HIGHLIGHTING_LEXICAL_ONLY_THRESHOLD_CHARS_DEFAULT
        )
        self._operation_latency_sink: Callable[[str, float, str | None], None] | None = None
        self._init_chrome_state()
        self._init_bracket_overlay_state()
        self._init_paste_hint_state()
        self._init_extra_selections_overlay_state()
        self._highlighter: object | None = None
        self._syntax_theme_refresh_pending = False
        self._syntax_registry = default_syntax_highlighter_registry()
        self._syntax_palette: dict[str, str] = {}
        self._tab_width = DEFAULT_TAB_WIDTH
        self._comment_prefix = "#"
        self._indent_style = "spaces"
        self._indent_size = DEFAULT_TAB_WIDTH
        self._cached_theme_tokens: ShellThemeTokens | None = None
        self._completion_requester: Callable[[str, int, bool, int, str, str], None] | None = None
        self._completion_resolve_requester: Callable[[CompletionItem, str, int, int], None] | None = None
        self._completion_accepted_callback: Callable[[CompletionItem], None] | None = None
        self._hover_requester: Callable[[str, int, int], None] | None = None
        self._hover_tooltip_enabled = constants.UI_EDITOR_HOVER_TOOLTIP_ENABLED_DEFAULT
        self._signature_help_provider: Callable[[str, int], str | None] | None = None
        self._signature_help_requester: Callable[[str, int, int], None] | None = None
        self._completion_enabled = True
        self._completion_auto_trigger = True
        self._completion_auto_trigger_period = True
        self._completion_min_chars = DEFAULT_COMPLETION_MIN_CHARS
        self._completion_request_generation = 0
        self._pending_completion_trigger_character = ""
        self._active_completion_prefix = ""
        self._hover_request_generation = 0
        self._hover_request_global_pos: QPoint | None = None
        self._signature_help_request_generation = 0
        self._completion_popup = CompletionController(self)
        self._completion_popup.set_widget(self)
        self._completion_popup.activated.connect(self._insert_completion_from_item)
        self._completion_popup.selection_changed.connect(self._request_completion_item_resolution)

        self._is_dark = False
        self._diag_error_color = QColor()
        self._diag_warning_color = QColor()
        self._diag_info_color = QColor()
        self._diagnostic_selections: list[Any] = []
        self._diagnostic_lines: dict[int, DiagnosticSeverity] = {}
        self._diagnostic_ranges: list[tuple[int, int, str]] = []

        self.setMouseTracking(True)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self.cursorPositionChanged.connect(self._maybe_dismiss_paste_hint_for_cursor)
        self.verticalScrollBar().valueChanged.connect(self._handle_viewport_changed)
        self._highlight_current_line()
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.set_editor_preferences(
            tab_width=DEFAULT_TAB_WIDTH,
            font_point_size=DEFAULT_FONT_POINT_SIZE,
            font_family=DEFAULT_FONT_FAMILY,
            indent_style="spaces",
            indent_size=DEFAULT_TAB_WIDTH,
        )

    def apply_theme(self, tokens: ShellThemeTokens, *, defer_syntax_rehighlight: bool = False) -> None:
        started_at = time.perf_counter()
        self._is_dark = tokens.is_dark
        self._cached_theme_tokens = tokens
        self._completion_popup.apply_theme(tokens)
        self._apply_paste_hint_theme(tokens)
        self._apply_chrome_theme(tokens)
        self._apply_extra_selections_overlay_theme(tokens)
        self._apply_bracket_overlay_theme(tokens)
        if tokens.diag_error_color:
            self._diag_error_color = QColor(tokens.diag_error_color)
        if tokens.diag_warning_color:
            self._diag_warning_color = QColor(tokens.diag_warning_color)
        if tokens.diag_info_color:
            self._diag_info_color = QColor(tokens.diag_info_color)
        self._syntax_palette = syntax_palette_from_tokens(tokens)
        self._mark_overlay_cache_dirty()
        self._line_number_area.update()
        self._highlight_current_line()
        rehighlight_syntax = self.isVisible() and not defer_syntax_rehighlight
        self._syntax_registry.apply_theme(
            self._highlighter,
            is_dark=tokens.is_dark,
            syntax_palette=self._syntax_palette,
            rehighlight=rehighlight_syntax,
        )
        self._syntax_theme_refresh_pending = self._highlighter is not None and not rehighlight_syntax
        self._apply_highlighter_runtime_policy()
        self._notify_highlighter_viewport_lines()
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        self._emit_operation_latency("editor_theme_apply_ms", elapsed_ms)

    def flush_pending_syntax_theme_refresh(self) -> None:
        if not self._syntax_theme_refresh_pending or self._highlighter is None:
            return
        if hasattr(self._highlighter, "rehighlight"):
            self._highlighter.rehighlight()  # type: ignore[union-attr]
        self._syntax_theme_refresh_pending = False
        self._notify_highlighter_viewport_lines()

    def set_operation_latency_sink(
        self,
        sink: Callable[[str, float, str | None], None] | None,
    ) -> None:
        self._operation_latency_sink = sink

    def _emit_operation_latency(self, metric_name: str, elapsed_ms: float) -> None:
        if self._operation_latency_sink is None:
            return
        self._operation_latency_sink(metric_name, elapsed_ms, self._active_file_path)

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
        self._highlighting_adaptive_mode = (
            adaptive_mode if adaptive_mode in valid_modes else constants.HIGHLIGHTING_MODE_NORMAL
        )
        self._highlighting_reduced_threshold_chars = max(1, int(reduced_threshold_chars))
        self._highlighting_lexical_only_threshold_chars = max(
            self._highlighting_reduced_threshold_chars,
            int(lexical_only_threshold_chars),
        )
        self._apply_highlighter_runtime_policy()
        self._notify_highlighter_viewport_lines()
        self._mark_overlay_cache_dirty()
        self._refresh_extra_selections()

    def _apply_highlighter_runtime_policy(self) -> None:
        if self._highlighter is None:
            return
        if hasattr(self._highlighter, "set_highlighting_policy"):
            self._highlighter.set_highlighting_policy(  # type: ignore[union-attr]
                adaptive_mode=self._highlighting_adaptive_mode,
                reduced_threshold_chars=self._highlighting_reduced_threshold_chars,
                lexical_only_threshold_chars=self._highlighting_lexical_only_threshold_chars,
            )

    def _notify_highlighter_viewport_lines(self) -> None:
        if self._highlighter is None:
            return
        if not hasattr(self._highlighter, "set_viewport_lines"):
            return
        document = self.document()
        if document is None:
            return
        top_cursor = self.cursorForPosition(QPoint(0, 0))
        bottom_cursor = self.cursorForPosition(QPoint(0, max(0, self.viewport().height() - 1)))
        start_line = top_cursor.blockNumber()
        end_line = max(start_line, bottom_cursor.blockNumber())
        self._highlighter.set_viewport_lines(start_line, end_line)  # type: ignore[union-attr]

    def _handle_viewport_changed(self, _value: int) -> None:
        self._notify_highlighter_viewport_lines()
        self._refresh_extra_selections()

    def set_language_for_path(self, file_path: str) -> None:
        started_at = time.perf_counter()
        document = self.document()
        previous_highlighter = self._highlighter
        if hasattr(previous_highlighter, "setDocument"):
            previous_highlighter.setDocument(None)  # type: ignore[union-attr]

        sample_lines: list[str] = []
        block = document.firstBlock()
        while block.isValid() and len(sample_lines) < 4:
            sample_lines.append(block.text())
            block = block.next()
        self._highlighter = self._syntax_registry.create_for_path(
            file_path=file_path,
            document=document,
            is_dark=self._is_dark,
            syntax_palette=self._syntax_palette,
            sample_text="\n".join(sample_lines),
            language_override_key=self._language_override_key,
        )
        self._apply_highlighter_runtime_policy()
        self._notify_highlighter_viewport_lines()
        self._active_file_path = file_path
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        self._emit_operation_latency("editor_language_attach_ms", elapsed_ms)

    def set_language_override(self, language_key: str | None) -> None:
        normalized = None if language_key is None else language_key.strip() or None
        if normalized == self._language_override_key:
            return
        self._language_override_key = normalized
        if self._active_file_path is not None:
            self.set_language_for_path(self._active_file_path)

    def clear_language_override(self) -> None:
        self.set_language_override(None)

    def language_override_key(self) -> str | None:
        return self._language_override_key

    def active_language_key(self) -> str | None:
        if self._highlighter is not None and hasattr(self._highlighter, "language_key"):
            return self._highlighter.language_key()  # type: ignore[union-attr]
        return self._language_override_key

    def available_language_modes(self) -> list[tuple[str, str]]:
        return self._syntax_registry.available_language_modes()

    def describe_token_under_cursor(self) -> str:
        cursor = self.textCursor()
        block_number = cursor.blockNumber()
        column = cursor.positionInBlock()
        if self._highlighter is None:
            lines = [
                "Language: Plain Text",
                "Engine: none",
                f"Line: {block_number + 1}",
                f"Column: {column + 1}",
            ]
            if self._language_override_key is not None:
                lines.append(f"Override: {self._language_override_key}")
            return "\n".join(lines)
        if hasattr(self._highlighter, "describe_position"):
            description = self._highlighter.describe_position(block_number, column)  # type: ignore[union-attr]
        else:
            language_key = self.active_language_key() or "plain_text"
            description = "\n".join(
                [
                    f"Language: {language_key}",
                    "Engine: unknown",
                    f"Line: {block_number + 1}",
                    f"Column: {column + 1}",
                ]
            )
        if self._language_override_key is None:
            return description
        return f"{description}\nOverride: {self._language_override_key}"

    def set_editor_preferences(
        self,
        *,
        tab_width: int,
        font_point_size: int,
        font_family: str = DEFAULT_FONT_FAMILY,
        indent_style: str = "spaces",
        indent_size: int = DEFAULT_TAB_WIDTH,
        hover_tooltip_enabled: bool = constants.UI_EDITOR_HOVER_TOOLTIP_ENABLED_DEFAULT,
        auto_reindent_flat_python_paste: bool = constants.UI_EDITOR_AUTO_REINDENT_FLAT_PYTHON_PASTE_DEFAULT,
    ) -> None:
        """Apply tab width, font family, and font-size preferences."""
        self._tab_width = max(2, tab_width)
        self._indent_style = "tabs" if indent_style == "tabs" else "spaces"
        self._indent_size = max(1, indent_size)
        self._hover_tooltip_enabled = bool(hover_tooltip_enabled)
        self._auto_reindent_flat_python_paste = bool(auto_reindent_flat_python_paste)
        font = self.font()
        font.setFamily(font_family)
        font.setPointSize(max(8, font_point_size))
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * self._tab_width)

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        super().showEvent(event)
        self.flush_pending_syntax_theme_refresh()

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        self._destroy_paste_hint_overlay_on_close()
        super().closeEvent(event)

    def go_to_line(self, line_number: int) -> None:
        safe_line = max(1, line_number)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.Start)
        cursor.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor, safe_line - 1)
        self.setTextCursor(cursor)
        self.setFocus()

    def word_under_cursor(self) -> str:
        cursor = self.textCursor()
        cursor.select(QTextCursor.WordUnderCursor)
        return cursor.selectedText().strip()

    def selected_text(self) -> str:
        return self.textCursor().selectedText().replace("\u2029", "\n")
