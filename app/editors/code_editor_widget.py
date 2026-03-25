"""Custom code editor widget with gutter, breakpoints, and syntax highlighting."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, cast

from PySide2.QtCore import QPoint, QPointF, QRect, QSize, QStringListModel, Qt
from PySide2.QtGui import QColor, QPainter, QPolygonF, QTextCursor, QTextFormat
from PySide2.QtWidgets import QCompleter, QPlainTextEdit, QTextEdit, QWidget

from app.bootstrap.logging_setup import get_subsystem_logger
from app.core import constants
from app.editors.code_editor_diagnostics import CodeEditorDiagnosticsMixin
from app.editors.code_editor_editing import CodeEditorEditingMixin
from app.editors.code_editor_search import CodeEditorSearchMixin
from app.editors.code_editor_semantics import CodeEditorSemanticsMixin
from app.editors.editor_overlay_policy import (
    effective_highlighting_mode,
    is_large_document,
    visible_document_window,
)
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


class _LineNumberArea(QWidget):
    def __init__(self, editor: "CodeEditorWidget") -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt signature
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        self._editor.paint_line_number_area(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        self._editor.toggle_breakpoint_at_y(event.pos().y())


class CodeEditorWidget(
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
        self._line_number_area = _LineNumberArea(self)
        self._breakpoints: set[int] = set()
        self._breakpoint_toggled_callback: Callable[[int, bool], None] | None = None
        self._debug_execution_line: int | None = None
        self._debug_execution_color = QColor("#D97706")
        self._debug_execution_line_bg = QColor("#D0E2FF")
        self._highlighter: object | None = None
        self._syntax_theme_refresh_pending = False
        self._syntax_registry = default_syntax_highlighter_registry()
        self._syntax_palette: dict[str, str] = {}
        self._tab_width = DEFAULT_TAB_WIDTH
        self._comment_prefix = "#"
        self._indent_style = "spaces"
        self._indent_size = DEFAULT_TAB_WIDTH
        self._completion_provider: Callable[[str, str, int, bool], list[CompletionItem]] | None = None
        self._completion_requester: Callable[[str, str, int, bool, int], None] | None = None
        self._completion_accepted_callback: Callable[[CompletionItem], None] | None = None
        self._hover_provider: Callable[[str, int], str | None] | None = None
        self._hover_requester: Callable[[str, int, int], None] | None = None
        self._signature_help_provider: Callable[[str, int], str | None] | None = None
        self._signature_help_requester: Callable[[str, int, int], None] | None = None
        self._completion_enabled = True
        self._completion_auto_trigger = True
        self._completion_min_chars = DEFAULT_COMPLETION_MIN_CHARS
        self._completion_request_generation = 0
        self._hover_request_generation = 0
        self._hover_request_global_pos: QPoint | None = None
        self._signature_help_request_generation = 0
        self._completion_items_by_label: dict[str, CompletionItem] = {}
        self._completion_model = QStringListModel(self)
        self._completion_popup = QCompleter(self._completion_model, self)
        self._completion_popup.setCaseSensitivity(Qt.CaseInsensitive)
        self._completion_popup.setWidget(self)
        self._completion_popup.activated.connect(self._insert_completion_from_label)

        self._is_dark = False
        self._gutter_bg = QColor("#F1F3F5")
        self._gutter_text = QColor("#ADB5BD")
        self._line_highlight = QColor("#EEF7FF")
        self._bracket_match_color = QColor("#FFD8A8")
        self._breakpoint_color = QColor("#E03131")

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
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self.verticalScrollBar().valueChanged.connect(self._handle_viewport_changed)
        self._update_line_number_area_width(0)
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
        self._gutter_bg = QColor(tokens.gutter_bg)
        self._gutter_text = QColor(tokens.gutter_text)
        self._line_highlight = QColor(tokens.line_highlight)
        self._bracket_match_color = QColor("#5C3D1A") if tokens.is_dark else QColor("#FFD8A8")
        self._breakpoint_color = QColor("#FF6B6B") if tokens.is_dark else QColor("#E03131")
        self._debug_execution_color = QColor(tokens.debug_paused_color) if tokens.debug_paused_color else self._debug_execution_color
        self._debug_execution_line_bg = QColor(tokens.debug_current_frame_bg) if tokens.debug_current_frame_bg else self._debug_execution_line_bg
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

    def set_breakpoint_toggled_callback(self, callback: Callable[[int, bool], None] | None) -> None:
        self._breakpoint_toggled_callback = callback

    def set_breakpoints(self, breakpoints: set[int]) -> None:
        self._breakpoints = set(breakpoints)
        self._line_number_area.update()

    def breakpoints(self) -> set[int]:
        return set(self._breakpoints)

    def toggle_breakpoint(self, line_number: int) -> bool:
        if line_number <= 0:
            return False
        if line_number in self._breakpoints:
            self._breakpoints.remove(line_number)
            is_enabled = False
        else:
            self._breakpoints.add(line_number)
            is_enabled = True
        self._line_number_area.update()
        if self._breakpoint_toggled_callback is not None:
            self._breakpoint_toggled_callback(line_number, is_enabled)
        return is_enabled

    def set_debug_execution_line(self, line_number: int | None) -> None:
        if self._debug_execution_line == line_number:
            return
        self._debug_execution_line = line_number
        self._mark_overlay_cache_dirty()
        self._line_number_area.update()
        self._highlight_current_line()

    def clear_debug_execution_line(self) -> None:
        self.set_debug_execution_line(None)

    def toggle_breakpoint_at_y(self, y_coordinate: int) -> None:
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= y_coordinate:
            if block.isVisible() and bottom >= y_coordinate:
                self.toggle_breakpoint(block_number + 1)
                return
            block = block.next()
            block_number += 1
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())

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
    ) -> None:
        """Apply tab width, font family, and font-size preferences."""
        self._tab_width = max(2, tab_width)
        self._indent_style = "tabs" if indent_style == "tabs" else "spaces"
        self._indent_size = max(1, indent_size)
        font = self.font()
        font.setFamily(font_family)
        font.setPointSize(max(8, font_point_size))
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * self._tab_width)

    _ICON_ZONE_WIDTH = 20

    def line_number_area_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return self._ICON_ZONE_WIDTH + 8 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_number_area_width(self, _new_block_count: int) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(0, rect.y(), self._line_number_area.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))
        self._notify_highlighter_viewport_lines()

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        super().showEvent(event)
        if not self._syntax_theme_refresh_pending or self._highlighter is None:
            return
        if hasattr(self._highlighter, "rehighlight"):
            self._highlighter.rehighlight()  # type: ignore[union-attr]
        self._syntax_theme_refresh_pending = False
        self._notify_highlighter_viewport_lines()

    def paint_line_number_area(self, event) -> None:
        painter = QPainter(self._line_number_area)
        try:
            painter.fillRect(event.rect(), self._gutter_bg)

            block = self.firstVisibleBlock()
            block_number = block.blockNumber()
            top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
            bottom = top + int(self.blockBoundingRect(block).height())
            icon_zone = self._ICON_ZONE_WIDTH

            while block.isValid() and top <= event.rect().bottom():
                if block.isVisible() and bottom >= event.rect().top():
                    line_number = block_number + 1
                    number_text = str(line_number)
                    color = self._gutter_text
                    font_height = self.fontMetrics().height()
                    center_y = top + font_height // 2

                    if line_number in self._breakpoints:
                        color = self._breakpoint_color
                        marker_radius = 4
                        painter.setBrush(color)
                        painter.setPen(Qt.NoPen)
                        painter.drawEllipse(2, center_y - marker_radius, marker_radius * 2, marker_radius * 2)

                    if line_number == self._debug_execution_line:
                        color = self._debug_execution_color
                        arrow_size = 5
                        arrow_x = icon_zone - arrow_size - 3
                        arrow = QPolygonF([
                            QPointF(arrow_x, center_y - arrow_size),
                            QPointF(arrow_x + arrow_size, center_y),
                            QPointF(arrow_x, center_y + arrow_size),
                        ])
                        painter.setBrush(self._debug_execution_color)
                        painter.setPen(Qt.NoPen)
                        painter.drawPolygon(arrow)

                    diag_severity = self._diagnostic_lines.get(line_number)
                    if diag_severity is not None and line_number not in self._breakpoints:
                        diag_color = self._diag_color_for_severity(diag_severity)
                        painter.setBrush(diag_color)
                        painter.setPen(Qt.NoPen)
                        tri_size = 4
                        painter.drawPolygon(QPolygonF([
                            QPointF(2, center_y - tri_size),
                            QPointF(2 + tri_size + 2, center_y),
                            QPointF(2, center_y + tri_size),
                        ]))

                    painter.setPen(color)
                    painter.drawText(
                        QRect(icon_zone, top, self._line_number_area.width() - icon_zone - 4, font_height),  # type: ignore
                        int(Qt.AlignRight),
                        number_text,
                    )  # type: ignore[call-overload]

                block = block.next()
                block_number += 1
                top = bottom
                bottom = top + int(self.blockBoundingRect(block).height())
        finally:
            painter.end()

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

        if effective_mode == constants.HIGHLIGHTING_MODE_NORMAL and not self._is_large_document():
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
        if self._debug_execution_line is not None:
            debug_sel = cast(Any, QTextEdit.ExtraSelection())
            debug_sel.format.setBackground(self._debug_execution_line_bg)
            debug_sel.format.setProperty(QTextFormat.FullWidthSelection, True)
            block = self.document().findBlockByNumber(self._debug_execution_line - 1)
            if block.isValid():
                debug_cursor = QTextCursor(block)
                debug_cursor.clearSelection()
                debug_sel.cursor = debug_cursor
                selections.append(debug_sel)
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

    def _build_bracket_match_selections(self) -> list[QTextEdit.ExtraSelection]:
        if self._is_large_document():
            return []
        cursor = self.textCursor()
        document = self.document()
        max_index = max(0, document.characterCount() - 1)
        position = cursor.position()
        if max_index <= 0 or position <= 0:
            return []
        pairs = {"(": ")", "[": "]", "{": "}"}
        inverse_pairs = {")": "(", "]": "[", "}": "{"}
        current_char = str(document.characterAt(position - 1))
        if current_char in pairs:
            match_position = self._find_matching_bracket(document, position - 1, current_char, pairs[current_char], max_index)
            if match_position is not None:
                return [self._selection_for_position(position - 1), self._selection_for_position(match_position)]
        if current_char in inverse_pairs:
            match_position = self._find_matching_bracket_backward(
                document,
                position - 1,
                inverse_pairs[current_char],
                current_char,
            )
            if match_position is not None:
                return [self._selection_for_position(position - 1), self._selection_for_position(match_position)]
        return []

    def _selection_for_position(self, position: int) -> QTextEdit.ExtraSelection:
        selection = cast(Any, QTextEdit.ExtraSelection())
        selection.format.setBackground(self._bracket_match_color)
        cursor = self.textCursor()
        cursor.setPosition(position)
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, 1)
        selection.cursor = cursor
        return selection

    def _find_matching_bracket(
        self,
        document,  # type: ignore[no-untyped-def]
        start: int,
        opening: str,
        closing: str,
        max_index: int,
    ) -> int | None:
        depth = 0
        for index in range(start, max_index):
            character = str(document.characterAt(index))
            if character == opening:
                depth += 1
            elif character == closing:
                depth -= 1
                if depth == 0:
                    return index
        return None

    def _find_matching_bracket_backward(
        self,
        document,  # type: ignore[no-untyped-def]
        start: int,
        opening: str,
        closing: str,
    ) -> int | None:
        depth = 0
        for index in range(start, -1, -1):
            character = str(document.characterAt(index))
            if character == closing:
                depth += 1
            elif character == opening:
                depth -= 1
                if depth == 0:
                    return index
        return None
