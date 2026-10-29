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

from typing import Callable, List, Optional, Sequence, Tuple

from app.qt.QtCore import QEvent, QObject, Qt, Signal
from app.qt.QtGui import QColor, QFont, QFontMetrics, QTextCursor, QTextFormat
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
from app.features.form_builder.qtside.theme.chrome import FormChrome

OPEN_FILE = "Open file"
MIN_POINTS = 8.0


def header_text(module_file: str) -> str:
    """``ui_invoice.py · as it will be saved``."""
    return "%s · as it will be saved" % module_file


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

    def __init__(self, parent: QWidget, editor: QPlainTextEdit) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.codeView")
        self.setAccessibleName("Python code")
        self._chrome: Optional[FormChrome] = None
        self._marked: Tuple[int, ...] = ()
        self._error = ""
        self._marking = False
        self._base_points = 0.0
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
        editor.setParent(self)
        self.editor = editor
        self.editor.setObjectName("formBuilder.codeViewBody")
        self.editor.setReadOnly(True)
        self.editor.setAccessibleName("Generated Python")
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        outer.addWidget(self.editor, 1)
        self.setFocusProxy(self.editor)
        self._escape = _EscapeFilter(self)
        for target in (self.editor, self._open, self):
            target.installEventFilter(self._escape)
        self.editor.cursorPositionChanged.connect(self._cursor_moved)
        self.editor.viewport().installEventFilter(self._escape)

    def readable_width(self, chars: int) -> int:
        """Pixels the split needs to show ``chars`` characters of a code line at the smallest font ``fit_font`` uses."""
        font = QFont(self.editor.font())
        font.setPointSizeF(min(MIN_POINTS, font.pointSizeF()))
        return self._width_for(chars, QFontMetrics(font).horizontalAdvance("M"))

    def _width_for(self, chars: int, advance: int) -> int:
        gutter = 0
        width_of = getattr(self.editor, "line_number_area_width", None)
        if callable(width_of):
            try:
                gutter = int(width_of())
            except Exception:  # noqa: BLE001
                gutter = 0
        bar = self.editor.verticalScrollBar().sizeHint().width()
        return advance * chars + gutter + bar + 24

    def fit_font(self, chars: int, available: int) -> int:
        """Shrink the code font (down to ``MIN_POINTS``) until ``chars`` characters fit in ``available`` px.

        Returns the characters that fit. Lines longer than that wrap.
        """
        font = QFont(self.editor.font())
        base = self._base_points or font.pointSizeF()
        self._base_points = base
        points = base
        while True:
            font.setPointSizeF(points)
            advance = QFontMetrics(font).horizontalAdvance("M")
            if self._width_for(chars, advance) <= available or points <= MIN_POINTS:
                break
            points = max(MIN_POINTS, points - 0.5)
        if abs(points - self.editor.font().pointSizeF()) > 0.01:
            self.editor.setFont(font)
        return max(0, (available - self._width_for(0, 0)) // max(1, advance))

    def restore_font(self) -> None:
        if self._base_points:
            font = QFont(self.editor.font())
            font.setPointSizeF(self._base_points)
            self.editor.setFont(font)
            self._base_points = 0.0

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
        chrome = self._chrome
        fill = QColor(chrome.selected) if chrome is not None else QColor(207, 227, 255)
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

    def apply_chrome(self, chrome: FormChrome) -> None:
        self._chrome = chrome
        self._header.setStyleSheet(
            "QFrame#formBuilder\\.codeViewHeader { background: %s; border-bottom: 1px solid %s; }"
            "QLabel#formBuilder\\.codeViewTitle { color: %s; background: transparent; border: none; }"
            "QPushButton#formBuilder\\.codeViewOpen { color: %s; background: %s;"
            " border: 1px solid %s; border-radius: 3px; padding: 2px 10px; }"
            "QPushButton#formBuilder\\.codeViewOpen:focus { border: %dpx solid %s; }"
            % (
                chrome.panel,
                chrome.border,
                chrome.text,
                chrome.text,
                chrome.input,
                chrome.border,
                chrome.focus_width or 2,
                chrome.accent,
            )
        )
        self.setStyleSheet("QFrame#formBuilder\\.codeView { border-left: 1px solid %s; }" % chrome.border)
        self._apply_marks()


__all__ = ["CodeViewPanel", "OPEN_FILE", "header_text"]
