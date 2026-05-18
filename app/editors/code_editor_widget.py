"""Custom code editor widget with gutter, breakpoints, and syntax highlighting."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, cast

from PySide2.QtCore import QMimeData, QPoint, Qt
from PySide2.QtGui import QColor, QContextMenuEvent, QTextCursor, QTextFormat
from PySide2.QtWidgets import QApplication, QMenu, QPlainTextEdit, QTextEdit, QWidget

from app.bootstrap.logging_setup import get_subsystem_logger
from app.core import constants
from app.editors.code_editor_bracket_overlay_mixin import CodeEditorBracketOverlayMixin
from app.editors.completion_popup import CompletionController
from app.editors.code_editor_chrome_mixin import CodeEditorChromeMixin
from app.editors.code_editor_diagnostics import CodeEditorDiagnosticsMixin
from app.editors.code_editor_editing import CodeEditorEditingMixin
from app.editors.code_editor_search import CodeEditorSearchMixin
from app.editors.code_editor_semantics import CodeEditorSemanticsMixin
from app.editors.editor_overlay_policy import (
    effective_highlighting_mode,
    is_large_document,
    visible_document_window,
)
from app.editors.text_editing import (
    FlatPythonIndentRepairResult,
    auto_paste_accepts_repair,
    looks_like_flat_python_paste,
    repair_flat_python_indentation,
)
from app.editors.paste_hint_overlay import PasteHintOverlay
from app.editors.syntax_registry import default_syntax_highlighter_registry, syntax_palette_from_tokens
from app.intelligence.completion_models import CompletionItem
from app.intelligence.diagnostics_service import CodeDiagnostic, DiagnosticSeverity
from app.intelligence.latency_tracker import RollingLatencyTracker
from app.shell.theme_tokens import ShellThemeTokens

DEFAULT_TAB_WIDTH = 4
DEFAULT_FONT_POINT_SIZE = 10
DEFAULT_FONT_FAMILY = "monospace"
DEFAULT_COMPLETION_MIN_CHARS = 2
LARGE_FILE_CHAR_THRESHOLD = constants.UI_INTELLIGENCE_HIGHLIGHTING_REDUCED_THRESHOLD_CHARS_DEFAULT
MAX_SEARCH_SELECTIONS_LARGE_FILE = 400
MAX_OVERLAY_SELECTIONS_LARGE_FILE = 700
VIEWPORT_CHAR_MARGIN = 8000
LANGUAGE_ATTACH_WARNING_MS = 80.0
THEME_APPLY_WARNING_MS = 90.0
OVERLAY_REFRESH_WARNING_MS = 24.0


class CodeEditorWidget(
    CodeEditorChromeMixin,
    CodeEditorBracketOverlayMixin,
    CodeEditorDiagnosticsMixin,
    CodeEditorSemanticsMixin,
    CodeEditorSearchMixin,
    CodeEditorEditingMixin,
    QPlainTextEdit,
):
    """QPlainTextEdit extension with common developer QoL affordances."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._logger = get_subsystem_logger("editors")
        self._metrics_logging_enabled = False
        self._active_file_path: str | None = None
        self._language_override_key: str | None = None
        self._highlighting_adaptive_mode = constants.HIGHLIGHTING_MODE_NORMAL
        self._highlighting_reduced_threshold_chars = constants.UI_INTELLIGENCE_HIGHLIGHTING_REDUCED_THRESHOLD_CHARS_DEFAULT
        self._highlighting_lexical_only_threshold_chars = (
            constants.UI_INTELLIGENCE_HIGHLIGHTING_LEXICAL_ONLY_THRESHOLD_CHARS_DEFAULT
        )
        self._language_attach_latency = RollingLatencyTracker("editor_language_attach_ms", window_size=120, snapshot_interval=30)
        self._theme_apply_latency = RollingLatencyTracker("editor_theme_apply_ms", window_size=120, snapshot_interval=30)
        self._overlay_refresh_latency = RollingLatencyTracker("editor_overlay_refresh_ms", window_size=180, snapshot_interval=75)
        self._init_chrome_state()
        self._init_bracket_overlay_state()
        self._highlighter: object | None = None
        self._syntax_theme_refresh_pending = False
        self._syntax_registry = default_syntax_highlighter_registry()
        self._syntax_palette: dict[str, str] = {}
        self._tab_width = DEFAULT_TAB_WIDTH
        self._comment_prefix = "#"
        self._indent_style = "spaces"
        self._indent_size = DEFAULT_TAB_WIDTH
        self._auto_reindent_flat_python_paste = constants.UI_EDITOR_AUTO_REINDENT_FLAT_PYTHON_PASTE_DEFAULT
        self._last_paste_range: tuple[int, int] | None = None
        self._paste_hint_overlay: PasteHintOverlay | None = None
        self._paste_hint_dismissed_this_session: bool = False
        self._paste_hint_anchor_block: int | None = None
        self._paste_hint_enable_always_callback: Callable[[], object] | None = None
        self._paste_hint_status_callback: Callable[[FlatPythonIndentRepairResult], object] | None = None
        self._cached_theme_tokens: ShellThemeTokens | None = None
        self._completion_provider: Callable[[str, str, int, bool], list[CompletionItem]] | None = None
        self._completion_requester: Callable[[str, str, int, bool, int, str, str], None] | None = None
        self._completion_resolve_requester: Callable[[CompletionItem, str, int, int], None] | None = None
        self._completion_accepted_callback: Callable[[CompletionItem], None] | None = None
        self._hover_provider: Callable[[str, int], str | None] | None = None
        self._hover_requester: Callable[[str, int, int], None] | None = None
        self._hover_tooltip_enabled = constants.UI_EDITOR_HOVER_TOOLTIP_ENABLED_DEFAULT
        self._signature_help_provider: Callable[[str, int], str | None] | None = None
        self._signature_help_requester: Callable[[str, int, int], None] | None = None
        self._completion_enabled = True
        self._completion_auto_trigger = True
        self._completion_min_chars = DEFAULT_COMPLETION_MIN_CHARS
        self._completion_request_generation = 0
        self._pending_completion_trigger_character = ""
        self._hover_request_generation = 0
        self._hover_request_global_pos: QPoint | None = None
        self._signature_help_request_generation = 0
        self._completion_popup = CompletionController(self)
        self._completion_popup.set_widget(self)
        self._completion_popup.activated.connect(self._insert_completion_from_item)
        self._completion_popup.selection_changed.connect(self._request_completion_item_resolution)

        self._is_dark = False
        self._line_highlight = QColor("#EEF7FF")

        self._search_match_bg = QColor("#FFE066")
        self._search_current_match_bg = QColor("#FF922B")
        self._search_selections: list[QTextEdit.ExtraSelection] = []
        self._search_match_positions: list[tuple[int, int]] = []
        self._search_current_index: int = -1

        self._diag_error_color = QColor("#E03131")
        self._diag_warning_color = QColor("#D97706")
        self._diag_info_color = QColor("#3366FF")
        self._diagnostic_selections: list[QTextEdit.ExtraSelection] = []
        self._diagnostic_lines: dict[int, DiagnosticSeverity] = {}
        self._diagnostic_ranges: list[tuple[int, int, str]] = []
        self._cached_non_cursor_selections: list[QTextEdit.ExtraSelection] = []
        self._overlay_cache_dirty = True
        self._overlay_generation = 0
        self._last_applied_overlay_generation = -1
        self._last_applied_cursor_position = -1
        self._last_applied_effective_mode = ""

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

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        started_at = time.perf_counter()
        self._is_dark = tokens.is_dark
        self._cached_theme_tokens = tokens
        self._completion_popup.apply_theme(tokens)
        if self._paste_hint_overlay is not None:
            self._paste_hint_overlay.apply_theme(tokens)
        self._apply_chrome_theme(tokens)
        self._line_highlight = QColor(tokens.line_highlight)
        self._apply_bracket_overlay_theme(is_dark=tokens.is_dark)
        if tokens.search_match_bg:
            self._search_match_bg = QColor(tokens.search_match_bg)
        if tokens.search_current_match_bg:
            self._search_current_match_bg = QColor(tokens.search_current_match_bg)
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
        rehighlight_syntax = self.isVisible()
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
        self._record_latency_metric(self._theme_apply_latency, elapsed_ms, warning_threshold_ms=THEME_APPLY_WARNING_MS)

    def set_metrics_logging_enabled(self, enabled: bool) -> None:
        self._metrics_logging_enabled = enabled

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
        self._record_latency_metric(
            self._language_attach_latency,
            elapsed_ms,
            warning_threshold_ms=LANGUAGE_ATTACH_WARNING_MS,
        )

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

    def insertFromMimeData(self, source: QMimeData) -> None:  # noqa: N802 - Qt signature
        """Apply flat-Python repair when accepted, else paste literally and maybe hint."""
        pasted_text = source.text() if source.hasText() else ""
        if self._auto_reindent_flat_python_paste and pasted_text:
            result = repair_flat_python_indentation(pasted_text, indent_text=self._indent_text())
            if auto_paste_accepts_repair(result):
                self._insert_text_as_paste(result.text, prefix_subsequent_lines=True)
                if self._paste_hint_status_callback is not None:
                    self._paste_hint_status_callback(result)
                return

        start = self.textCursor().selectionStart() if self.textCursor().hasSelection() else self.textCursor().position()
        super().insertFromMimeData(source)
        end = self.textCursor().position()
        self._last_paste_range = (start, end)
        self._select_paste_range_if_multiline(start, end, self.textCursor())
        if pasted_text:
            self._maybe_show_flat_python_paste_hint(pasted_text, (start, end))

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        super().showEvent(event)
        if not self._syntax_theme_refresh_pending or self._highlighter is None:
            return
        if hasattr(self._highlighter, "rehighlight"):
            self._highlighter.rehighlight()  # type: ignore[union-attr]
        self._syntax_theme_refresh_pending = False
        self._notify_highlighter_viewport_lines()

    def _show_context_menu(self, event: QContextMenuEvent) -> None:
        """Augment the default context menu with flat-Python smart-paste actions."""
        menu = self.createStandardContextMenu(event.pos())
        try:
            self._augment_context_menu_with_flat_python_actions(menu)
            menu.exec_(event.globalPos())
        finally:
            menu.deleteLater()

    def _augment_context_menu_with_flat_python_actions(self, menu: QMenu) -> None:
        """Insert *Paste and Re-indent* / *Re-indent Selection* actions when relevant."""
        clipboard = QApplication.clipboard()
        clipboard_text = clipboard.text() if clipboard is not None else ""
        clipboard_looks_flat = bool(clipboard_text) and looks_like_flat_python_paste(clipboard_text)

        cursor = self.textCursor()
        has_selection = cursor.hasSelection()
        selection_text = cursor.selectedText().replace("\u2029", "\n") if has_selection else ""
        selection_looks_flat = bool(selection_text) and looks_like_flat_python_paste(selection_text)

        if not clipboard_looks_flat and not selection_looks_flat:
            return

        menu.addSeparator()
        if clipboard_looks_flat:
            paste_action = menu.addAction("Paste and Re-indent (Flat Python)")
            if paste_action is not None:
                paste_action.triggered.connect(self._context_menu_paste_reindent)
        if selection_looks_flat:
            reindent_action = menu.addAction("Re-indent Selection (Flat Python)")
            if reindent_action is not None:
                reindent_action.triggered.connect(self._context_menu_reindent_selection)

    def _context_menu_paste_reindent(self) -> None:
        result = self.paste_reindented_flat_python()
        if self._paste_hint_status_callback is not None:
            self._paste_hint_status_callback(result)

    def _context_menu_reindent_selection(self) -> None:
        result = self.reindent_flat_python_selection()
        if self._paste_hint_status_callback is not None:
            self._paste_hint_status_callback(result)

    def set_paste_hint_enable_always_callback(self, callback: Callable[[], object] | None) -> None:
        """Register the handler invoked when the user clicks "Always" on the paste hint."""
        self._paste_hint_enable_always_callback = callback

    def set_paste_hint_status_callback(
        self,
        callback: Callable[[FlatPythonIndentRepairResult], object] | None,
    ) -> None:
        """Register a handler that receives the repair result after any flat-Python re-indent."""
        self._paste_hint_status_callback = callback

    def has_flat_python_paste_hint_visible(self) -> bool:
        """Test helper: whether the paste-hint overlay is currently shown."""
        overlay = self._paste_hint_overlay
        if overlay is None:
            return False
        # Use isVisibleTo(parent): the overlay is a child of the editor's
        # viewport, so ``isVisible()`` reports False under the offscreen
        # platform when the parent editor itself has not been shown.
        parent_widget = overlay.parentWidget()
        return bool(overlay.isVisibleTo(parent_widget))

    def trigger_flat_python_paste_hint_reindent(self) -> None:
        """Test helper: simulate the user clicking *Re-indent* on the paste hint."""
        if self._paste_hint_overlay is None:
            return
        self._paste_hint_overlay.reindentRequested.emit()

    def trigger_flat_python_paste_hint_always(self) -> None:
        """Test helper: simulate the user clicking *Always* on the paste hint."""
        if self._paste_hint_overlay is None:
            return
        self._paste_hint_overlay.enableAlwaysRequested.emit()

    def trigger_flat_python_paste_hint_dismiss(self) -> None:
        """Test helper: simulate the user clicking the dismiss (×) button."""
        if self._paste_hint_overlay is None:
            return
        self._paste_hint_overlay.dismissed.emit()
        self._paste_hint_overlay.hide_overlay()

    def _maybe_show_flat_python_paste_hint(
        self,
        pasted_text: str,
        paste_range: tuple[int, int],
    ) -> None:
        """Show the inline paste hint when conditions warrant.

        Conditions:
          * auto-paste mode is OFF,
          * the user did not dismiss the hint this session,
          * ``looks_like_flat_python_paste`` is true on the literal text, and
          * a dry-run repair returns confidence != low.
        """
        if self._auto_reindent_flat_python_paste:
            return
        if self._paste_hint_dismissed_this_session:
            return
        if not pasted_text or not looks_like_flat_python_paste(pasted_text):
            return
        dry_run = repair_flat_python_indentation(pasted_text, indent_text=self._indent_text())
        if not dry_run.changed:
            return
        from app.editors.text_editing import FLAT_PYTHON_CONFIDENCE_LOW

        if dry_run.confidence == FLAT_PYTHON_CONFIDENCE_LOW:
            return

        overlay = self._ensure_paste_hint_overlay()
        self._paste_hint_anchor_block = self.document().findBlock(max(paste_range[0], paste_range[1] - 1)).blockNumber()
        anchor_point = self._compute_paste_hint_anchor_point(paste_range)
        overlay.show_at(self.viewport(), anchor_point)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        self._destroy_paste_hint_overlay()
        super().closeEvent(event)

    def _destroy_paste_hint_overlay(self) -> None:
        overlay = self._paste_hint_overlay
        if overlay is None:
            return
        self._paste_hint_overlay = None
        try:
            overlay.hide()
            overlay.deleteLater()
        except RuntimeError:
            # Underlying C++ object already deleted.
            pass

    def _ensure_paste_hint_overlay(self) -> PasteHintOverlay:
        overlay = self._paste_hint_overlay
        if overlay is None:
            overlay = PasteHintOverlay(self.viewport())
            overlay.reindentRequested.connect(self._handle_paste_hint_reindent)
            overlay.enableAlwaysRequested.connect(self._handle_paste_hint_always)
            overlay.dismissed.connect(self._handle_paste_hint_dismissed)
            if self._cached_theme_tokens is not None:
                overlay.apply_theme(self._cached_theme_tokens)
            self._paste_hint_overlay = overlay
        elif self._cached_theme_tokens is not None:
            overlay.apply_theme(self._cached_theme_tokens)
        return overlay


    def _compute_paste_hint_anchor_point(self, paste_range: tuple[int, int]) -> QPoint:
        viewport = self.viewport()
        cursor = QTextCursor(self.document())
        cursor.setPosition(paste_range[1])
        rect = self.cursorRect(cursor)
        margin_y = 4
        x = max(0, rect.left())
        y = rect.bottom() + margin_y
        if y > viewport.height() - 4:
            y = max(0, rect.top() - margin_y - 28)
        return QPoint(x, y)

    def _handle_paste_hint_reindent(self) -> None:
        if self._paste_hint_overlay is not None:
            self._paste_hint_overlay.hide_overlay()
        self._reindent_last_paste_range()

    def _handle_paste_hint_always(self) -> None:
        if self._paste_hint_overlay is not None:
            self._paste_hint_overlay.hide_overlay()
        if self._paste_hint_enable_always_callback is not None:
            self._paste_hint_enable_always_callback()
        self._reindent_last_paste_range()

    def _handle_paste_hint_dismissed(self) -> None:
        self._paste_hint_dismissed_this_session = True
        self._paste_hint_anchor_block = None

    def _reindent_last_paste_range(self) -> None:
        if self._last_paste_range is None:
            return
        result = self.reindent_flat_python_selection()
        if self._paste_hint_status_callback is not None:
            self._paste_hint_status_callback(result)
        self._paste_hint_anchor_block = None

    def _dismiss_flat_python_paste_hint(self, *, remember_session: bool) -> None:
        overlay = self._paste_hint_overlay
        if overlay is None or not overlay.isVisible():
            return
        overlay.hide_overlay()
        if remember_session:
            self._paste_hint_dismissed_this_session = True
        self._paste_hint_anchor_block = None

    def _maybe_dismiss_paste_hint_for_cursor(self) -> None:
        if self._paste_hint_anchor_block is None:
            return
        overlay = self._paste_hint_overlay
        if overlay is None or not overlay.isVisible():
            return
        cursor_block = self.textCursor().blockNumber()
        if abs(cursor_block - self._paste_hint_anchor_block) > 1:
            overlay.hide_overlay()
            self._paste_hint_anchor_block = None

    def _highlight_current_line(self) -> None:
        if self.isReadOnly():
            self.setExtraSelections([])
            return
        self._refresh_extra_selections()

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

    def _refresh_extra_selections(self) -> None:
        """Rebuild ExtraSelections with cached non-cursor overlays."""
        started_at = time.perf_counter()
        selections: list[QTextEdit.ExtraSelection] = []
        effective_mode = self._effective_highlighting_mode()
        cursor_position = self.textCursor().position()
        if (
            not self._overlay_cache_dirty
            and self._overlay_generation == self._last_applied_overlay_generation
            and cursor_position == self._last_applied_cursor_position
            and effective_mode == self._last_applied_effective_mode
        ):
            return

        line_selection = cast(Any, QTextEdit.ExtraSelection())
        line_selection.format.setBackground(self._line_highlight)
        line_selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        line_selection.cursor = self.textCursor()
        line_selection.cursor.clearSelection()
        selections.append(line_selection)

        if effective_mode == constants.HIGHLIGHTING_MODE_NORMAL:
            selections.extend(self._build_bracket_match_selections())

        if effective_mode != constants.HIGHLIGHTING_MODE_LEXICAL_ONLY:
            non_cursor = self._non_cursor_extra_selections()
            if self._is_large_document():
                non_cursor = self._viewport_cap_selections(
                    non_cursor,
                    max_count=MAX_OVERLAY_SELECTIONS_LARGE_FILE,
                )
            selections.extend(non_cursor)
        self.setExtraSelections(selections)
        self._last_applied_overlay_generation = self._overlay_generation
        self._last_applied_cursor_position = cursor_position
        self._last_applied_effective_mode = effective_mode
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        self._record_latency_metric(
            self._overlay_refresh_latency,
            elapsed_ms,
            warning_threshold_ms=OVERLAY_REFRESH_WARNING_MS,
        )

    def _non_cursor_extra_selections(self) -> list[QTextEdit.ExtraSelection]:
        if self._overlay_cache_dirty:
            self._cached_non_cursor_selections = self._build_non_cursor_extra_selections()
            self._overlay_cache_dirty = False
        return list(self._cached_non_cursor_selections)

    def _build_non_cursor_extra_selections(self) -> list[QTextEdit.ExtraSelection]:
        selections: list[QTextEdit.ExtraSelection] = []
        debug_selection = self._debug_execution_extra_selection()
        if debug_selection is not None:
            selections.append(debug_selection)
        selections.extend(self._diagnostic_selections)
        selections.extend(self._bounded_search_selections())
        return selections

    def _bounded_search_selections(self) -> list[QTextEdit.ExtraSelection]:
        if not self._is_large_document():
            return self._search_selections
        if 0 <= self._search_current_index < len(self._search_selections):
            return [self._search_selections[self._search_current_index]]
        return self._search_selections[:MAX_SEARCH_SELECTIONS_LARGE_FILE]

    def _mark_overlay_cache_dirty(self) -> None:
        self._overlay_cache_dirty = True
        self._overlay_generation += 1

    def _is_large_document(self) -> bool:
        return is_large_document(
            document_size=self.document().characterCount(),
            reduced_threshold_chars=self._highlighting_reduced_threshold_chars,
        )

    def _effective_highlighting_mode(self) -> str:
        return effective_highlighting_mode(
            adaptive_mode=self._highlighting_adaptive_mode,
            document_size=self.document().characterCount(),
            reduced_threshold_chars=self._highlighting_reduced_threshold_chars,
            lexical_only_threshold_chars=self._highlighting_lexical_only_threshold_chars,
        )

    def _viewport_cap_selections(
        self,
        selections: list[QTextEdit.ExtraSelection],
        *,
        max_count: int,
    ) -> list[QTextEdit.ExtraSelection]:
        if len(selections) <= max_count:
            return selections
        visible_start, visible_end = self._visible_document_window()
        filtered: list[QTextEdit.ExtraSelection] = []
        for selection in selections:
            cursor = selection.cursor
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            if end <= start:
                start = cursor.position()
                end = start + 1
            if start >= visible_end or end <= visible_start:
                continue
            filtered.append(selection)
            if len(filtered) >= max_count:
                break
        if filtered:
            return filtered
        return selections[:max_count]

    def _visible_document_window(self) -> tuple[int, int]:
        max_position = max(0, self.document().characterCount() - 1)
        top_cursor = self.cursorForPosition(QPoint(0, 0))
        bottom_cursor = self.cursorForPosition(QPoint(0, max(0, self.viewport().height() - 1)))
        return visible_document_window(
            top_position=top_cursor.position(),
            bottom_position=bottom_cursor.position(),
            max_position=max_position,
            margin=VIEWPORT_CHAR_MARGIN,
        )

    def _record_latency_metric(
        self,
        tracker: RollingLatencyTracker,
        elapsed_ms: float,
        *,
        warning_threshold_ms: float,
    ) -> None:
        snapshot = tracker.record(elapsed_ms)
        if not self._metrics_logging_enabled:
            return
        file_label = self._active_file_path or "<unsaved>"
        if elapsed_ms > warning_threshold_ms:
            self._logger.warning(
                "Editor latency warning: file=%s metric=%s elapsed_ms=%.2f",
                file_label,
                tracker.metric_name,
                elapsed_ms,
            )
            return
        if snapshot is not None:
            self._logger.info(
                "Editor latency telemetry: file=%s metric=%s count=%s p50_ms=%.2f p95_ms=%.2f max_ms=%.2f",
                file_label,
                snapshot.metric_name,
                snapshot.count,
                snapshot.p50_ms,
                snapshot.p95_ms,
                snapshot.max_ms,
            )

