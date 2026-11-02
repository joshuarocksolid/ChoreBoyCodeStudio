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

from typing import Optional

from app.qt.QtCore import Qt
from app.qt.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from app.qt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from app.shell.diff_gutter import DiffGutterArea
from app.shell.diff_parser import (
    LINE_KIND_ADD,
    LINE_KIND_CONTEXT,
    LINE_KIND_FILE_LABEL,
    LINE_KIND_HEADER,
    LINE_KIND_REMOVE,
    DiffHunk,
    DiffStats,
    compute_diff_hunks,
    inline_gutter_numbers,
    side_by_side_buffers,
)
from app.shell.theme_tokens import ShellThemeTokens

DIFF_VIEW_MODE_INLINE = "inline"
DIFF_VIEW_MODE_SIDE_BY_SIDE = "side_by_side"

__all__ = [
    "DIFF_VIEW_MODE_INLINE",
    "DIFF_VIEW_MODE_SIDE_BY_SIDE",
    "LINE_KIND_ADD",
    "LINE_KIND_CONTEXT",
    "LINE_KIND_FILE_LABEL",
    "LINE_KIND_HEADER",
    "LINE_KIND_REMOVE",
    "DiffHunk",
    "DiffStats",
    "DiffView",
    "compute_diff_hunks",
]


def _line_tint(base_hex: str, *, is_dark: bool) -> QColor:
    color = QColor(base_hex)
    color.setAlpha(48 if is_dark else 38)
    return color


def _word_tint(base_hex: str, *, is_dark: bool) -> QColor:
    """Stronger than the line tint, still the same green or red."""
    color = QColor(base_hex)
    color.setAlpha(180 if is_dark else 160)
    return color


def _is_metadata_header(line: str) -> bool:
    return line.startswith("--- ") or line.startswith("+++ ") or line.startswith("@@")


def _without_metadata_headers(
    text: str,
    old_numbers: list,
    new_numbers: list,
) -> tuple:
    kept_lines = []
    kept_old = []
    kept_new = []
    for index, line in enumerate(text.splitlines()):
        if _is_metadata_header(line):
            continue
        kept_lines.append(line)
        kept_old.append(old_numbers[index] if index < len(old_numbers) else None)
        kept_new.append(new_numbers[index] if index < len(new_numbers) else None)
    return "\n".join(kept_lines), kept_old, kept_new


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
        self._file_format.setFontWeight(QFont.DemiBold)

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
        self._hide_metadata_headers = False
        self._add_word = _word_tint("#1A7F37", is_dark=tokens.is_dark)
        self._remove_word = _word_tint("#E03131", is_dark=tokens.is_dark)

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

    def emphasize_changed_words(self, *, limit: int = 250) -> None:
        """Overlay intra-line highlights. ``set_texts`` stays unchanged for existing callers."""
        from difflib import SequenceMatcher

        from app.qt.QtGui import QTextCharFormat, QTextCursor
        from app.qt.QtWidgets import QTextEdit

        def paint(editor: QPlainTextEdit, groups: list[tuple[list[tuple[int, int, int]], QColor]]) -> None:
            selections = []
            for pairs, color in groups:
                strong = QTextCharFormat()
                strong.setBackground(color)
                for block_no, start, end in pairs:
                    if end <= start:
                        continue
                    block = editor.document().findBlockByNumber(block_no)
                    if not block.isValid():
                        continue
                    cursor = QTextCursor(block)
                    cursor.setPosition(block.position() + start)
                    cursor.setPosition(block.position() + end, QTextCursor.KeepAnchor)
                    selection = QTextEdit.ExtraSelection()
                    selection.cursor = cursor
                    selection.format = strong
                    selections.append(selection)
            editor.setExtraSelections(selections)

        inline_removed: list[tuple[int, int, int]] = []
        inline_added: list[tuple[int, int, int]] = []
        lines = self._inline_editor.toPlainText().splitlines()
        used = 0
        index = 0
        while index < len(lines) - 1 and used < limit:
            left = lines[index]
            right = lines[index + 1]
            if (
                left.startswith("-")
                and right.startswith("+")
                and not _is_metadata_header(left)
                and not _is_metadata_header(right)
            ):
                matcher = SequenceMatcher(a=left[1:], b=right[1:])
                for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                    if tag == "equal":
                        continue
                    inline_removed.append((index, i1 + 1, i2 + 1))
                    inline_added.append((index + 1, j1 + 1, j2 + 1))
                used += 1
                index += 2
                continue
            index += 1
        paint(
            self._inline_editor,
            [(inline_removed, self._remove_word), (inline_added, self._add_word)],
        )

        before_pairs: list[tuple[int, int, int]] = []
        after_pairs: list[tuple[int, int, int]] = []
        before_lines = self._before_pane.toPlainText().splitlines()
        after_lines = self._after_pane.toPlainText().splitlines()
        span = min(len(before_lines), len(after_lines), limit)
        for row in range(span):
            if before_lines[row] == after_lines[row]:
                continue
            matcher = SequenceMatcher(a=before_lines[row], b=after_lines[row])
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == "equal":
                    continue
                before_pairs.append((row, i1, i2))
                after_pairs.append((row, j1, j2))
        paint(self._before_pane, [(before_pairs, self._remove_word)])
        paint(self._after_pane, [(after_pairs, self._add_word)])

    def set_hide_metadata_headers(self, hide: bool) -> None:
        """Drop ``---`` / ``+++`` / ``@@`` lines from the inline view."""
        self._hide_metadata_headers = hide
        if self._raw_diff_text:
            self._render_inline()

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
        self._add_word = _word_tint(tokens.test_passed_color or "#1A7F37", is_dark=tokens.is_dark)
        self._remove_word = _word_tint(tokens.diag_error_color or "#E03131", is_dark=tokens.is_dark)

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
        self._inline_gutter = DiffGutterArea(self._inline_editor)
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
        self._before_gutter = DiffGutterArea(self._before_pane)
        self._before_gutter.set_columns(show_old=True, show_new=False)

        self._after_pane = QPlainTextEdit(splitter)
        self._after_pane.setObjectName("shell.diffView.afterPane")
        self._after_pane.setReadOnly(True)
        self._after_pane.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._after_pane.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self._after_highlighter = _PaneHighlighter(
            self._after_pane.document(), self._tokens
        )
        self._after_gutter = DiffGutterArea(self._after_pane)
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
        old_numbers, new_numbers = inline_gutter_numbers(text, self._hunks)
        if self._hide_metadata_headers:
            text, old_numbers, new_numbers = _without_metadata_headers(text, old_numbers, new_numbers)
        self._inline_editor.setPlainText(text)
        self._inline_gutter.set_numbers(
            old_numbers=old_numbers,
            new_numbers=new_numbers,
        )

    def _render_side_by_side(self) -> None:
        before_pane_lines, after_pane_lines, before_kinds, after_kinds, before_nums, after_nums = (
            side_by_side_buffers(self._hunks)
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
