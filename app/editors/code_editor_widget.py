"""Custom code editor widget with gutter, breakpoints, and syntax highlighting."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from PySide2.QtCore import QRect, QSize, QStringListModel, Qt
from PySide2.QtGui import QColor, QKeyEvent, QPainter, QTextCursor, QTextFormat
from PySide2.QtWidgets import QApplication, QCompleter, QPlainTextEdit, QTextEdit, QWidget

from app.editors.text_editing import indent_lines, outdent_lines, toggle_comment_lines
from app.editors.syntax_json import JsonSyntaxHighlighter
from app.editors.syntax_markdown import MarkdownSyntaxHighlighter
from app.editors.syntax_python import PythonSyntaxHighlighter
from app.intelligence.completion_models import CompletionItem
from app.intelligence.completion_providers import extract_completion_prefix

DEFAULT_TAB_WIDTH = 4
DEFAULT_FONT_POINT_SIZE = 10
DEFAULT_COMPLETION_MIN_CHARS = 2


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
        self._tab_width = DEFAULT_TAB_WIDTH
        self._comment_prefix = "# "
        self._completion_provider: Callable[[str, str, int, bool], list[CompletionItem]] | None = None
        self._completion_enabled = True
        self._completion_auto_trigger = True
        self._completion_min_chars = DEFAULT_COMPLETION_MIN_CHARS
        self._completion_items_by_label: dict[str, CompletionItem] = {}
        self._completion_model = QStringListModel(self)
        self._completion_popup = QCompleter(self._completion_model, self)
        self._completion_popup.setCaseSensitivity(Qt.CaseInsensitive)
        self._completion_popup.setWidget(self)
        self._completion_popup.activated.connect(self._insert_completion_from_label)

        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_line_number_area_width(0)
        self._highlight_current_line()
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.set_editor_preferences(tab_width=DEFAULT_TAB_WIDTH, font_point_size=DEFAULT_FONT_POINT_SIZE)

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

    def set_editor_preferences(self, *, tab_width: int, font_point_size: int) -> None:
        """Apply tab width and font-size preferences."""
        self._tab_width = max(2, tab_width)
        font = self.font()
        font.setPointSize(max(8, font_point_size))
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * self._tab_width)

    def set_completion_provider(self, provider: Callable[[str, str, int, bool], list[CompletionItem]] | None) -> None:
        """Attach completion provider callback invoked during editor typing."""
        self._completion_provider = provider

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

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt signature
        if self._handle_completion_popup_navigation(event):
            return

        if event.key() == Qt.Key_Space and event.modifiers() & Qt.ControlModifier:
            self.trigger_completion(manual=True)
            event.accept()
            return

        super().keyPressEvent(event)
        if not self._completion_enabled or not self._completion_auto_trigger:
            return

        inserted_text = event.text()
        if inserted_text == ".":
            self.trigger_completion(manual=True, force_empty_prefix=True)
            return
        if inserted_text and (inserted_text.isalnum() or inserted_text == "_"):
            self.trigger_completion(manual=False)
            return
        if self._completion_popup.popup().isVisible():
            self._completion_popup.popup().hide()

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
                    QRect(0, top, self._line_number_area.width() - 6, self.fontMetrics().height()),
                    int(Qt.AlignRight),
                    number_text,
                    QRect(),
                )

            block = block.next()
            block_number += 1
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())

    def _highlight_current_line(self) -> None:
        if self.isReadOnly():
            self.setExtraSelections([])
            return

        selections: list[QTextEdit.ExtraSelection] = []

        line_selection = cast(Any, QTextEdit.ExtraSelection())
        line_selection.format.setBackground(QColor("#EEF7FF"))
        line_selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        line_selection.cursor = self.textCursor()
        line_selection.cursor.clearSelection()
        selections.append(line_selection)

        bracket_selection = self._build_bracket_match_selection()
        if bracket_selection is not None:
            selections.append(bracket_selection)

        self.setExtraSelections(selections)

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

    def indent_selection(self) -> None:
        selected = self.textCursor().selectedText()
        if not selected:
            self.insertPlainText(" " * self._tab_width)
            return
        updated = indent_lines(selected.replace("\u2029", "\n"), indent_text=" " * self._tab_width)
        self._replace_selected_text(updated)

    def outdent_selection(self) -> None:
        selected = self.textCursor().selectedText()
        if not selected:
            return
        updated = outdent_lines(selected.replace("\u2029", "\n"), indent_text=" " * self._tab_width)
        self._replace_selected_text(updated)

    def toggle_comment_selection(self) -> None:
        selected = self.textCursor().selectedText()
        if not selected:
            cursor = self.textCursor()
            cursor.select(QTextCursor.LineUnderCursor)
            selected = cursor.selectedText()
        updated = toggle_comment_lines(selected.replace("\u2029", "\n"), comment_prefix=self._comment_prefix)
        self._replace_selected_text(updated)

    def _replace_selected_text(self, replacement_text: str) -> None:
        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.LineUnderCursor)
        cursor.insertText(replacement_text)
        self.setTextCursor(cursor)

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

    def _build_bracket_match_selection(self) -> QTextEdit.ExtraSelection | None:
        cursor = self.textCursor()
        document_text = self.toPlainText()
        position = cursor.position()
        if not document_text:
            return None
        pairs = {"(": ")", "[": "]", "{": "}"}
        inverse_pairs = {")": "(", "]": "[", "}": "{"}
        if position > 0:
            current_char = document_text[position - 1]
            if current_char in pairs:
                match_position = self._find_matching_bracket(document_text, position - 1, current_char, pairs[current_char])
                if match_position is not None:
                    return self._selection_for_position(match_position)
            if current_char in inverse_pairs:
                match_position = self._find_matching_bracket_backward(
                    document_text,
                    position - 1,
                    inverse_pairs[current_char],
                    current_char,
                )
                if match_position is not None:
                    return self._selection_for_position(match_position)
        return None

    def _selection_for_position(self, position: int) -> QTextEdit.ExtraSelection:
        selection = cast(Any, QTextEdit.ExtraSelection())
        selection.format.setBackground(QColor("#FFD8A8"))
        cursor = self.textCursor()
        cursor.setPosition(position)
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, 1)
        selection.cursor = cursor
        return selection

    def _find_matching_bracket(self, text: str, start: int, opening: str, closing: str) -> int | None:
        depth = 0
        for index in range(start, len(text)):
            character = text[index]
            if character == opening:
                depth += 1
            elif character == closing:
                depth -= 1
                if depth == 0:
                    return index
        return None

    def _find_matching_bracket_backward(self, text: str, start: int, opening: str, closing: str) -> int | None:
        depth = 0
        for index in range(start, -1, -1):
            character = text[index]
            if character == closing:
                depth += 1
            elif character == opening:
                depth -= 1
                if depth == 0:
                    return index
        return None
