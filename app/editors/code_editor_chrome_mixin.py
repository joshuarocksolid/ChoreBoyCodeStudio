"""Gutter, breakpoint, and debug-line chrome for CodeEditorWidget."""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from PySide2.QtCore import QPointF, QRect, QSize, Qt
from PySide2.QtGui import QColor, QPainter, QPolygonF, QTextCursor, QTextFormat
from PySide2.QtWidgets import QTextEdit, QWidget

from app.shell.theme_tokens import ShellThemeTokens


if TYPE_CHECKING:
    from PySide2.QtWidgets import QPlainTextEdit

    class _CodeEditorChromeBase(QPlainTextEdit):
        _line_number_area: "_LineNumberArea"
        _breakpoints: set[int]
        _breakpoint_toggled_callback: Callable[[int, bool], None] | None
        _debug_execution_line: int | None
        _debug_execution_color: QColor
        _debug_execution_line_bg: QColor
        _gutter_bg: QColor
        _gutter_text: QColor
        _breakpoint_color: QColor
        _diagnostic_lines: dict[int, Any]

        def _diag_color_for_severity(self, severity: Any) -> QColor: ...
        def _mark_overlay_cache_dirty(self) -> None: ...
        def _highlight_current_line(self) -> None: ...
        def _notify_highlighter_viewport_lines(self) -> None: ...
else:
    class _CodeEditorChromeBase:
        pass


class _LineNumberArea(QWidget):
    def __init__(self, editor: CodeEditorChromeMixin) -> None:
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


class CodeEditorChromeMixin(_CodeEditorChromeBase):
    """Editor chrome split from the main editor widget."""

    _ICON_ZONE_WIDTH = 20

    def _init_chrome_state(self) -> None:
        self._line_number_area = _LineNumberArea(self)
        self._breakpoints: set[int] = set()
        self._breakpoint_toggled_callback: Callable[[int, bool], None] | None = None
        self._debug_execution_line: int | None = None
        self._debug_execution_color = QColor("#D97706")
        self._debug_execution_line_bg = QColor("#D0E2FF")
        self._gutter_bg = QColor("#F1F3F5")
        self._gutter_text = QColor("#ADB5BD")
        self._breakpoint_color = QColor("#E03131")
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self._update_line_number_area_width(0)

    def _apply_chrome_theme(self, tokens: ShellThemeTokens) -> None:
        self._gutter_bg = QColor(tokens.gutter_bg)
        self._gutter_text = QColor(tokens.gutter_text)
        self._breakpoint_color = QColor("#FF6B6B") if tokens.is_dark else QColor("#E03131")
        if tokens.debug_paused_color:
            self._debug_execution_color = QColor(tokens.debug_paused_color)
        if tokens.debug_current_frame_bg:
            self._debug_execution_line_bg = QColor(tokens.debug_current_frame_bg)

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

    def resizeEvent(self, e) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        super().resizeEvent(e)
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

    def _debug_execution_extra_selection(self) -> QTextEdit.ExtraSelection | None:
        if self._debug_execution_line is None:
            return None
        debug_sel = cast(Any, QTextEdit.ExtraSelection())
        debug_sel.format.setBackground(self._debug_execution_line_bg)
        debug_sel.format.setProperty(QTextFormat.FullWidthSelection, True)
        block = self.document().findBlockByNumber(self._debug_execution_line - 1)
        if not block.isValid():
            return None
        debug_cursor = QTextCursor(block)
        debug_cursor.clearSelection()
        debug_sel.cursor = debug_cursor
        return debug_sel
