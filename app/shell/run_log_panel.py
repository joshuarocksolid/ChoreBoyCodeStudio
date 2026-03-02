"""Modern Run Log panel with metadata toolbar and rich-text output."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide2.QtCore import Signal
from PySide2.QtGui import QColor, QFont, QPalette, QTextCharFormat, QTextCursor
from PySide2.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from app.shell.theme_tokens import ShellThemeTokens


@dataclass(frozen=True)
class RunInfo:
    """Lightweight summary of a completed run for toolbar display."""

    run_id: str = ""
    mode: str = ""
    entry_file: str = ""
    exit_code: int | None = None


_TB_START_RE = re.compile(r"^Traceback \(most recent call last\):")
_TB_FILE_RE = re.compile(r"^\s+File \".+\", line \d+")
_TB_EXCEPTION_RE = re.compile(r"^\w[\w.]*(?:Error|Exception|Warning|Exit)(?::\s|$)")


def _classify_line(line: str, in_traceback: bool) -> tuple[str, bool]:
    """Return (category, still_in_traceback) for a single log line.

    Categories: 'meta', 'error', 'normal'.
    """
    if line.startswith("[runner]") or line.startswith("[system]"):
        return "meta", False
    if _TB_START_RE.match(line):
        return "error", True
    if in_traceback:
        if _TB_FILE_RE.match(line) or line.startswith("    "):
            return "error", True
        if _TB_EXCEPTION_RE.match(line):
            return "error", False
        return "normal", False
    if _TB_EXCEPTION_RE.match(line):
        return "error", False
    return "normal", False


class RunLogPanel(QWidget):
    """Run Log panel with a metadata toolbar and rich-text output area."""

    open_log_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.bottom.runLog")

        self._log_path: str | None = None
        self._in_traceback = False
        self._col_text = "#E9ECEF"
        self._col_muted = "#ADB5BD"
        self._col_error = "#FF6B6B"
        self._col_success = "#3FB950"

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # -- toolbar --
        self._toolbar = QWidget(self)
        self._toolbar.setObjectName("shell.bottom.runLog.toolbar")
        tb = QHBoxLayout(self._toolbar)
        tb.setContentsMargins(8, 3, 8, 3)
        tb.setSpacing(8)

        self._status_dot = QLabel(self._toolbar)
        self._status_dot.setObjectName("shell.bottom.runLog.statusDot")
        self._status_dot.setFixedSize(8, 8)
        self._status_dot.setProperty("runLogState", "idle")
        tb.addWidget(self._status_dot)

        self._meta_label = QLabel("", self._toolbar)
        self._meta_label.setObjectName("shell.bottom.runLog.metaLabel")
        self._meta_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(self._meta_label)

        self._open_btn = QToolButton(self._toolbar)
        self._open_btn.setText("Open Log")
        self._open_btn.setObjectName("shell.bottom.runLog.openBtn")
        self._open_btn.setAutoRaise(True)
        self._open_btn.setToolTip("Open the log file in the editor")
        self._open_btn.clicked.connect(self._on_open_clicked)
        self._open_btn.setVisible(False)
        tb.addWidget(self._open_btn)

        self._clear_btn = QToolButton(self._toolbar)
        self._clear_btn.setText("Clear")
        self._clear_btn.setObjectName("shell.bottom.runLog.clearBtn")
        self._clear_btn.setAutoRaise(True)
        self._clear_btn.setToolTip("Clear the Run Log display")
        self._clear_btn.clicked.connect(self.clear)
        tb.addWidget(self._clear_btn)

        root.addWidget(self._toolbar)

        # -- text area --
        self._text = QTextEdit(self)
        self._text.setObjectName("shell.bottom.runLog.textArea")
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QTextEdit.NoWrap)
        mono = QFont("Monospace", 10)
        mono.setStyleHint(QFont.Monospace)
        self._text.setFont(mono)
        root.addWidget(self._text, 1)

    # -- public API --------------------------------------------------------

    def apply_theme(self, tokens: "ShellThemeTokens") -> None:
        self._col_text = tokens.text_primary
        self._col_muted = tokens.text_muted
        self._col_error = tokens.diag_error_color
        self._col_success = tokens.debug_running_color

        pal = self._text.palette()
        pal.setColor(QPalette.Base, QColor(tokens.editor_bg))
        pal.setColor(QPalette.Text, QColor(tokens.text_primary))
        self._text.setPalette(pal)

        self._reformat_current_content()

    def begin_run(self, run_info: RunInfo | None = None) -> None:
        """Clear display and set toolbar to 'running' for a new session."""
        self._in_traceback = False
        self._log_path = None
        self._open_btn.setVisible(False)
        self._text.clear()
        self._update_toolbar(run_info)
        self._set_status("running")

    def append_live_line(self, text: str, *, stream: str = "stdout") -> None:
        """Append a single output line with color classification and auto-scroll."""
        prefix = ""
        if stream == "stderr":
            prefix = "[stderr] "
        elif stream == "system":
            prefix = "[system] "

        fmt = self._format_for_category("normal")
        for raw_line in text.rstrip().splitlines():
            display = f"{prefix}{raw_line}" if prefix else raw_line
            category, self._in_traceback = _classify_line(display, self._in_traceback)
            fmt = self._format_for_category(category)

            cursor = self._text.textCursor()
            cursor.movePosition(QTextCursor.End)
            if self._text.toPlainText():
                cursor.insertText("\n")
            cursor.insertText(display, fmt)

        self._text.moveCursor(QTextCursor.End)

    def end_run(self, run_info: RunInfo | None = None, *, log_path: str | None = None) -> None:
        """Update toolbar status after a run finishes, keeping streamed content."""
        self._in_traceback = False
        if log_path:
            self._log_path = log_path
            self._open_btn.setVisible(True)
        self._update_toolbar(run_info)

    def set_log_content(
        self,
        text: str,
        *,
        run_info: RunInfo | None = None,
        log_path: str | None = None,
    ) -> None:
        self._log_path = log_path
        self._open_btn.setVisible(bool(log_path))
        self._update_toolbar(run_info)
        self._render_log_text(text)

    def set_empty(self, message: str = "(No run log available)") -> None:
        self._log_path = None
        self._open_btn.setVisible(False)
        self._meta_label.setText("")
        self._set_status("idle")
        self._text.clear()
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self._col_muted))
        cursor = self._text.textCursor()
        cursor.insertText(message, fmt)

    def clear(self) -> None:
        self._log_path = None
        self._open_btn.setVisible(False)
        self._meta_label.setText("")
        self._set_status("idle")
        self._text.clear()

    # -- internals ---------------------------------------------------------

    def _format_for_category(self, category: str) -> QTextCharFormat:
        fmt = QTextCharFormat()
        if category == "meta":
            fmt.setForeground(QColor(self._col_muted))
        elif category == "error":
            fmt.setForeground(QColor(self._col_error))
        else:
            fmt.setForeground(QColor(self._col_text))
        return fmt

    def _update_toolbar(self, info: RunInfo | None) -> None:
        if info is None:
            self._meta_label.setText("")
            self._set_status("idle")
            return

        parts: list[str] = []
        if info.mode:
            parts.append(info.mode.replace("_", " ").title())
        if info.entry_file:
            parts.append(info.entry_file)
        if info.run_id:
            short_id = info.run_id[-8:] if len(info.run_id) > 8 else info.run_id
            parts.append(f"({short_id})")
        self._meta_label.setText("  \u2022  ".join(parts))

        if info.exit_code is None:
            self._set_status("idle")
        elif info.exit_code == 0:
            self._set_status("success")
        else:
            self._set_status("error")

    def _set_status(self, state: str) -> None:
        self._status_dot.setProperty("runLogState", state)
        self._status_dot.style().unpolish(self._status_dot)
        self._status_dot.style().polish(self._status_dot)

    def _render_log_text(self, text: str) -> None:
        self._text.clear()
        if not text:
            return

        cursor = self._text.textCursor()
        cursor.beginEditBlock()

        fmt_normal = QTextCharFormat()
        fmt_normal.setForeground(QColor(self._col_text))

        fmt_meta = QTextCharFormat()
        fmt_meta.setForeground(QColor(self._col_muted))

        fmt_error = QTextCharFormat()
        fmt_error.setForeground(QColor(self._col_error))

        in_traceback = False
        lines = text.splitlines()
        for i, line in enumerate(lines):
            category, in_traceback = _classify_line(line, in_traceback)
            if category == "meta":
                fmt = fmt_meta
            elif category == "error":
                fmt = fmt_error
            else:
                fmt = fmt_normal
            if i > 0:
                cursor.insertText("\n")
            cursor.insertText(line, fmt)

        cursor.endEditBlock()
        self._text.moveCursor(QTextCursor.Start)

    def _reformat_current_content(self) -> None:
        """Re-render existing text with updated theme colors."""
        raw = self._text.toPlainText()
        if raw:
            self._render_log_text(raw)

    def _on_open_clicked(self) -> None:
        if self._log_path:
            self.open_log_requested.emit(self._log_path)
