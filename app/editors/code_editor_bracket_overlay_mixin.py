"""Bounded bracket matching overlay for CodeEditorWidget."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from PySide2.QtGui import QColor, QTextCursor
from PySide2.QtWidgets import QTextEdit


BRACKET_MATCH_SCAN_LIMIT_CHARS = 2_000


if TYPE_CHECKING:
    from PySide2.QtGui import QTextDocument
    from PySide2.QtWidgets import QPlainTextEdit

    class _CodeEditorBracketOverlayBase(QPlainTextEdit):
        _bracket_match_color: QColor
else:
    class _CodeEditorBracketOverlayBase:
        pass


class CodeEditorBracketOverlayMixin(_CodeEditorBracketOverlayBase):
    """Bracket-match overlay behavior split from the main editor widget."""

    def _init_bracket_overlay_state(self) -> None:
        self._bracket_match_color = QColor("#FFD8A8")

    def _apply_bracket_overlay_theme(self, *, is_dark: bool) -> None:
        self._bracket_match_color = QColor("#5C3D1A") if is_dark else QColor("#FFD8A8")

    def _build_bracket_match_selections(self) -> list[QTextEdit.ExtraSelection]:
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
            match_position = self._find_matching_bracket(
                document,
                position - 1,
                current_char,
                pairs[current_char],
                max_index,
                scan_limit_chars=BRACKET_MATCH_SCAN_LIMIT_CHARS,
            )
            if match_position is not None:
                return [self._selection_for_position(position - 1), self._selection_for_position(match_position)]
        if current_char in inverse_pairs:
            match_position = self._find_matching_bracket_backward(
                document,
                position - 1,
                inverse_pairs[current_char],
                current_char,
                scan_limit_chars=BRACKET_MATCH_SCAN_LIMIT_CHARS,
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
        document: "QTextDocument",
        start: int,
        opening: str,
        closing: str,
        max_index: int,
        *,
        scan_limit_chars: int,
    ) -> int | None:
        depth = 0
        scan_end = min(max_index, start + max(0, scan_limit_chars) + 1)
        for index in range(start, scan_end):
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
        document: "QTextDocument",
        start: int,
        opening: str,
        closing: str,
        *,
        scan_limit_chars: int,
    ) -> int | None:
        depth = 0
        scan_start = max(0, start - max(0, scan_limit_chars))
        for index in range(start, scan_start - 1, -1):
            character = str(document.characterAt(index))
            if character == closing:
                depth += 1
            elif character == opening:
                depth -= 1
                if depth == 0:
                    return index
        return None
