"""Extra-selection overlay orchestration for CodeEditorWidget."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from PySide2.QtCore import QPoint
from PySide2.QtGui import QColor, QTextFormat
from PySide2.QtWidgets import QTextEdit

from app.core import constants
from app.editors.editor_overlay_policy import (
    effective_highlighting_mode,
    is_large_document,
    visible_document_window,
)


MAX_SEARCH_SELECTIONS_LARGE_FILE = 400
MAX_OVERLAY_SELECTIONS_LARGE_FILE = 700
VIEWPORT_CHAR_MARGIN = 8000


if TYPE_CHECKING:
    from PySide2.QtWidgets import QPlainTextEdit

    class _CodeEditorExtraSelectionsOverlayBase(QPlainTextEdit):
        _line_highlight: QColor
        _search_selections: list[QTextEdit.ExtraSelection]
        _search_current_index: int
        _diagnostic_selections: list[QTextEdit.ExtraSelection]
        _cached_non_cursor_selections: list[QTextEdit.ExtraSelection]
        _overlay_cache_dirty: bool
        _overlay_generation: int
        _last_applied_overlay_generation: int
        _last_applied_cursor_position: int
        _last_applied_effective_mode: str
        _highlighting_adaptive_mode: str
        _highlighting_reduced_threshold_chars: int
        _highlighting_lexical_only_threshold_chars: int
        _operation_latency_sink: Callable[[str, float, str | None], None] | None
        _active_file_path: str | None

        def _build_bracket_match_selections(self) -> list[QTextEdit.ExtraSelection]: ...
        def _debug_execution_extra_selection(self) -> QTextEdit.ExtraSelection | None: ...
        def _emit_operation_latency(self, metric_name: str, elapsed_ms: float) -> None: ...
else:
    class _CodeEditorExtraSelectionsOverlayBase:
        pass


class CodeEditorExtraSelectionsOverlayMixin(_CodeEditorExtraSelectionsOverlayBase):
    """Line highlight, diagnostics, search, and bracket overlay refresh split from the hub."""

    def _init_extra_selections_overlay_state(self) -> None:
        self._line_highlight = QColor("#EEF7FF")
        self._search_match_bg = QColor("#FFE066")
        self._search_current_match_bg = QColor("#FF922B")
        self._search_selections = []
        self._search_match_positions: list[tuple[int, int]] = []
        self._search_current_index = -1
        self._cached_non_cursor_selections: list[QTextEdit.ExtraSelection] = []
        self._overlay_cache_dirty = True
        self._overlay_generation = 0
        self._last_applied_overlay_generation = -1
        self._last_applied_cursor_position = -1
        self._last_applied_effective_mode = ""

    def _apply_extra_selections_overlay_theme(self, tokens: Any) -> None:
        self._line_highlight = QColor(tokens.line_highlight)
        if tokens.search_match_bg:
            self._search_match_bg = QColor(tokens.search_match_bg)
        if tokens.search_current_match_bg:
            self._search_current_match_bg = QColor(tokens.search_current_match_bg)

    def _highlight_current_line(self) -> None:
        if self.isReadOnly():
            self.setExtraSelections([])
            return
        self._refresh_extra_selections()

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
        self._emit_operation_latency("editor_overlay_refresh_ms", elapsed_ms)

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
