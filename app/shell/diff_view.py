"""Themed diff renderer used by the local-history and recovery dialogs.

The widget supports two modes:

* ``inline`` — a single ``QPlainTextEdit`` showing the unified diff text
  with red/green tinted background lines and dimmed hunk headers.  The
  text content is the standard ``difflib.unified_diff`` payload so that
  callers (and tests) can scrape it via ``toPlainText()``.
* ``side_by_side`` — two synchronised ``QPlainTextEdit`` panes for the
  before / after texts, with each pane painting per-line tints
  (removals on the left, additions on the right, context unchanged).

Both modes share a small two-column gutter (old line number, new line
number for the inline mode; a single column per pane for side-by-side
mode).

Public API:

* :func:`compute_diff_hunks` — pure parser turning two text buffers
  into a typed list of hunks.  Used directly by the unit tests.
* :class:`DiffView` — the QWidget the dialogs embed.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from PySide2.QtCore import QRect, QSize, Qt
from PySide2.QtGui import (
    QColor,
    QFontDatabase,
    QPainter,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide2.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from app.shell.theme_tokens import ShellThemeTokens


DIFF_VIEW_MODE_INLINE = "inline"
DIFF_VIEW_MODE_SIDE_BY_SIDE = "side_by_side"

LINE_KIND_CONTEXT = "context"
LINE_KIND_ADD = "add"
LINE_KIND_REMOVE = "remove"
LINE_KIND_HEADER = "header"
LINE_KIND_FILE_LABEL = "file_label"


@dataclass
class DiffLine:
    """One classified line in a unified diff."""

    kind: str
    text: str
    old_no: Optional[int] = None
    new_no: Optional[int] = None


@dataclass
class DiffHunk:
    """One @@ ... @@ block with classified lines."""

    header: str
    old_start: int
    new_start: int
    lines: List[DiffLine] = field(default_factory=list)


@dataclass
class DiffStats:
    """Aggregate counts for a diff."""

    added: int
    removed: int

    @property
    def is_empty(self) -> bool:
        return self.added == 0 and self.removed == 0


def compute_diff_hunks(
    before_text: str,
    after_text: str,
    *,
    from_label: str = "before",
    to_label: str = "after",
) -> tuple[list[DiffHunk], DiffStats, str]:
    """Return parsed hunks, aggregate stats, and the raw unified-diff text.

    The third return value is the full ``difflib.unified_diff`` text
    (suitable for ``QPlainTextEdit.setPlainText``); the hunks list is
    used by the gutter and the side-by-side renderer.
    """

    before_lines = before_text.splitlines()
    after_lines = after_text.splitlines()
    diff_lines = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=from_label,
            tofile=to_label,
            lineterm="",
        )
    )
    raw_text = "\n".join(diff_lines)

    hunks: list[DiffHunk] = []
    current_hunk: Optional[DiffHunk] = None
    old_cursor = 0
    new_cursor = 0
    added = 0
    removed = 0

    for line in diff_lines:
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("@@"):
            old_start, new_start = _parse_hunk_header(line)
            current_hunk = DiffHunk(
                header=line,
                old_start=old_start,
                new_start=new_start,
            )
            hunks.append(current_hunk)
            old_cursor = old_start
            new_cursor = new_start
            continue
        if current_hunk is None:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            current_hunk.lines.append(
                DiffLine(kind=LINE_KIND_ADD, text=line[1:], new_no=new_cursor)
            )
            new_cursor += 1
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            current_hunk.lines.append(
                DiffLine(kind=LINE_KIND_REMOVE, text=line[1:], old_no=old_cursor)
            )
            old_cursor += 1
            removed += 1
        else:
            payload = line[1:] if line.startswith(" ") else line
            current_hunk.lines.append(
                DiffLine(
                    kind=LINE_KIND_CONTEXT,
                    text=payload,
                    old_no=old_cursor,
                    new_no=new_cursor,
                )
            )
            old_cursor += 1
            new_cursor += 1

    return hunks, DiffStats(added=added, removed=removed), raw_text


def _parse_hunk_header(header: str) -> tuple[int, int]:
    """Best-effort parse of '@@ -1,3 +1,4 @@' style hunk headers."""
    try:
        body = header.split("@@")[1].strip()
        parts = body.split()
        old_part = parts[0].lstrip("-").split(",")[0]
        new_part = parts[1].lstrip("+").split(",")[0]
        return int(old_part), int(new_part)
    except (IndexError, ValueError):
        return 1, 1


def _line_tint(base_hex: str, *, is_dark: bool) -> QColor:
    color = QColor(base_hex)
    color.setAlpha(48 if is_dark else 38)
    return color


class _DiffInlineHighlighter(QSyntaxHighlighter):
    """Color the unified-diff text inside the inline view."""

    def __init__(self, document, tokens: ShellThemeTokens) -> None:
        super().__init__(document)
        self._add_format = QTextCharFormat()
        self._remove_format = QTextCharFormat()
        self._hunk_format = QTextCharFormat()
        self._file_format = QTextCharFormat()
        self.apply_theme(tokens)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        add_bg = _line_tint(tokens.test_passed_color or "#1A7F37", is_dark=tokens.is_dark)
        remove_bg = _line_tint(tokens.diag_error_color or "#E03131", is_dark=tokens.is_dark)
        muted_bg = QColor(tokens.row_alt_bg or tokens.panel_bg)

        self._add_format.setBackground(add_bg)
        self._add_format.setForeground(QColor(tokens.text_primary))

        self._remove_format.setBackground(remove_bg)
        self._remove_format.setForeground(QColor(tokens.text_primary))

        self._hunk_format.setBackground(muted_bg)
        self._hunk_format.setForeground(QColor(tokens.text_muted))
        self._hunk_format.setFontItalic(True)

        self._file_format.setForeground(QColor(tokens.text_muted))
        self._file_format.setFontWeight(600)

        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt signature
        if not text:
            return
        if text.startswith("@@"):
            self.setFormat(0, len(text), self._hunk_format)
            return
        if text.startswith("---") or text.startswith("+++"):
            self.setFormat(0, len(text), self._file_format)
            return
        if text.startswith("+"):
            self.setFormat(0, len(text), self._add_format)
            return
        if text.startswith("-"):
            self.setFormat(0, len(text), self._remove_format)
            return


class _PaneHighlighter(QSyntaxHighlighter):
    """Per-pane highlighter for side-by-side mode.

    Lines are tinted by absolute line number rather than by leading
    character (the side-by-side panes contain plain source text without
    +/- markers).
    """

    def __init__(self, document, tokens: ShellThemeTokens) -> None:
        super().__init__(document)
        self._tinted_lines: dict[int, str] = {}
        self._add_format = QTextCharFormat()
        self._remove_format = QTextCharFormat()
        self._gap_format = QTextCharFormat()
        self.apply_theme(tokens)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        add_bg = _line_tint(tokens.test_passed_color or "#1A7F37", is_dark=tokens.is_dark)
        remove_bg = _line_tint(tokens.diag_error_color or "#E03131", is_dark=tokens.is_dark)
        gap_bg = QColor(tokens.row_alt_bg or tokens.panel_bg)

        self._add_format.setBackground(add_bg)
        self._add_format.setForeground(QColor(tokens.text_primary))
        self._remove_format.setBackground(remove_bg)
        self._remove_format.setForeground(QColor(tokens.text_primary))
        self._gap_format.setBackground(gap_bg)
        self._gap_format.setForeground(QColor(tokens.text_muted))
        self.rehighlight()

    def set_line_kinds(self, line_kinds: dict[int, str]) -> None:
        self._tinted_lines = dict(line_kinds)
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt signature
        block_no = self.currentBlock().blockNumber()
        kind = self._tinted_lines.get(block_no)
        if kind == LINE_KIND_ADD:
            self.setFormat(0, len(text), self._add_format)
        elif kind == LINE_KIND_REMOVE:
            self.setFormat(0, len(text), self._remove_format)
        elif kind == "gap":
            if text:
                self.setFormat(0, len(text), self._gap_format)


class _GutterArea(QWidget):
    """Two-column line-number gutter painted alongside a QPlainTextEdit."""

    def __init__(self, editor: QPlainTextEdit, owner: "DiffView") -> None:
        super().__init__(editor)
        self._editor = editor
        self._owner = owner
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
        from PySide2.QtCore import QEvent

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


class DiffView(QWidget):
    """Color-coded diff renderer with inline / side-by-side modes."""

    def __init__(self, tokens: ShellThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._mode = DIFF_VIEW_MODE_INLINE
        self._before_text = ""
        self._after_text = ""
        self._before_label = "before"
        self._after_label = "after"
        self._stats = DiffStats(added=0, removed=0)
        self._raw_diff_text = ""
        self._hunks: list[DiffHunk] = []

        self.setObjectName("shell.diffView")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack_container = QWidget(self)
        self._stack = QStackedLayout(self._stack_container)
        self._stack.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack_container, 1)

        self._message_label = QLabel("", self)
        self._message_label.setObjectName("shell.diffView.message")
        self._message_label.setAlignment(Qt.AlignCenter)
        self._message_label.setVisible(False)
        layout.addWidget(self._message_label)

        self._build_inline_view()
        self._build_side_by_side_view()
        self._stack.setCurrentWidget(self._inline_container)
        self.apply_theme(tokens)

    # -- Public API ----------------------------------------------------

    def set_texts(
        self,
        before_text: str,
        after_text: str,
        *,
        before_label: str,
        after_label: str,
    ) -> None:
        self._before_text = before_text
        self._after_text = after_text
        self._before_label = before_label
        self._after_label = after_label
        self._render()

    def set_mode(self, mode: str) -> None:
        if mode not in (DIFF_VIEW_MODE_INLINE, DIFF_VIEW_MODE_SIDE_BY_SIDE):
            raise ValueError(f"Unknown diff view mode: {mode!r}")
        if mode == self._mode:
            return
        self._mode = mode
        if mode == DIFF_VIEW_MODE_INLINE:
            self._stack.setCurrentWidget(self._inline_container)
        else:
            self._stack.setCurrentWidget(self._side_container)

    def mode(self) -> str:
        return self._mode

    def stats(self) -> DiffStats:
        return self._stats

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._tokens = tokens
        self._inline_editor.setStyleSheet(_editor_stylesheet(tokens))
        self._before_pane.setStyleSheet(_editor_stylesheet(tokens))
        self._after_pane.setStyleSheet(_editor_stylesheet(tokens))
        self._inline_highlighter.apply_theme(tokens)
        self._before_highlighter.apply_theme(tokens)
        self._after_highlighter.apply_theme(tokens)
        self._inline_gutter.apply_theme(tokens)
        self._before_gutter.apply_theme(tokens)
        self._after_gutter.apply_theme(tokens)
        self._before_label_widget.setStyleSheet(_pane_label_stylesheet(tokens))
        self._after_label_widget.setStyleSheet(_pane_label_stylesheet(tokens))
        self._message_label.setStyleSheet(
            f"color: {tokens.text_muted}; padding: 24px;"
        )

    def set_message(self, message: Optional[str]) -> None:
        """Show a centered status message instead of the diff content."""
        if message:
            self._message_label.setText(message)
            self._message_label.setVisible(True)
            self._stack_container.setVisible(False)
        else:
            self._message_label.setVisible(False)
            self._stack_container.setVisible(True)

    def toPlainText(self) -> str:  # noqa: N802 - Qt-style alias for tests
        """Return the raw unified-diff text (kept stable for legacy callers)."""
        return self._raw_diff_text

    def raw_diff_text(self) -> str:
        return self._raw_diff_text

    # -- Build helpers -------------------------------------------------

    def _build_inline_view(self) -> None:
        container = QWidget(self._stack_container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._inline_editor = QPlainTextEdit(container)
        self._inline_editor.setObjectName("shell.diffView.inline")
        self._inline_editor.setReadOnly(True)
        self._inline_editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._inline_editor.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self._inline_highlighter = _DiffInlineHighlighter(
            self._inline_editor.document(), self._tokens
        )
        self._inline_gutter = _GutterArea(self._inline_editor, self)
        self._inline_gutter.set_columns(show_old=True, show_new=True)
        layout.addWidget(self._inline_editor, 1)

        self._inline_container = container
        self._stack.addWidget(container)

    def _build_side_by_side_view(self) -> None:
        container = QWidget(self._stack_container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        labels = QHBoxLayout()
        labels.setContentsMargins(0, 0, 0, 4)
        labels.setSpacing(8)
        self._before_label_widget = QLabel(self._before_label, container)
        self._before_label_widget.setObjectName("shell.diffView.paneLabel")
        self._after_label_widget = QLabel(self._after_label, container)
        self._after_label_widget.setObjectName("shell.diffView.paneLabel")
        labels.addWidget(self._before_label_widget, 1)
        labels.addWidget(self._after_label_widget, 1)
        layout.addLayout(labels)

        splitter = QSplitter(Qt.Horizontal, container)
        splitter.setObjectName("shell.diffView.splitter")
        splitter.setChildrenCollapsible(False)

        self._before_pane = QPlainTextEdit(splitter)
        self._before_pane.setObjectName("shell.diffView.beforePane")
        self._before_pane.setReadOnly(True)
        self._before_pane.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._before_pane.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self._before_highlighter = _PaneHighlighter(
            self._before_pane.document(), self._tokens
        )
        self._before_gutter = _GutterArea(self._before_pane, self)
        self._before_gutter.set_columns(show_old=True, show_new=False)

        self._after_pane = QPlainTextEdit(splitter)
        self._after_pane.setObjectName("shell.diffView.afterPane")
        self._after_pane.setReadOnly(True)
        self._after_pane.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._after_pane.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self._after_highlighter = _PaneHighlighter(
            self._after_pane.document(), self._tokens
        )
        self._after_gutter = _GutterArea(self._after_pane, self)
        self._after_gutter.set_columns(show_old=False, show_new=True)

        splitter.addWidget(self._before_pane)
        splitter.addWidget(self._after_pane)
        splitter.setSizes([400, 400])
        layout.addWidget(splitter, 1)

        self._before_pane.verticalScrollBar().valueChanged.connect(
            self._after_pane.verticalScrollBar().setValue
        )
        self._after_pane.verticalScrollBar().valueChanged.connect(
            self._before_pane.verticalScrollBar().setValue
        )

        self._side_container = container
        self._stack.addWidget(container)

    # -- Render --------------------------------------------------------

    def _render(self) -> None:
        hunks, stats, raw_text = compute_diff_hunks(
            self._before_text,
            self._after_text,
            from_label=self._before_label,
            to_label=self._after_label,
        )
        self._hunks = hunks
        self._stats = stats
        self._raw_diff_text = raw_text or "No textual differences found."

        self._render_inline()
        self._render_side_by_side()

        self._before_label_widget.setText(self._before_label)
        self._after_label_widget.setText(self._after_label)

    def _render_inline(self) -> None:
        text = self._raw_diff_text
        self._inline_editor.setPlainText(text)
        old_numbers, new_numbers = _inline_gutter_numbers(text, self._hunks)
        self._inline_gutter.set_numbers(
            old_numbers=old_numbers,
            new_numbers=new_numbers,
        )

    def _render_side_by_side(self) -> None:
        before_pane_lines, after_pane_lines, before_kinds, after_kinds, before_nums, after_nums = (
            _side_by_side_buffers(self._hunks)
        )

        if not self._hunks:
            self._before_pane.setPlainText(self._before_text)
            self._after_pane.setPlainText(self._after_text)
            before_lines = self._before_text.splitlines() or [""]
            after_lines = self._after_text.splitlines() or [""]
            self._before_gutter.set_numbers(
                old_numbers=list(range(1, len(before_lines) + 1)),
                new_numbers=[None] * len(before_lines),
            )
            self._after_gutter.set_numbers(
                old_numbers=[None] * len(after_lines),
                new_numbers=list(range(1, len(after_lines) + 1)),
            )
            self._before_highlighter.set_line_kinds({})
            self._after_highlighter.set_line_kinds({})
            return

        self._before_pane.setPlainText("\n".join(before_pane_lines))
        self._after_pane.setPlainText("\n".join(after_pane_lines))
        self._before_gutter.set_numbers(
            old_numbers=before_nums,
            new_numbers=[None] * len(before_pane_lines),
        )
        self._after_gutter.set_numbers(
            old_numbers=[None] * len(after_pane_lines),
            new_numbers=after_nums,
        )
        self._before_highlighter.set_line_kinds(before_kinds)
        self._after_highlighter.set_line_kinds(after_kinds)


def _inline_gutter_numbers(
    raw_text: str, hunks: Iterable[DiffHunk]
) -> tuple[list[Optional[int]], list[Optional[int]]]:
    """Compute per-line gutter numbers for the inline (unified) view.

    The inline editor displays the raw unified-diff text — including
    ``---`` / ``+++`` / ``@@`` lines — so the numbering must be aligned
    line-for-line with that text.
    """

    old_numbers: list[Optional[int]] = []
    new_numbers: list[Optional[int]] = []
    if not raw_text:
        return old_numbers, new_numbers

    hunks_iter = iter(hunks)
    current_hunk: Optional[DiffHunk] = next(hunks_iter, None)
    old_cursor = 0
    new_cursor = 0

    for line in raw_text.splitlines():
        if line.startswith("---") or line.startswith("+++"):
            old_numbers.append(None)
            new_numbers.append(None)
            continue
        if line.startswith("@@"):
            if current_hunk is not None:
                old_cursor = current_hunk.old_start
                new_cursor = current_hunk.new_start
                current_hunk = next(hunks_iter, None)
            old_numbers.append(None)
            new_numbers.append(None)
            continue
        if line.startswith("+"):
            old_numbers.append(None)
            new_numbers.append(new_cursor)
            new_cursor += 1
        elif line.startswith("-"):
            old_numbers.append(old_cursor)
            new_numbers.append(None)
            old_cursor += 1
        else:
            old_numbers.append(old_cursor)
            new_numbers.append(new_cursor)
            old_cursor += 1
            new_cursor += 1

    return old_numbers, new_numbers


def _side_by_side_buffers(
    hunks: Iterable[DiffHunk],
) -> tuple[
    list[str], list[str], dict[int, str], dict[int, str], list[Optional[int]], list[Optional[int]]
]:
    """Build aligned side-by-side text and per-line classifications.

    Removed lines pad the right pane with empty rows, additions pad the
    left pane.  Returns ``(before_lines, after_lines, before_kinds,
    after_kinds, before_numbers, after_numbers)`` where ``*_kinds`` map
    a 0-based block number to ``add`` / ``remove`` / ``gap`` / context
    (absent).
    """

    before_lines: list[str] = []
    after_lines: list[str] = []
    before_kinds: dict[int, str] = {}
    after_kinds: dict[int, str] = {}
    before_numbers: list[Optional[int]] = []
    after_numbers: list[Optional[int]] = []

    for hunk_index, hunk in enumerate(hunks):
        if hunk_index > 0:
            before_lines.append("")
            after_lines.append("")
            before_numbers.append(None)
            after_numbers.append(None)
            before_kinds[len(before_lines) - 1] = "gap"
            after_kinds[len(after_lines) - 1] = "gap"

        index = 0
        line_count = len(hunk.lines)
        while index < line_count:
            line = hunk.lines[index]
            if line.kind == LINE_KIND_CONTEXT:
                before_lines.append(line.text)
                after_lines.append(line.text)
                before_numbers.append(line.old_no)
                after_numbers.append(line.new_no)
                index += 1
                continue

            removes: list[DiffLine] = []
            adds: list[DiffLine] = []
            while index < line_count and hunk.lines[index].kind == LINE_KIND_REMOVE:
                removes.append(hunk.lines[index])
                index += 1
            while index < line_count and hunk.lines[index].kind == LINE_KIND_ADD:
                adds.append(hunk.lines[index])
                index += 1

            paired = max(len(removes), len(adds))
            for slot in range(paired):
                remove_line = removes[slot] if slot < len(removes) else None
                add_line = adds[slot] if slot < len(adds) else None
                if remove_line is not None:
                    before_lines.append(remove_line.text)
                    before_numbers.append(remove_line.old_no)
                    before_kinds[len(before_lines) - 1] = LINE_KIND_REMOVE
                else:
                    before_lines.append("")
                    before_numbers.append(None)
                    before_kinds[len(before_lines) - 1] = "gap"
                if add_line is not None:
                    after_lines.append(add_line.text)
                    after_numbers.append(add_line.new_no)
                    after_kinds[len(after_lines) - 1] = LINE_KIND_ADD
                else:
                    after_lines.append("")
                    after_numbers.append(None)
                    after_kinds[len(after_lines) - 1] = "gap"

    if not before_lines:
        before_lines = [""]
        after_lines = [""]
        before_numbers = [None]
        after_numbers = [None]

    return (
        before_lines,
        after_lines,
        before_kinds,
        after_kinds,
        before_numbers,
        after_numbers,
    )


def _editor_stylesheet(tokens: ShellThemeTokens) -> str:
    return (
        f"QPlainTextEdit {{"
        f"  background: {tokens.editor_bg};"
        f"  color: {tokens.text_primary};"
        f"  border: 1px solid {tokens.border};"
        f"  border-radius: 6px;"
        f"  selection-background-color: {tokens.tree_selected_bg or tokens.accent};"
        f"  selection-color: {tokens.text_primary};"
        f"}}"
    )


def _pane_label_stylesheet(tokens: ShellThemeTokens) -> str:
    return (
        f"color: {tokens.text_muted};"
        f"font-size: 11px;"
        f"font-weight: 600;"
        f"text-transform: uppercase;"
        f"letter-spacing: 0.5px;"
        f"padding: 0 4px 4px 4px;"
    )
