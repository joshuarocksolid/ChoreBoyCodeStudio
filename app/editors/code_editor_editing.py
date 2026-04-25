"""Editing transform behavior for CodeEditorWidget."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide2.QtGui import QTextCursor
from PySide2.QtWidgets import QApplication

from app.editors.text_editing import (
    FlatPythonIndentRepairResult,
    indent_lines,
    map_offset_through_text_change,
    next_line_indentation,
    outdent_lines,
    repair_flat_python_indentation,
    smart_backspace_columns,
    toggle_comment_lines,
)


if TYPE_CHECKING:
    from PySide2.QtWidgets import QPlainTextEdit

    class _CodeEditorEditingBase(QPlainTextEdit):
        _comment_prefix: str
        _indent_style: str
        _indent_size: int
else:
    class _CodeEditorEditingBase:
        pass


class CodeEditorEditingMixin(_CodeEditorEditingBase):
    """Editing transforms split out from the main editor widget."""

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

    def paste_reindented_flat_python(self) -> FlatPythonIndentRepairResult:
        """Paste clipboard text, repairing flattened Python indentation when detected."""
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        result = repair_flat_python_indentation(text, indent_text=self._indent_text())
        should_apply_repair = result.reason != "not a flat Python paste"
        insert_text = result.text if should_apply_repair else text
        self._insert_text_as_paste(insert_text, prefix_subsequent_lines=should_apply_repair)
        return result

    def reindent_flat_python_selection(self) -> FlatPythonIndentRepairResult:
        """Repair flattened Python indentation in the selection or most recent paste."""
        cursor = self.textCursor()
        if cursor.hasSelection():
            cursor = self._expand_selection_to_full_lines(cursor)
        else:
            paste_range = getattr(self, "_last_paste_range", None)
            if not paste_range:
                return FlatPythonIndentRepairResult(
                    text="",
                    changed=False,
                    confidence="low",
                    parse_ok=False,
                    reason="no selection or recent paste",
                )
            start, end = paste_range
            cursor = QTextCursor(self.document())
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)

        selected = cursor.selectedText().replace("\u2029", "\n")
        result = repair_flat_python_indentation(selected, indent_text=self._indent_text())
        if result.reason == "not a flat Python paste":
            return result
        start = cursor.selectionStart()
        cursor.beginEditBlock()
        cursor.insertText(result.text)
        cursor.endEditBlock()
        end = cursor.position()
        self.setTextCursor(cursor)
        setattr(self, "_last_paste_range", (start, end))
        return result

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

    def _insert_text_as_paste(self, text: str, *, prefix_subsequent_lines: bool = False) -> None:
        cursor = self.textCursor()
        start = cursor.selectionStart() if cursor.hasSelection() else cursor.position()
        insert_text = self._prefix_paste_subsequent_lines(text) if prefix_subsequent_lines else text
        cursor.beginEditBlock()
        cursor.insertText(insert_text)
        cursor.endEditBlock()
        end = cursor.position()
        self.setTextCursor(cursor)
        setattr(self, "_last_paste_range", (start, end))

    def _prefix_paste_subsequent_lines(self, text: str) -> str:
        if "\n" not in text:
            return text
        cursor = self.textCursor()
        line_prefix = cursor.block().text()[: cursor.positionInBlock()]
        if not line_prefix or line_prefix.strip():
            return text
        return text.replace("\n", f"\n{line_prefix}")

    def replace_document_text(self, replacement_text: str) -> bool:
        """Replace the full document in one undo step while preserving editor context."""
        original_text = self.toPlainText()
        if replacement_text == original_text:
            return False

        cursor = self.textCursor()
        original_anchor = cursor.anchor()
        original_position = cursor.position()
        vertical_scroll = self.verticalScrollBar().value()
        horizontal_scroll = self.horizontalScrollBar().value()
        mapped_anchor = map_offset_through_text_change(original_text, replacement_text, original_anchor)
        mapped_position = map_offset_through_text_change(original_text, replacement_text, original_position)

        edit_cursor = QTextCursor(self.document())
        edit_cursor.beginEditBlock()
        edit_cursor.select(QTextCursor.Document)
        edit_cursor.insertText(replacement_text)
        edit_cursor.endEditBlock()

        restored_cursor = QTextCursor(self.document())
        restored_cursor.setPosition(mapped_anchor)
        move_mode = QTextCursor.MoveAnchor if mapped_anchor == mapped_position else QTextCursor.KeepAnchor
        restored_cursor.setPosition(mapped_position, move_mode)
        self.setTextCursor(restored_cursor)
        self.verticalScrollBar().setValue(min(vertical_scroll, self.verticalScrollBar().maximum()))
        self.horizontalScrollBar().setValue(min(horizontal_scroll, self.horizontalScrollBar().maximum()))
        return True

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
