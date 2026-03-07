"""Inline terminal-style Python console widget.

Replaces the split output-box + input-row design with a single QTextEdit
subclass where the user types directly after the ``>>> `` prompt, just like
a real Python REPL.  Past output is read-only; the cursor always lives at
the end of the current input line.
"""

from __future__ import annotations

import code
from pathlib import Path

from PySide2.QtCore import Qt, Signal
from PySide2.QtGui import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QFontDatabase,
    QKeyEvent,
    QPalette,
    QTextCharFormat,
    QTextCursor,
)
from PySide2.QtWidgets import QInputDialog, QMenu, QTextEdit

from app.shell.theme_tokens import ShellThemeTokens


_PROMPT = ">>> "
_CONT_PROMPT = "... "
_PROMPT_LEN = len(_PROMPT)
_MAX_HISTORY = 200

# FreeCAD prints module-load messages during process teardown that are not
# meaningful to the user.  Filter them out of the console output.
_FREECAD_TEARDOWN_PREFIXES = ("Loading Post Frame Workbench Module",)


class PythonConsoleWidget(QTextEdit):
    """A terminal-style inline REPL console.

    Signals
    -------
    input_submitted(str):
        Emitted when the user presses Enter with non-empty input.
    interrupt_requested():
        Emitted when the user presses Ctrl+C without a text selection.
    """

    input_submitted: Signal = Signal(str)
    interrupt_requested: Signal = Signal()
    restart_requested: Signal = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # Position in the document right after the ">>> " prefix — this is
        # where user-editable input begins.  -1 means no active prompt.
        self._prompt_anchor: int = -1

        self._history: list[str] = []
        self._history_index: int = 0
        self._session_active: bool = False
        self._pending_block_lines: list[str] = []

        # Token-derived colors (set proper values via apply_theme).
        self._col_text: str = "#E9ECEF"
        self._col_muted: str = "#ADB5BD"
        self._col_accent: str = "#5B8CFF"
        self._col_error: str = "#FF6B6B"
        self._col_error_dim: str = "#CC8080"
        self._col_bg: str = "#1B1F23"

        self._setup_appearance()
        self._render_startup_hint()
        self._show_prompt()

    # ------------------------------------------------------------------
    # Appearance / theme
    # ------------------------------------------------------------------

    def _setup_appearance(self) -> None:
        self.setReadOnly(False)
        self.setUndoRedoEnabled(False)
        self.setLineWrapMode(QTextEdit.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setAcceptRichText(False)
        self.setAcceptDrops(True)
        self.setCursorWidth(2)

        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        font.setPointSize(10)
        self.setFont(font)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        """Update widget colors from theme tokens (call on every theme change)."""
        self._col_text = tokens.text_primary
        self._col_muted = tokens.text_muted
        self._col_accent = tokens.accent
        self._col_bg = tokens.editor_bg
        self._col_error = "#FF6B6B" if tokens.is_dark else "#CC0000"
        self._col_error_dim = "#CC8080" if tokens.is_dark else "#994444"

        palette = self.palette()
        palette.setColor(QPalette.Base, QColor(tokens.editor_bg))
        palette.setColor(QPalette.Text, QColor(tokens.text_primary))
        self.setPalette(palette)

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def clear(self) -> None:  # type: ignore[override]
        super().clear()
        self._prompt_anchor = -1
        self._pending_block_lines.clear()

    def clear_console(self) -> None:
        """User-facing clear: wipe the display and re-show a fresh prompt.

        Unlike ``clear()`` this preserves session-active state and history so
        the REPL session can continue seamlessly.
        """
        self.clear()
        self._show_prompt()

    def set_session_active(self, active: bool) -> None:
        """Show or hide the interactive prompt.

        Call with ``True`` when a REPL session starts and ``False`` when it
        ends. The session-end message should be appended *before* calling with
        ``False`` so it appears above the deactivation notice.
        """
        if active:
            self._session_active = True
            self._pending_block_lines.clear()
            if self._prompt_anchor < 0:
                self._show_prompt()
        else:
            self._session_active = False
            self._pending_block_lines.clear()
            if self._prompt_anchor < 0:
                self._show_prompt()

    # ------------------------------------------------------------------
    # Output appending (called by MainWindow on runner events)
    # ------------------------------------------------------------------

    def append_output(self, text: str, stream: str = "stdout") -> None:
        """Append *text* from the runner before the current prompt line.

        - ``stderr`` output is rendered in the error color.
        - Lines starting with ``[system]`` or ``[debug]`` get distinct styles.
        - Known FreeCAD teardown noise is silently dropped.
        - Auto-scroll only fires when the view was already pinned to the bottom.
        """
        if any(text.lstrip().startswith(p) for p in _FREECAD_TEARDOWN_PREFIXES):
            return

        at_bottom = self._is_at_bottom()

        if self._prompt_anchor < 0:
            self._append_at_end(text, stream)
        else:
            self._insert_before_prompt(text, stream)

        # Document modifications can cause Qt to re-derive the widget's
        # current char format from the character at the cursor position
        # (the prompt's accent format).  Re-assert the default so that
        # subsequent user typing stays in the neutral text color.
        self.setCurrentCharFormat(self._default_fmt())

        if at_bottom:
            self._scroll_to_bottom()

    def _append_at_end(self, text: str, stream: str) -> None:
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.End)
        text_to_insert = text if text.endswith("\n") else text + "\n"
        cursor.insertText(text_to_insert, self._fmt_for(stream, text))

    def _insert_before_prompt(self, text: str, stream: str) -> None:
        """Insert *text* before the prompt line, updating ``_prompt_anchor``."""
        prompt_start = self._prompt_anchor - _PROMPT_LEN
        text_to_insert = text if text.endswith("\n") else text + "\n"

        cursor = QTextCursor(self.document())
        cursor.setPosition(prompt_start)
        cursor.insertText(text_to_insert, self._fmt_for(stream, text))

        # Shift the anchor by however many characters were inserted.
        self._prompt_anchor += len(text_to_insert)

    # ------------------------------------------------------------------
    # Key handling
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        key = event.key()
        mods = _enum_int(event.modifiers())

        _ctrl = _enum_int(Qt.ControlModifier)
        _alt = _enum_int(Qt.AltModifier)
        _shift = _enum_int(Qt.ShiftModifier)

        # Ctrl+C: copy selection or send interrupt signal.
        if key == Qt.Key_C and mods == _ctrl:
            if self.textCursor().hasSelection():
                self.copy()
            elif self._session_active:
                self.interrupt_requested.emit()
            return

        # Ctrl+A: select all (allow, but move cursor to end after).
        if key == Qt.Key_A and mods == _ctrl:
            super().keyPressEvent(event)
            return

        if key == Qt.Key_R and mods == _ctrl:
            self._show_history_search_picker()
            return

        # Clipboard paste — allow, but protect the prompt boundary afterwards.
        if key == Qt.Key_V and mods == _ctrl:
            cursor = self.textCursor()
            if cursor.position() < self._prompt_anchor:
                cursor.movePosition(QTextCursor.End)
                self.setTextCursor(cursor)
            super().keyPressEvent(event)
            return

        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._submit()
            return

        if key == Qt.Key_Up and not (mods & _alt):
            self._history_up()
            return

        if key == Qt.Key_Down and not (mods & _alt):
            self._history_down()
            return

        # Home → jump to just after the prompt prefix.
        if key == Qt.Key_Home:
            cursor = self.textCursor()
            new_pos = self._prompt_anchor
            if mods & _shift:
                cursor.setPosition(new_pos, QTextCursor.KeepAnchor)
            else:
                cursor.setPosition(new_pos)
            self.setTextCursor(cursor)
            return

        cursor = self.textCursor()
        sel_start = min(cursor.position(), cursor.anchor())

        # Left / Backspace: block movement/deletion into the prompt prefix.
        if key == Qt.Key_Left:
            if cursor.position() <= self._prompt_anchor:
                return
            super().keyPressEvent(event)
            return

        if key == Qt.Key_Backspace:
            if sel_start < self._prompt_anchor:
                return
            if not cursor.hasSelection() and cursor.position() <= self._prompt_anchor:
                return
            super().keyPressEvent(event)
            return

        # Delete: block deletion of the prompt character.
        if key == Qt.Key_Delete:
            if sel_start < self._prompt_anchor:
                return
            super().keyPressEvent(event)
            return

        # For any printable character: if cursor is before the prompt, jump to end.
        if cursor.position() < self._prompt_anchor and event.text():
            cursor.movePosition(QTextCursor.End)
            self.setTextCursor(cursor)

        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        """Allow clicking anywhere (for text selection); keep editing at end."""
        super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:  # type: ignore[override]
        menu: QMenu = self.createStandardContextMenu()
        menu.addSeparator()
        clear_action = menu.addAction("Clear Console")
        clear_action.triggered.connect(self.clear_console)
        restart_action = menu.addAction("Restart Python Console")
        restart_action.triggered.connect(self.restart_requested.emit)
        menu.exec_(event.globalPos())

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 - Qt signature
        mime_data = event.mimeData()
        if mime_data is None or not mime_data.hasUrls():
            event.ignore()
            return
        local_files = [url for url in mime_data.urls() if url.isLocalFile()]
        if not local_files:
            event.ignore()
            return
        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 - Qt signature
        mime_data = event.mimeData()
        if mime_data is None or not mime_data.hasUrls():
            event.ignore()
            return
        local_paths = [url.toLocalFile() for url in mime_data.urls() if url.isLocalFile()]
        if not local_paths:
            event.ignore()
            return
        if self._handle_dropped_local_path(local_paths[0]):
            event.acceptProposedAction()
            return
        event.ignore()

    # ------------------------------------------------------------------
    # Submission and history
    # ------------------------------------------------------------------

    def _submit(self) -> None:
        line_text = self._get_input_text()

        # Visually commit the typed line (append newline).
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.End)
        cursor.insertText("\n", self._default_fmt())
        self.setTextCursor(cursor)

        # Invalidate the prompt anchor until the new prompt is shown.
        self._prompt_anchor = -1
        candidate_lines = [*self._pending_block_lines, line_text]
        source = "\n".join(candidate_lines)
        complete = _is_source_complete(source)
        has_visible_input = bool(source.strip())

        if not complete:
            self._pending_block_lines = candidate_lines
            if self._session_active:
                self._show_prompt(continuation=True)
            return

        self._pending_block_lines.clear()

        if has_visible_input:
            history_entry = source.rstrip("\n")
            if not self._history or self._history[-1] != history_entry:
                self._history.append(history_entry)
                if len(self._history) > _MAX_HISTORY:
                    self._history.pop(0)
            self._history_index = len(self._history)
            self._show_prompt()
            self.input_submitted.emit(source)
            return

        self._history_index = len(self._history)
        self._show_prompt()

    def _history_up(self) -> None:
        if not self._history:
            return
        self._history_index = max(0, self._history_index - 1)
        self._replace_input(self._history[self._history_index])

    def _history_down(self) -> None:
        if not self._history:
            return
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._replace_input(self._history[self._history_index])
        else:
            self._history_index = len(self._history)
            self._replace_input("")

    # ------------------------------------------------------------------
    # Prompt management
    # ------------------------------------------------------------------

    def _show_prompt(self, prefill: str = "", *, continuation: bool = False) -> None:
        """Append a prompt and position the cursor after it."""
        self.setReadOnly(False)
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.End)
        prompt = _CONT_PROMPT if continuation else _PROMPT

        prompt_fmt = QTextCharFormat()
        prompt_fmt.setForeground(QColor(self._col_accent))
        prompt_fmt.setFontWeight(QFont.Bold)
        cursor.insertText(prompt, prompt_fmt)

        default_fmt = self._default_fmt()
        cursor.setCharFormat(default_fmt)

        self._prompt_anchor = cursor.position()

        if prefill:
            cursor.insertText(prefill, default_fmt)

        self.setTextCursor(cursor)
        self.setCurrentCharFormat(default_fmt)
        self._scroll_to_bottom()

    def _handle_dropped_local_path(self, local_path: str) -> bool:
        path = Path(local_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            self.append_output(
                f"[system] Drop ignored: file not found: {path}\n",
                "system",
            )
            return False
        if path.suffix.lower() != ".py":
            self.append_output(
                f"[system] Drop ignored: '{path.name}' is not a Python file.\n",
                "system",
            )
            return False
        command = self._command_for_dropped_file(path)
        self.append_output(f"[system] Executing dropped file: {path}\n", "system")
        self._replace_input(command)
        self._submit()
        return True

    def _command_for_dropped_file(self, path: Path) -> str:
        return f"import runpy; runpy.run_path({repr(str(path))}, run_name='__main__')"

    def _render_startup_hint(self) -> None:
        """Display a brief startup message while the REPL process launches."""
        self.setReadOnly(False)
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self._col_muted))
        fmt.setFontItalic(True)
        cursor.insertText(
            "Starting Python Console\u2026\n",
            fmt,
        )
        self.setTextCursor(cursor)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_input_text(self) -> str:
        if self._prompt_anchor < 0:
            return ""
        return self.document().toPlainText()[self._prompt_anchor:]

    def _replace_input(self, text: str) -> None:
        """Replace text after the prompt with *text* (used for history)."""
        if self._prompt_anchor < 0:
            return
        cursor = QTextCursor(self.document())
        cursor.setPosition(self._prompt_anchor)
        cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        default_fmt = self._default_fmt()
        cursor.insertText(text, default_fmt)
        self.setTextCursor(cursor)
        self.setCurrentCharFormat(default_fmt)

    def _is_at_bottom(self) -> bool:
        bar = self.verticalScrollBar()
        return bar.value() >= bar.maximum() - 4

    def _scroll_to_bottom(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _default_fmt(self) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self._col_text))
        fmt.setFontWeight(QFont.Normal) 
        fmt.setFontItalic(False)
        return fmt

    def _fmt_for(self, stream: str, text: str) -> QTextCharFormat:
        """Return a ``QTextCharFormat`` appropriate for *stream* / *text*.

        For ``stderr``, traceback context lines (header, ``File`` locations,
        source echoes) use a softer dimmed-error color so the final error
        message line stands out.
        """
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Normal)

        if stream == "stderr":
            if _is_traceback_context(text):
                fmt.setForeground(QColor(self._col_error_dim))
            else:
                fmt.setForeground(QColor(self._col_error))
        elif stream == "system" or text.lstrip().startswith("[system]"):
            fmt.setForeground(QColor(self._col_muted))
            fmt.setFontItalic(True)
        elif text.lstrip().startswith("[debug]"):
            fmt.setForeground(QColor(self._col_accent))
        else:
            fmt.setForeground(QColor(self._col_text))

        return fmt

    # ------------------------------------------------------------------
    # Expose internals for testing
    # ------------------------------------------------------------------

    @property
    def prompt_anchor(self) -> int:
        return self._prompt_anchor

    @property
    def history(self) -> list[str]:
        return list(self._history)

    def history_snapshot(self) -> list[str]:
        return list(self._history)

    def set_history(self, entries: list[str]) -> None:
        normalized = [entry for entry in entries if isinstance(entry, str) and entry.strip()]
        if len(normalized) > _MAX_HISTORY:
            normalized = normalized[-_MAX_HISTORY:]
        self._history = normalized
        self._history_index = len(self._history)

    def _show_history_search_picker(self) -> None:
        if not self._history:
            return
        current_query = self._get_input_text().strip().lower()
        candidates = list(reversed(self._history))
        if current_query:
            filtered = [entry for entry in candidates if current_query in entry.lower()]
            if filtered:
                candidates = filtered
        selected, accepted = QInputDialog.getItem(
            self,
            "Console History",
            "Select command:",
            candidates,
            0,
            False,
        )
        if not accepted or not selected:
            return
        self._replace_input(str(selected))


def _is_source_complete(source: str) -> bool:
    """Return True when *source* forms a complete Python REPL block."""
    try:
        return code.compile_command(source, symbol="single") is not None
    except (OverflowError, SyntaxError, ValueError):
        # Syntax errors should still be submitted so runner REPL prints them.
        return True


def _is_traceback_context(text: str) -> bool:
    """Return True for traceback frame/context lines (not the final error)."""
    stripped = text.lstrip()
    return (
        stripped.startswith("Traceback (most recent call last)")
        or stripped.startswith("File \"")
        or stripped.startswith("During handling of the above exception")
        or (text.startswith(" ") and not stripped.startswith("^"))
    )


def _enum_int(value: object) -> int:
    enum_value = getattr(value, "value", value)
    return int(enum_value)
