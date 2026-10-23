"""Gutter, breakpoint, and debug-line chrome for CodeEditorWidget."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from app.qt.QtCore import QPointF, QRect, QSize, Qt
from app.qt.QtGui import QColor, QFont, QFontMetrics, QPainter, QPolygonF, QTextCursor, QTextFormat
from app.qt.QtWidgets import QTextEdit, QToolTip, QWidget
from app.qt.qt_compat import event_global_pos, event_pos

from app.shell.theme_tokens import ShellThemeTokens


@dataclass(frozen=True)
class LineNote:
    first_line: int
    last_line: int
    label: str
    tooltip: str


class _AnchoredLineNote:
    __slots__ = ("start", "end", "label", "tooltip")

    def __init__(self, start: QTextCursor, end: QTextCursor, label: str, tooltip: str) -> None:
        self.start = start
        self.end = end
        self.label = label
        self.tooltip = tooltip


def _paint_bracket(painter: QPainter, x: int, top: int, bottom: int, color: QColor) -> None:
    height = bottom - top
    if height < 2:
        height = 2
    painter.fillRect(x, top, 2, height, color)
    painter.fillRect(x - 4, top, 6, 2, color)
    painter.fillRect(x - 4, top + height - 2, 6, 2, color)


if TYPE_CHECKING:
    from app.qt.QtWidgets import QPlainTextEdit

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
        _anchored_notes: list[_AnchoredLineNote]

        def _diag_color_for_severity(self, severity: Any) -> QColor: ...
        def _mark_overlay_cache_dirty(self) -> None: ...
        def _highlight_current_line(self) -> None: ...
        def _notify_highlighter_viewport_lines(self) -> None: ...
        def buffer_views(self) -> list[Any]: ...
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
        self._editor.toggle_breakpoint_at_y(event_pos(event).y())

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        pos = event_pos(event)
        tip = self._editor._gutter_note_tooltip(int(pos.x()), int(pos.y()))
        if tip:
            QToolTip.showText(event_global_pos(event), tip, self)
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        QToolTip.hideText()
        super().leaveEvent(event)


class CodeEditorChromeMixin(_CodeEditorChromeBase):
    """Editor chrome split from the main editor widget."""

    _ICON_ZONE_WIDTH = 20
    _NOTE_BRACKET_SLOT = 8
    _NOTE_LABEL_GAP = 6

    def _init_chrome_state(self) -> None:
        self._line_number_area = _LineNumberArea(self)
        self._anchored_notes: list[_AnchoredLineNote] = []
        self._line_number_area.setMouseTracking(True)
        self._breakpoint_toggled_callback: Callable[[int, bool], None] | None = None
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
        self._breakpoint_color = QColor(tokens.diag_error_color)
        if tokens.debug_paused_color:
            self._debug_execution_color = QColor(tokens.debug_paused_color)
        if tokens.debug_current_frame_bg:
            self._debug_execution_line_bg = QColor(tokens.debug_current_frame_bg)

    def set_breakpoint_toggled_callback(self, callback: Callable[[int, bool], None] | None) -> None:
        self._breakpoint_toggled_callback = callback

    def set_breakpoints(self, breakpoints: set[int]) -> None:
        self._breakpoints = set(breakpoints)
        self._update_gutters_of_buffer_views()

    def breakpoints(self) -> set[int]:
        return set(self._breakpoints)

    def set_line_notes(self, notes: Sequence[LineNote]) -> None:
        document = self.document()
        anchored: list[_AnchoredLineNote] = []
        for note in notes:
            first = note.first_line
            if first <= 0:
                continue
            last = note.last_line if note.last_line >= first else first
            start_block = document.findBlockByNumber(first - 1)
            if not start_block.isValid():
                continue
            end_block = document.findBlockByNumber(last - 1)
            if not end_block.isValid():
                end_block = document.lastBlock()
            start = QTextCursor(document)
            start.setPosition(start_block.position())
            end = QTextCursor(document)
            end.setPosition(end_block.position() + max(0, end_block.length() - 1))
            anchored.append(_AnchoredLineNote(start, end, note.label, note.tooltip))
        self._anchored_notes = anchored
        self._update_line_number_area_width(0)
        self._line_number_area.update()

    def line_note_tooltip(self, line_number: int) -> str | None:
        for first, last, _label, tooltip in self._resolved_notes():
            if first <= line_number <= last and tooltip:
                return tooltip
        return None

    def _resolved_notes(self) -> list[tuple[int, int, str, str]]:
        resolved: list[tuple[int, int, str, str]] = []
        for note in self._anchored_notes:
            start_block = note.start.block()
            if not start_block.isValid():
                continue
            end_block = note.end.block()
            first = start_block.blockNumber() + 1
            last = end_block.blockNumber() + 1 if end_block.isValid() else first
            if last < first:
                first, last = last, first
            resolved.append((first, last, note.label, note.tooltip))
        return resolved

    def _note_caption_font(self) -> QFont:
        font = QFont(self.font())
        size = font.pointSize()
        if size > 0:
            font.setPointSize(max(1, size - 1))
            return font
        pixels = font.pixelSize()
        if pixels > 0:
            font.setPixelSize(max(1, pixels - 1))
        return font

    def _gutter_number_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return self._ICON_ZONE_WIDTH + 8 + self.fontMetrics().horizontalAdvance("9") * digits

    def _note_label_column(self) -> int:
        metrics = QFontMetrics(self._note_caption_font())
        widest = 0
        for note in self._anchored_notes:
            if note.label:
                widest = max(widest, metrics.horizontalAdvance(note.label))
        if widest == 0:
            return 0
        return widest + self._NOTE_LABEL_GAP

    def _label_on_line(self, line_number: int) -> str:
        for first, _last, label, _tooltip in self._resolved_notes():
            if line_number == first and label:
                return label
        return ""

    def _line_number_at_y(self, y_coordinate: int) -> int | None:
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        while block.isValid() and top <= y_coordinate:
            if block.isVisible() and bottom >= y_coordinate:
                return block_number + 1
            block = block.next()
            block_number += 1
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
        return None

    def _gutter_note_tooltip(self, x: int, y: int) -> str | None:
        if not self._anchored_notes:
            return None
        line = self._line_number_at_y(y)
        if line is None:
            return None
        bracket_left = self._line_number_area.width() - self._NOTE_BRACKET_SLOT
        label_left = self._gutter_number_width()
        for first, last, label, tooltip in self._resolved_notes():
            if not (first <= line <= last) or not tooltip:
                continue
            on_bracket = x >= bracket_left
            on_label = bool(label) and line == first and label_left <= x < bracket_left
            if on_bracket or on_label:
                return tooltip
        return None

    def _paint_note_brackets(self, painter: QPainter) -> None:
        if not self._anchored_notes:
            return
        x = self._line_number_area.width() - 4
        color = self._gutter_text
        document = self.document()
        for first, last, _label, _tooltip in self._resolved_notes():
            start_block = document.findBlockByNumber(first - 1)
            end_block = document.findBlockByNumber(last - 1)
            if not start_block.isValid() or not end_block.isValid():
                continue
            top = int(self.blockBoundingGeometry(start_block).translated(self.contentOffset()).top())
            end_top = self.blockBoundingGeometry(end_block).translated(self.contentOffset()).top()
            bottom = int(end_top + self.blockBoundingRect(end_block).height())
            _paint_bracket(painter, x, top, bottom, color)

    def toggle_breakpoint(self, line_number: int) -> bool:
        if line_number <= 0:
            return False
        if line_number in self._breakpoints:
            self._breakpoints.remove(line_number)
            is_enabled = False
        else:
            self._breakpoints.add(line_number)
            is_enabled = True
        self._update_gutters_of_buffer_views()
        if self._breakpoint_toggled_callback is not None:
            self._breakpoint_toggled_callback(line_number, is_enabled)
        return is_enabled

    def set_debug_execution_line(self, line_number: int | None) -> None:
        if self._debug_execution_line == line_number:
            return
        self._debug_execution_line = line_number
        for view in self.buffer_views():
            view._mark_overlay_cache_dirty()
            view._line_number_area.update()
            view._highlight_current_line()

    def _update_gutters_of_buffer_views(self) -> None:
        for view in self.buffer_views():
            view._line_number_area.update()

    def clear_debug_execution_line(self) -> None:
        self.set_debug_execution_line(None)

    def toggle_breakpoint_at_y(self, y_coordinate: int) -> None:
        line_number = self._line_number_at_y(y_coordinate)
        if line_number is not None:
            self.toggle_breakpoint(line_number)

    def line_number_area_width(self) -> int:
        width = self._gutter_number_width()
        if self._anchored_notes:
            width += self._note_label_column() + self._NOTE_BRACKET_SLOT
        return width

    def _update_line_number_area_width(self, _new_block_count: int) -> None:
        width = self.line_number_area_width()
        self.setViewportMargins(width, 0, 0, 0)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(QRect(cr.left(), cr.top(), width, cr.height()))

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
            self._paint_note_brackets(painter)

            block = self.firstVisibleBlock()
            number_width = self._gutter_number_width()
            label_column = self._note_label_column() if self._anchored_notes else 0
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
                        QRect(icon_zone, top, number_width - icon_zone - 4, font_height),  # type: ignore
                        int(Qt.AlignRight),
                        number_text,
                    )  # type: ignore[call-overload]
                    label = self._label_on_line(line_number) if label_column else ""
                    label_slot = label_column - self._NOTE_LABEL_GAP
                    if label and label_slot > 0:
                        caption = self._note_caption_font()
                        if QFontMetrics(caption).horizontalAdvance(label) <= label_slot:
                            painter.setFont(caption)
                            painter.setPen(self._gutter_text)
                            painter.drawText(
                                QRect(number_width, top, label_slot, font_height),  # type: ignore
                                int(Qt.AlignRight | Qt.AlignVCenter),
                                label,
                            )  # type: ignore[call-overload]
                            painter.setFont(self.font())

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
