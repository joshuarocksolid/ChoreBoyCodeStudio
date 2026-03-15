"""Custom code editor widget with gutter, breakpoints, and syntax highlighting."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any, cast

from PySide2.QtCore import QEvent, QPoint, QPointF, QRect, QSize, QStringListModel, Qt
from PySide2.QtGui import QColor, QKeyEvent, QPainter, QPolygonF, QTextCharFormat, QTextCursor, QTextFormat
from PySide2.QtWidgets import QApplication, QCompleter, QPlainTextEdit, QTextEdit, QToolTip, QWidget

from app.bootstrap.logging_setup import get_subsystem_logger
from app.core import constants
from app.editors.editor_overlay_policy import (
    effective_highlighting_mode,
    is_large_document,
    visible_document_window,
)
from app.editors.find_replace_bar import FindOptions
from app.editors.syntax_registry import default_syntax_highlighter_registry, syntax_palette_from_tokens
from app.editors.text_editing import (
    indent_lines,
    next_line_indentation,
    outdent_lines,
    smart_backspace_columns,
    toggle_comment_lines,
)
from app.intelligence.completion_models import CompletionItem
from app.intelligence.completion_providers import extract_completion_prefix
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
LANGUAGE_SNIFF_SAMPLE_LINES = 12


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


class CodeEditorWidget(QPlainTextEdit):
    """QPlainTextEdit extension with common developer QoL affordances."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._logger = get_subsystem_logger("editors")
        self._metrics_logging_enabled = False
        self._active_file_path: str | None = None
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
        self._syntax_registry = default_syntax_highlighter_registry()
        self._syntax_palette: dict[str, str] = {}
        self._tab_width = DEFAULT_TAB_WIDTH
        self._comment_prefix = "#"
        self._indent_style = "spaces"
        self._indent_size = DEFAULT_TAB_WIDTH
        self._completion_provider: Callable[[str, str, int, bool], list[CompletionItem]] | None = None
        self._completion_accepted_callback: Callable[[CompletionItem], None] | None = None
        self._completion_enabled = True
        self._completion_auto_trigger = True
        self._completion_min_chars = DEFAULT_COMPLETION_MIN_CHARS
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
        self._syntax_registry.apply_theme(
            self._highlighter,
            is_dark=tokens.is_dark,
            syntax_palette=self._syntax_palette,
        )
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

    # ------------------------------------------------------------------
    # Diagnostics API (squiggly underlines, gutter markers, hover)
    # ------------------------------------------------------------------

    def set_diagnostics(self, diagnostics: list[CodeDiagnostic]) -> None:
        """Apply diagnostics: build squiggly underlines, gutter markers, and hover ranges."""
        self._diagnostic_selections.clear()
        self._diagnostic_lines.clear()
        self._diagnostic_ranges.clear()

        _SEVERITY_PRIORITY = {DiagnosticSeverity.ERROR: 0, DiagnosticSeverity.WARNING: 1, DiagnosticSeverity.INFO: 2}

        doc = self.document()
        for diag in diagnostics:
            color = self._diag_color_for_severity(diag.severity)
            block = doc.findBlockByNumber(diag.line_number - 1)
            if not block.isValid():
                continue

            block_start = block.position()
            line_text = block.text()

            if diag.col_start is not None and diag.col_end is not None:
                start_pos = block_start + diag.col_start
                end_pos = block_start + diag.col_end
            else:
                stripped = line_text.lstrip()
                leading = len(line_text) - len(stripped)
                start_pos = block_start + leading
                end_pos = block_start + len(line_text)

            if start_pos >= end_pos:
                end_pos = block_start + max(len(line_text), 1)

            sel = cast(Any, QTextEdit.ExtraSelection())
            sel.format.setUnderlineStyle(QTextCharFormat.WaveUnderline)
            sel.format.setUnderlineColor(color)
            if diag.code in {"PY301", "PY302"}:
                sel.format.setForeground(color)
            cursor = QTextCursor(doc)
            cursor.setPosition(start_pos)
            cursor.setPosition(end_pos, QTextCursor.KeepAnchor)
            sel.cursor = cursor
            self._diagnostic_selections.append(sel)

            tooltip = f"[{diag.code}] {diag.message}"
            self._diagnostic_ranges.append((start_pos, end_pos, tooltip))

            cur_severity = self._diagnostic_lines.get(diag.line_number)
            if cur_severity is None or _SEVERITY_PRIORITY.get(diag.severity, 2) < _SEVERITY_PRIORITY.get(cur_severity, 2):
                self._diagnostic_lines[diag.line_number] = diag.severity

        self._mark_overlay_cache_dirty()
        self._refresh_extra_selections()
        self._line_number_area.update()

    def clear_diagnostics(self) -> None:
        self._diagnostic_selections.clear()
        self._diagnostic_lines.clear()
        self._diagnostic_ranges.clear()
        self._mark_overlay_cache_dirty()
        self._refresh_extra_selections()
        self._line_number_area.update()

    def _diag_color_for_severity(self, severity: DiagnosticSeverity) -> QColor:
        if severity == DiagnosticSeverity.ERROR:
            return self._diag_error_color
        if severity == DiagnosticSeverity.WARNING:
            return self._diag_warning_color
        return self._diag_info_color

    def event(self, ev: QEvent) -> bool:  # type: ignore[override]
        if ev.type() == QEvent.ToolTip:
            pos = ev.pos()  # type: ignore[union-attr]
            cursor = self.cursorForPosition(pos)
            cursor_pos = cursor.position()
            for start, end, tooltip in self._diagnostic_ranges:
                if start <= cursor_pos < end:
                    QToolTip.showText(ev.globalPos(), tooltip, self)  # type: ignore[union-attr]
                    return True
            QToolTip.hideText()
            return True
        return super().event(ev)

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
        while block.isValid() and len(sample_lines) < LANGUAGE_SNIFF_SAMPLE_LINES:
            sample_lines.append(block.text())
            block = block.next()
        self._highlighter = self._syntax_registry.create_for_path(
            file_path=file_path,
            document=document,
            is_dark=self._is_dark,
            syntax_palette=self._syntax_palette,
            sample_text="\n".join(sample_lines),
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

    def set_completion_provider(self, provider: Callable[[str, str, int, bool], list[CompletionItem]] | None) -> None:
        """Attach completion provider callback invoked during editor typing."""
        self._completion_provider = provider

    def set_completion_accepted_callback(self, callback: Callable[[CompletionItem], None] | None) -> None:
        """Attach callback invoked when completion item is accepted."""
        self._completion_accepted_callback = callback

    def set_completion_preferences(self, *, enabled: bool, auto_trigger: bool, min_chars: int) -> None:
        """Apply completion behavior preferences."""
        self._completion_enabled = enabled
        self._completion_auto_trigger = auto_trigger
        self._completion_min_chars = max(1, min_chars)
        if not enabled:
            self._completion_popup.popup().hide()

    def trigger_completion(self, *, manual: bool, force_empty_prefix: bool = False) -> None:
        """Request and display completion candidates at current cursor location."""
        if not self._completion_enabled or self._completion_provider is None:
            return
        source_text = self.toPlainText()
        cursor_position = self.textCursor().position()
        prefix = extract_completion_prefix(source_text, cursor_position)
        if not force_empty_prefix and not manual and len(prefix) < self._completion_min_chars:
            self._completion_popup.popup().hide()
            return

        items = self._completion_provider(prefix, source_text, cursor_position, manual or force_empty_prefix)
        if not items:
            self._completion_popup.popup().hide()
            return
        self._show_completion_items(items, prefix=prefix)

    def keyPressEvent(self, e: QKeyEvent) -> None:  # noqa: N802 - Qt signature
        if self._handle_completion_popup_navigation(e):
            return

        if e.key() == Qt.Key_Space and e.modifiers() & Qt.ControlModifier:
            self.trigger_completion(manual=True)
            e.accept()
            return

        if e.key() == Qt.Key_Tab and not e.modifiers():
            self.indent_selection()
            e.accept()
            return
        if e.key() == Qt.Key_Backtab:
            self.outdent_selection()
            e.accept()
            return
        if e.key() == Qt.Key_Backspace and not e.modifiers():
            if self._handle_smart_backspace():
                e.accept()
                return
        if e.key() in {Qt.Key_Return, Qt.Key_Enter} and not (e.modifiers() & (Qt.ControlModifier | Qt.AltModifier)):
            self._insert_newline_with_auto_indent()
            e.accept()
            return

        super().keyPressEvent(e)
        if not self._completion_enabled or not self._completion_auto_trigger:
            return

        inserted_text = e.text()
        if inserted_text == ".":
            self.trigger_completion(manual=True, force_empty_prefix=True)
            return
        if inserted_text and (inserted_text.isalnum() or inserted_text == "_"):
            self.trigger_completion(manual=False)
            return
        if self._completion_popup.popup().isVisible():
            self._completion_popup.popup().hide()

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

    # ------------------------------------------------------------------
    # Search API
    # ------------------------------------------------------------------

    def highlight_all_matches(self, query: str, options: FindOptions) -> int:
        """Highlight all matches and return total count. Sets current index to -1."""
        self._search_selections.clear()
        self._search_match_positions.clear()
        self._search_current_index = -1

        if not query:
            self._refresh_extra_selections()
            return 0

        pattern = self._compile_search_pattern(query, options)
        if pattern is None:
            self._refresh_extra_selections()
            return 0

        text = self.toPlainText()
        for m in pattern.finditer(text):
            start, end = m.start(), m.end()
            self._search_match_positions.append((start, end))
            sel = self._make_match_selection(start, end, is_current=False)
            self._search_selections.append(sel)

        self._mark_overlay_cache_dirty()
        self._refresh_extra_selections()
        return len(self._search_match_positions)

    def find_next(self) -> tuple[int, int]:
        """Move to the next match. Returns (current_1indexed, total)."""
        total = len(self._search_match_positions)
        if total == 0:
            return (0, 0)

        cursor_pos = self.textCursor().position()
        next_idx = 0
        for i, (start, _end) in enumerate(self._search_match_positions):
            if start >= cursor_pos:
                next_idx = i
                break
        else:
            next_idx = 0

        self._go_to_match(next_idx)
        return (self._search_current_index + 1, total)

    def find_previous(self) -> tuple[int, int]:
        """Move to previous match. Returns (current_1indexed, total)."""
        total = len(self._search_match_positions)
        if total == 0:
            return (0, 0)

        cursor_pos = self.textCursor().position()
        cursor_sel_start = self.textCursor().selectionStart()
        prev_idx = total - 1
        for i in range(total - 1, -1, -1):
            start, _end = self._search_match_positions[i]
            if start < cursor_sel_start:
                prev_idx = i
                break
        else:
            prev_idx = total - 1

        self._go_to_match(prev_idx)
        return (self._search_current_index + 1, total)

    def replace_current_match(self, replacement: str, query: str, options: FindOptions) -> tuple[int, int]:
        """Replace the current match and move to next. Returns (current_1indexed, total)."""
        if self._search_current_index < 0 or not self._search_match_positions:
            return self.find_next()

        start, end = self._search_match_positions[self._search_current_index]
        cursor = self.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.insertText(replacement)
        self.setTextCursor(cursor)

        total = self.highlight_all_matches(query, options)
        if total == 0:
            return (0, 0)
        return self.find_next()

    def replace_all_matches(self, query: str, replacement: str, options: FindOptions) -> int:
        """Replace all matches. Returns count of replacements made."""
        if not self._search_match_positions:
            return 0

        cursor = self.textCursor()
        cursor.beginEditBlock()
        offset = 0
        count = 0
        for start, end in self._search_match_positions:
            adj_start = start + offset
            adj_end = end + offset
            cursor.setPosition(adj_start)
            cursor.setPosition(adj_end, QTextCursor.KeepAnchor)
            cursor.insertText(replacement)
            offset += len(replacement) - (end - start)
            count += 1
        cursor.endEditBlock()
        self.setTextCursor(cursor)

        self.highlight_all_matches(query, options)
        return count

    def clear_search_highlights(self) -> None:
        """Remove all search highlights."""
        self._search_selections.clear()
        self._search_match_positions.clear()
        self._search_current_index = -1
        self._mark_overlay_cache_dirty()
        self._refresh_extra_selections()

    def _go_to_match(self, index: int) -> None:
        if index < 0 or index >= len(self._search_match_positions):
            return

        self._search_current_index = index
        start, end = self._search_match_positions[index]

        self._search_selections = []
        for i, (s, e) in enumerate(self._search_match_positions):
            sel = self._make_match_selection(s, e, is_current=(i == index))
            self._search_selections.append(sel)
        self._mark_overlay_cache_dirty()
        self._refresh_extra_selections()

        cursor = self.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        self.setTextCursor(cursor)
        self.centerCursor()

    def _make_match_selection(self, start: int, end: int, *, is_current: bool) -> QTextEdit.ExtraSelection:
        sel = cast(Any, QTextEdit.ExtraSelection())
        color = self._search_current_match_bg if is_current else self._search_match_bg
        sel.format.setBackground(color)
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        sel.cursor = cursor
        return sel

    @staticmethod
    def _compile_search_pattern(query: str, options: FindOptions) -> re.Pattern[str] | None:
        flags = 0 if options.case_sensitive else re.IGNORECASE
        if options.regex:
            try:
                return re.compile(query, flags)
            except re.error:
                return None
        escaped = re.escape(query)
        if options.whole_word:
            escaped = rf"\b{escaped}\b"
        return re.compile(escaped, flags)

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

    def indent_selection(self) -> None:
        selected = self.textCursor().selectedText()
        if not selected:
            self.insertPlainText(self._indent_text())
            return
        updated = indent_lines(selected.replace("\u2029", "\n"), indent_text=self._indent_text())
        self._replace_selected_text(updated)

    def outdent_selection(self) -> None:
        selected = self.textCursor().selectedText()
        if not selected:
            return
        updated = outdent_lines(selected.replace("\u2029", "\n"), indent_text=self._indent_text())
        self._replace_selected_text(updated)

    def toggle_comment_selection(self) -> None:
        cursor = self.textCursor()
        if cursor.hasSelection():
            cursor = self._expand_selection_to_full_lines(cursor)
        else:
            cursor.select(QTextCursor.LineUnderCursor)
        selected = cursor.selectedText()
        updated = toggle_comment_lines(selected.replace("\u2029", "\n"), comment_prefix=self._comment_prefix)
        cursor.insertText(updated)
        self.setTextCursor(cursor)

    def _expand_selection_to_full_lines(self, cursor: QTextCursor) -> QTextCursor:
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        document = self.document()
        start_block = document.findBlock(start)
        end_lookup_position = end - 1 if end > start else end
        end_block = document.findBlock(max(0, end_lookup_position))
        expanded_cursor = QTextCursor(document)
        expanded_cursor.setPosition(start_block.position())
        end_position = max(expanded_cursor.position(), end_block.position() + max(0, end_block.length() - 1))
        expanded_cursor.setPosition(end_position, QTextCursor.KeepAnchor)
        return expanded_cursor

    def _replace_selected_text(self, replacement_text: str) -> None:
        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.LineUnderCursor)
        cursor.insertText(replacement_text)
        self.setTextCursor(cursor)

    def _handle_smart_backspace(self) -> bool:
        cursor = self.textCursor()
        if cursor.hasSelection():
            return False
        remove_count = smart_backspace_columns(
            cursor.block().text(),
            cursor.positionInBlock(),
            indent_text=self._indent_text(),
        )
        if remove_count <= 0:
            return False
        cursor.beginEditBlock()
        for _ in range(remove_count):
            cursor.deletePreviousChar()
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        return True

    def _insert_newline_with_auto_indent(self) -> None:
        cursor = self.textCursor()
        if cursor.hasSelection():
            cursor.removeSelectedText()
        line_prefix = cursor.block().text()[: cursor.positionInBlock()]
        indent = next_line_indentation(line_prefix, indent_text=self._indent_text())
        cursor.beginEditBlock()
        cursor.insertText(f"\n{indent}")
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def _indent_text(self) -> str:
        if self._indent_style == "tabs":
            return "\t"
        return " " * self._indent_size

    def _handle_completion_popup_navigation(self, event: QKeyEvent) -> bool:
        popup = self._completion_popup.popup()
        if not popup.isVisible():
            return False

        if event.key() in {Qt.Key_Escape}:
            popup.hide()
            event.accept()
            return True

        if event.key() in {Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab}:
            current_index = popup.currentIndex()
            if current_index.isValid():
                selected_label = current_index.data(0)
                if selected_label is not None:
                    self._insert_completion_from_label(str(selected_label))
            popup.hide()
            event.accept()
            return True

        if event.key() in {Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Home, Qt.Key_End}:
            QApplication.sendEvent(popup, event)
            return True

        return False

    def _show_completion_items(self, items: list[CompletionItem], *, prefix: str) -> None:
        labels: list[str] = []
        mapped_items: dict[str, CompletionItem] = {}
        for item in items:
            display_label = item.label if not item.detail else f"{item.label} — {item.detail}"
            if display_label in mapped_items:
                display_label = f"{display_label} ({item.kind.value})"
            labels.append(display_label)
            mapped_items[display_label] = item

        if not labels:
            self._completion_popup.popup().hide()
            return

        self._completion_items_by_label = mapped_items
        self._completion_model.setStringList(labels)
        self._completion_popup.setCompletionPrefix(prefix)
        popup = self._completion_popup.popup()
        popup.setCurrentIndex(self._completion_model.index(0, 0))
        rect = self.cursorRect()
        rect.setWidth(max(240, popup.sizeHintForColumn(0) + 24))
        self._completion_popup.complete(rect)

    def _insert_completion_from_label(self, display_label: object) -> None:
        normalized_label = str(display_label)
        completion_item = self._completion_items_by_label.get(normalized_label)
        if completion_item is None:
            return

        cursor = self.textCursor()
        current_prefix = extract_completion_prefix(self.toPlainText(), cursor.position())
        if current_prefix:
            cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(current_prefix))
            cursor.removeSelectedText()
        cursor.insertText(completion_item.insert_text)
        self.setTextCursor(cursor)
        if self._completion_accepted_callback is not None:
            self._completion_accepted_callback(completion_item)

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
