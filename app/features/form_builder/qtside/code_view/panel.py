"""The split beside the canvas: generated Python, read only (M5.5a, UX-PREV-004).

A header ("ui_invoice.py · as it will be saved" and [Open file]) over the CBCS code
editor with Python highlighting. The panel only shows what it is given:

* ``show_code`` replaces the text and keeps the scroll position;
* ``show_error`` shows the FB502 sentence (or any sentence) in place of code;
* ``mark`` scrolls to a widget's creating line and marks every line that names it
  with the selection fill (``fb.row_selected``);
* ``line_clicked`` reports a click on a line, so the controller can select the widget it names.

Esc anywhere inside the split asks to close it (``close_requested``).
"""

from __future__ import annotations

import logging
from typing import Callable, List, Optional, Sequence, Tuple

from app.qt.QtCore import QEvent, QObject, Qt, Signal
from app.qt.QtGui import QColor, QTextCursor, QTextFormat
from app.qt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from app.shell.theme_tokens import ShellThemeTokens

logger = logging.getLogger(__name__)

OPEN_FILE = "Open file"


def header_text(module_file: str) -> str:
    """``ui_invoice.py · as it will be saved``."""
    return "%s · as it will be saved" % module_file


def _make_editor(parent: QWidget) -> QPlainTextEdit:
    """The shell's code editor, or a plain text edit when the shell's cannot be made."""
    try:
        from app.editors.code_editor_widget import CodeEditorWidget

        editor = CodeEditorWidget(parent)
        editor.set_language_for_path("ui_form.py")
        return editor
    except Exception:
        logger.exception("the code view could not make the code editor")
        return QPlainTextEdit(parent)


class _EscapeFilter(QObject):
    def __init__(self, owner: "CodeViewPanel") -> None:
        super().__init__(owner)
        self._owner = owner

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == getattr(QEvent, "Type", QEvent).KeyPress:
            if event.key() == Qt.Key.Key_Escape and not event.modifiers():  # type: ignore[attr-defined]
                self._owner.close_requested.emit()
                return True
        return False


class CodeViewPanel(QFrame):
    close_requested: "Signal" = Signal()
    open_file_requested: "Signal" = Signal()
    line_clicked: "Signal" = Signal(int)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.codeView")
        self.setAccessibleName("Python code")
        self._tokens: Optional[ShellThemeTokens] = None
        self._marked: Tuple[int, ...] = ()
        self._error = ""
        self._marking = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._header = QFrame(self)
        self._header.setObjectName("formBuilder.codeViewHeader")
        row = QHBoxLayout(self._header)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(8)
        self._title = QLabel("", self._header)
        self._title.setObjectName("formBuilder.codeViewTitle")
        row.addWidget(self._title, 1)
        self._open = QPushButton(OPEN_FILE, self._header)
        self._open.setObjectName("formBuilder.codeViewOpen")
        self._open.clicked.connect(lambda _checked=False: self.open_file_requested.emit())
        self._open.hide()
        row.addWidget(self._open, 0)
        outer.addWidget(self._header)
        self.editor = _make_editor(self)
        self.editor.setObjectName("formBuilder.codeViewBody")
        self.editor.setReadOnly(True)
        self.editor.setAccessibleName("Generated Python")
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        outer.addWidget(self.editor, 1)
        self.setFocusProxy(self.editor)
        self._escape = _EscapeFilter(self)
        for target in (self.editor, self._open, self):
            target.installEventFilter(self._escape)
        self.editor.cursorPositionChanged.connect(self._cursor_moved)
        self.editor.viewport().installEventFilter(self._escape)

    # ---- content

    def set_header(self, module_file: str, *, can_open: bool) -> None:
        self._title.setText(header_text(module_file))
        self._title.setAccessibleName(self._title.text())
        self._open.setVisible(can_open)

    def text(self) -> str:
        return "" if self._error else self.editor.toPlainText()

    def error_text(self) -> str:
        return self._error

    def show_code(self, text: str) -> None:
        """Replace the code, keeping the place the reader was at."""
        self._error = ""
        bar = self.editor.verticalScrollBar()
        keep = bar.value()
        if self.editor.toPlainText() != text:
            self.editor.setPlainText(text)
            bar.setValue(keep)
        self._apply_marks()

    def show_error(self, sentence: str) -> None:
        """The reason the code cannot be shown, in place of the code."""
        self._error = sentence
        self._marked = ()
        self.editor.setPlainText(sentence)
        self._apply_marks()

    # ---- marks

    def mark(self, lines: Sequence[int], scroll_to: Optional[int]) -> None:
        """Mark ``lines`` (0-based) and scroll so ``scroll_to`` is in view."""
        self._marked = tuple(lines)
        self._apply_marks()
        if scroll_to is None or self._error:
            return
        block = self.editor.document().findBlockByNumber(scroll_to)
        if not block.isValid():
            return
        self._marking = True
        try:
            self.editor.setTextCursor(QTextCursor(block))
            self.editor.centerCursor()
        finally:
            self._marking = False
        self._apply_marks()

    def marked_lines(self) -> Tuple[int, ...]:
        return self._marked

    def first_visible_line(self) -> int:
        return self.editor.firstVisibleBlock().blockNumber()

    def last_visible_line(self) -> int:
        view = self.editor.viewport().rect()
        block = self.editor.cursorForPosition(view.bottomLeft()).block()
        return block.blockNumber()

    def _apply_marks(self) -> None:
        tokens = self._tokens
        fill = QColor(tokens.tree_selected_bg if tokens is not None else "#cfe3ff")
        selections: List[QTextEdit.ExtraSelection] = []
        document = self.editor.document()
        for number in self._marked:
            block = document.findBlockByNumber(number)
            if not block.isValid():
                continue
            found = QTextEdit.ExtraSelection()
            found.format.setBackground(fill)
            found.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            found.cursor = QTextCursor(block)
            found.cursor.clearSelection()
            selections.append(found)
        self.editor.setExtraSelections(selections)

    def _cursor_moved(self) -> None:
        # The shell's editor clears its extra selections when a read-only cursor moves; marks are ours.
        self._apply_marks()
        if self.editor.hasFocus() and not self._error and not self._marking:
            self.line_clicked.emit(self.editor.textCursor().blockNumber())

    # ---- look

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._tokens = tokens
        apply = getattr(self.editor, "apply_theme", None)
        if callable(apply):
            try:
                apply(tokens)
            except Exception:
                logger.exception("the code view could not theme its editor")
        self._header.setStyleSheet(
            "QFrame#formBuilder\\.codeViewHeader { background: %s; border-bottom: 1px solid %s; }"
            "QLabel#formBuilder\\.codeViewTitle { color: %s; background: transparent; border: none; }"
            "QPushButton#formBuilder\\.codeViewOpen { color: %s; background: transparent;"
            " border: 1px solid %s; border-radius: 4px; padding: 2px 8px; }"
            "QPushButton#formBuilder\\.codeViewOpen:focus { border: %dpx solid %s; }"
            % (
                tokens.panel_bg,
                tokens.border,
                tokens.text_primary,
                tokens.text_primary,
                tokens.border,
                tokens.focus_border_width or 2,
                tokens.accent,
            )
        )
        self.setStyleSheet("QFrame#formBuilder\\.codeView { border-left: 1px solid %s; }" % tokens.border)
        self._apply_marks()


__all__ = ["CodeViewPanel", "OPEN_FILE", "header_text"]
