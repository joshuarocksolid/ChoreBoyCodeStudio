"""Search and replace highlighting behavior for CodeEditorWidget."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, cast

from PySide2.QtGui import QTextCursor
from PySide2.QtWidgets import QTextEdit

from app.editors.find_replace_bar import FindOptions

MAX_EDITOR_REGEX_QUERY_CHARS = 512
MAX_EDITOR_SEARCH_TEXT_CHARS = 1_000_000

if TYPE_CHECKING:
    from PySide2.QtWidgets import QPlainTextEdit

    class _CodeEditorSearchBase(QPlainTextEdit):
        _search_selections: list[Any]
        _search_match_positions: list[tuple[int, int]]
        _search_current_index: int
        _search_match_bg: Any
        _search_current_match_bg: Any

        def _mark_overlay_cache_dirty(self) -> None: ...
        def _refresh_extra_selections(self) -> None: ...
else:
    class _CodeEditorSearchBase:
        pass


class CodeEditorSearchMixin(_CodeEditorSearchBase):
    """Search/highlight behavior split out from the main editor widget."""

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
        if len(text) > MAX_EDITOR_SEARCH_TEXT_CHARS and options.regex:
            self._refresh_extra_selections()
            return 0
        for match in pattern.finditer(text):
            start, end = match.start(), match.end()
            self._search_match_positions.append((start, end))
            selection = self._make_match_selection(start, end, is_current=False)
            self._search_selections.append(selection)

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
        for index, (start, _end) in enumerate(self._search_match_positions):
            if start >= cursor_pos:
                next_idx = index
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

        cursor_sel_start = self.textCursor().selectionStart()
        prev_idx = total - 1
        for index in range(total - 1, -1, -1):
            start, _end = self._search_match_positions[index]
            if start < cursor_sel_start:
                prev_idx = index
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
        for current_index, (match_start, match_end) in enumerate(self._search_match_positions):
            selection = self._make_match_selection(match_start, match_end, is_current=(current_index == index))
            self._search_selections.append(selection)
        self._mark_overlay_cache_dirty()
        self._refresh_extra_selections()

        cursor = self.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        self.setTextCursor(cursor)
        self.centerCursor()

    def _make_match_selection(self, start: int, end: int, *, is_current: bool) -> QTextEdit.ExtraSelection:
        selection = cast(Any, QTextEdit.ExtraSelection())
        color = self._search_current_match_bg if is_current else self._search_match_bg
        selection.format.setBackground(color)
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        selection.cursor = cursor
        return selection

    @staticmethod
    def _compile_search_pattern(query: str, options: FindOptions) -> re.Pattern[str] | None:
        flags = 0 if options.case_sensitive else re.IGNORECASE
        if options.regex and len(query) > MAX_EDITOR_REGEX_QUERY_CHARS:
            return None
        if options.regex:
            try:
                return re.compile(query, flags)
            except re.error:
                return None
        escaped = re.escape(query)
        if options.whole_word:
            escaped = rf"\b{escaped}\b"
        return re.compile(escaped, flags)
