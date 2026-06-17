"""Line-number gutter painted alongside diff editor panes."""

from __future__ import annotations

from typing import Optional

from PySide2.QtCore import QEvent, QRect, QSize, Qt
from PySide2.QtGui import QColor, QPainter
from PySide2.QtWidgets import QPlainTextEdit, QWidget

from app.shell.theme_tokens import ShellThemeTokens


class DiffGutterArea(QWidget):
    """Two-column line-number gutter painted alongside a QPlainTextEdit."""

    def __init__(self, editor: QPlainTextEdit) -> None:
        super().__init__(editor)
        self._editor = editor
        self._old_numbers: list[Optional[int]] = []
        self._new_numbers: list[Optional[int]] = []
        self._show_old = True
        self._show_new = True
        self._gutter_bg = QColor("#F1F3F5")
        self._gutter_text = QColor("#ADB5BD")
        self._editor.blockCountChanged.connect(self._handle_block_count)
        self._editor.updateRequest.connect(self._handle_update_request)
        self._editor.installEventFilter(self)
        self._refresh_width()

    def set_columns(self, *, show_old: bool, show_new: bool) -> None:
        self._show_old = show_old
        self._show_new = show_new
        self._refresh_width()

    def set_numbers(
        self,
        *,
        old_numbers: list[Optional[int]],
        new_numbers: list[Optional[int]],
    ) -> None:
        self._old_numbers = list(old_numbers)
        self._new_numbers = list(new_numbers)
        self._refresh_width()
        self.update()

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._gutter_bg = QColor(tokens.gutter_bg)
        self._gutter_text = QColor(tokens.gutter_text)
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt signature
        return QSize(self._compute_width(), 0)

    def _compute_width(self) -> int:
        digits_old = len(str(max((n for n in self._old_numbers if n is not None), default=1)))
        digits_new = len(str(max((n for n in self._new_numbers if n is not None), default=1)))
        digits_old = max(digits_old, 2)
        digits_new = max(digits_new, 2)
        digit_width = self._editor.fontMetrics().horizontalAdvance("9")
        column_pad = 8
        total = column_pad
        if self._show_old:
            total += digit_width * digits_old + column_pad
        if self._show_new:
            total += digit_width * digits_new + column_pad
        return total

    def _refresh_width(self) -> None:
        width = self._compute_width()
        self._editor.setViewportMargins(width, 0, 0, 0)
        cr = self._editor.contentsRect()
        self.setGeometry(QRect(cr.left(), cr.top(), width, cr.height()))

    def _handle_block_count(self, _new_count: int) -> None:
        self._refresh_width()

    def _handle_update_request(self, rect: QRect, dy: int) -> None:
        if dy:
            self.scroll(0, dy)
        else:
            self.update(0, rect.y(), self.width(), rect.height())
        if rect.contains(self._editor.viewport().rect()):
            self._refresh_width()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt signature
        if watched is self._editor and event.type() == QEvent.Resize:
            self._refresh_width()
        return super().eventFilter(watched, event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt signature
        painter = QPainter(self)
        try:
            painter.fillRect(event.rect(), self._gutter_bg)
            painter.setPen(self._gutter_text)
            block = self._editor.firstVisibleBlock()
            block_number = block.blockNumber()
            top = int(
                self._editor.blockBoundingGeometry(block)
                .translated(self._editor.contentOffset())
                .top()
            )
            bottom = top + int(self._editor.blockBoundingRect(block).height())
            font_height = self._editor.fontMetrics().height()
            digit_width = self._editor.fontMetrics().horizontalAdvance("9")
            digits_old = max(
                len(str(max((n for n in self._old_numbers if n is not None), default=1))),
                2,
            )
            digits_new = max(
                len(str(max((n for n in self._new_numbers if n is not None), default=1))),
                2,
            )
            column_pad = 8

            while block.isValid() and top <= event.rect().bottom():
                if block.isVisible() and bottom >= event.rect().top():
                    x_offset = column_pad
                    if self._show_old:
                        old_no = (
                            self._old_numbers[block_number]
                            if block_number < len(self._old_numbers)
                            else None
                        )
                        if old_no is not None:
                            painter.drawText(
                                QRect(x_offset, top, digit_width * digits_old, font_height),
                                int(Qt.AlignRight),
                                str(old_no),
                            )
                        x_offset += digit_width * digits_old + column_pad
                    if self._show_new:
                        new_no = (
                            self._new_numbers[block_number]
                            if block_number < len(self._new_numbers)
                            else None
                        )
                        if new_no is not None:
                            painter.drawText(
                                QRect(x_offset, top, digit_width * digits_new, font_height),
                                int(Qt.AlignRight),
                                str(new_no),
                            )
                block = block.next()
                block_number += 1
                top = bottom
                bottom = top + int(self._editor.blockBoundingRect(block).height())
        finally:
            painter.end()
