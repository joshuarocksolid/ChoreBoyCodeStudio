"""Custom code editor widget with gutter, breakpoints, and syntax highlighting."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Optional

from PySide2.QtCore import QRect, QSize, Qt
from PySide2.QtGui import QColor, QPainter, QTextCursor, QTextFormat
from PySide2.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

from app.editors.syntax_json import JsonSyntaxHighlighter
from app.editors.syntax_markdown import MarkdownSyntaxHighlighter
from app.editors.syntax_python import PythonSyntaxHighlighter


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
        self._line_number_area = _LineNumberArea(self)
        self._breakpoints: set[int] = set()
        self._breakpoint_toggled_callback: Callable[[int, bool], None] | None = None
        self._highlighter: object | None = None

        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_line_number_area_width(0)
        self._highlight_current_line()
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)

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
        extension = Path(file_path).suffix.lower()
        document = self.document()
        if extension == ".py":
            self._highlighter = PythonSyntaxHighlighter(document)
        elif extension in {".json"}:
            self._highlighter = JsonSyntaxHighlighter(document)
        elif extension in {".md", ".markdown"}:
            self._highlighter = MarkdownSyntaxHighlighter(document)
        else:
            self._highlighter = None

    def line_number_area_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return 16 + self.fontMetrics().horizontalAdvance("9") * digits

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

    def paint_line_number_area(self, event) -> None:
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QColor("#F1F3F5"))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                line_number = block_number + 1
                number_text = str(line_number)
                color = QColor("#ADB5BD")
                if line_number in self._breakpoints:
                    color = QColor("#E03131")
                    marker_radius = 4
                    center_y = top + self.fontMetrics().height() // 2
                    painter.setBrush(color)
                    painter.setPen(Qt.NoPen)
                    painter.drawEllipse(2, center_y - marker_radius, marker_radius * 2, marker_radius * 2)
                painter.setPen(color)
                painter.drawText(
                    0,
                    top,
                    self._line_number_area.width() - 6,
                    self.fontMetrics().height(),
                    Qt.AlignRight,
                    number_text,
                )

            block = block.next()
            block_number += 1
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())

    def _highlight_current_line(self) -> None:
        if self.isReadOnly():
            self.setExtraSelections([])
            return

        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor("#EEF7FF"))
        selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])

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
