"""Prompt shown when CBCS closes while a program it started is still running.

Clair (3 Oct): closing CBCS also closed the FreeCAD window her program had
opened. The runner leads its own process group, and a plain ``Popen`` in the
user's program joins that group, so stopping the run took FreeCAD with it.
This prompt lets the user keep the program (and its windows) running.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import os
from pathlib import Path
from typing import Any, Optional, Sequence

from PySide2.QtCore import Qt
from PySide2.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide2.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.core import constants
from app.shell.dialog_chrome import (
    FOOTER_ROLE_DESTRUCTIVE_SECONDARY,
    FOOTER_ROLE_PRIMARY,
    FOOTER_ROLE_SECONDARY,
    add_footer_button,
    add_footer_stretch,
    build_dialog_chrome,
)
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette
from app.shell.unsaved_changes_dialog import _warning_icon

WINDOW_TITLE = "Close ChoreBoy Code Studio"
TITLE = "A program you started from CBCS is still running"
SUBTITLE = "Choose what happens to it when CBCS closes."
STOP_HELP = (
    "<b>Stop It</b> ends the program and every window it opened, such as FreeCAD, "
    "then closes CBCS. Unsaved work in those windows is lost."
)
KEEP_HELP = (
    "<b>Keep It Running</b> closes CBCS and leaves the program open. "
    "Its output no longer appears in the Run Log."
)
DEBUG_HELP = (
    "A program started with <b>Debug</b> cannot keep running without CBCS. "
    "Use Run instead of Debug if it should stay open after CBCS closes."
)
CANCEL_HELP = "<b>Cancel</b> keeps CBCS open."

_DIALOG_OBJECT_NAME = "shell.closeWhileRunningDialog"
_CARD_OBJECT_NAME = "shell.closeWhileRunningDialog.runCard"
_RUN_NAME_OBJECT_NAME = "shell.closeWhileRunningDialog.runName"
_RUN_DETAIL_OBJECT_NAME = "shell.closeWhileRunningDialog.runDetail"
_ALSO_OPENED_OBJECT_NAME = "shell.closeWhileRunningDialog.alsoOpened"
_HELP_OBJECT_NAME = "shell.closeWhileRunningDialog.help"

_SHELL_NAMES = frozenset({"sh", "bash", "dash"})


class CloseRunChoice(str, Enum):
    """What the user picked for the running program."""

    CANCEL = "cancel"
    STOP = "stop"
    KEEP = "keep"


@dataclass(frozen=True)
class RunningProgramSummary:
    """Everything the prompt shows about the running program."""

    name: str
    running_for: str
    started_with: str
    also_opened: tuple[str, ...] = ()
    can_keep_running: bool = True


def format_running_for(elapsed_seconds: float) -> str:
    """Return ``Running for ...`` in whole minutes / hours."""
    minutes = max(0, int(elapsed_seconds // 60))
    if minutes < 1:
        return "Running for less than a minute"
    if minutes < 60:
        return "Running for 1 minute" if minutes == 1 else f"Running for {minutes} minutes"
    hours, rest = divmod(minutes, 60)
    text = "1 hour" if hours == 1 else f"{hours} hours"
    if rest:
        text += " 1 minute" if rest == 1 else f" {rest} minutes"
    return f"Running for {text}"


def _read_text(path: str) -> str:
    try:
        with open(path, "rb") as handle:
            return handle.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _process_group_of(stat_text: str) -> Optional[int]:
    # /proc/<pid>/stat: "pid (comm) state ppid pgrp ..." (comm may contain spaces).
    closing = stat_text.rfind(")")
    if closing < 0:
        return None
    fields = stat_text[closing + 1 :].split()
    if len(fields) < 3:
        return None
    try:
        return int(fields[2])
    except ValueError:
        return None


def _freecad_window_label(argv: Sequence[str]) -> Optional[str]:
    args = [arg for arg in argv if arg]
    if args and os.path.basename(args[0]) in _SHELL_NAMES and len(args) > 1 and not args[1].startswith("-"):
        args = args[1:]
    if not args:
        return None
    program = os.path.basename(args[0]).lower()
    if "freecad" not in args[0].lower() or program not in {"freecad", "apprun"}:
        return None
    if any(arg in ("-c", "--console") for arg in args[1:]):
        return None
    documents = [os.path.basename(arg) for arg in args[1:] if arg.lower().endswith(".fcstd")]
    if documents:
        return f"FreeCAD ({', '.join(documents)})"
    return "FreeCAD"


def find_opened_windows(process_group_id: int, *, proc_root: str = "/proc") -> tuple[str, ...]:
    """Name the FreeCAD windows started inside the run's process group.

    Linux only (reads ``/proc``). Returns ``()`` when nothing is known, so the
    prompt leaves the "It also opened" line out.
    """
    try:
        entries = os.listdir(proc_root)
    except OSError:
        return ()
    labels: list[str] = []
    for entry in sorted(entries, key=lambda name: (len(name), name)):
        if not entry.isdigit() or int(entry) == process_group_id:
            continue
        if _process_group_of(_read_text(os.path.join(proc_root, entry, "stat"))) != process_group_id:
            continue
        argv = _read_text(os.path.join(proc_root, entry, "cmdline")).split("\0")
        label = _freecad_window_label(argv)
        if label is not None and label not in labels:
            labels.append(label)
    return tuple(labels)


def build_running_program_summary(
    session: Any,
    *,
    loaded_project: Any,
    process_id: Optional[int],
    now: Optional[datetime] = None,
) -> RunningProgramSummary:
    """Describe the active run for the prompt. ``session`` is a ``RunSession``."""
    entry_file = str(getattr(session, "entry_file", "") or "")
    mode = str(getattr(session, "mode", "") or "")
    name = Path(entry_file).name or "Your program"
    project_name = ""
    default_entry = ""
    if loaded_project is not None:
        metadata = getattr(loaded_project, "metadata", None)
        project_name = str(getattr(metadata, "name", "") or "")
        default_entry = str(getattr(metadata, "default_entry", "") or "")
        project_root = str(getattr(loaded_project, "project_root", "") or "")
        if default_entry and project_root:
            default_entry = str(Path(project_root, default_entry))
    if project_name:
        name = f"{name}  ({project_name})"

    started_at = getattr(session, "started_at", None)
    if isinstance(started_at, datetime):
        running_for = format_running_for(((now or datetime.now()) - started_at).total_seconds())
    else:
        running_for = "Running"

    is_debug = mode == constants.RUN_MODE_PYTHON_DEBUG
    if is_debug:
        started_with = "started with Debug"
    elif default_entry and entry_file and Path(entry_file) == Path(default_entry):
        started_with = "started with Run Project"
    else:
        started_with = "started with Run File"

    also_opened = find_opened_windows(process_id) if process_id else ()
    return RunningProgramSummary(
        name=name,
        running_for=running_for,
        started_with=started_with,
        also_opened=also_opened,
        can_keep_running=not is_debug,
    )


def _resolve_tokens(dialog: QDialog) -> ShellThemeTokens:
    accessor = getattr(dialog.parent(), "current_theme_tokens", None)
    if callable(accessor):
        try:
            resolved = accessor()
        except (AttributeError, RuntimeError):
            resolved = None
        if isinstance(resolved, ShellThemeTokens):
            return resolved
    return tokens_from_palette(dialog.palette())


def _dot_icon(color_hex: str, size: int = 10, canvas: int = 14) -> QIcon:
    pixmap = QPixmap(canvas, canvas)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color_hex))
    offset = (canvas - size) // 2
    painter.drawEllipse(offset, offset, size, size)
    painter.end()
    return QIcon(pixmap)


def _style_sheet(tokens: ShellThemeTokens) -> str:
    info = tokens.diag_info_color or tokens.accent
    return f"""
QDialog#shell\\.closeWhileRunningDialog {{
    background: {tokens.window_bg};
    color: {tokens.text_primary};
}}
QLabel#shell\\.dialogChrome\\.icon {{ background: transparent; }}
QFrame#shell\\.closeWhileRunningDialog\\.runCard {{
    background: {tokens.panel_bg};
    border: 1px solid {tokens.border};
    border-left: 3px solid {info};
    border-radius: 6px;
}}
QLabel#shell\\.closeWhileRunningDialog\\.runName {{
    color: {tokens.text_primary};
    font-size: 13px;
    font-weight: 700;
    background: transparent;
}}
QLabel#shell\\.closeWhileRunningDialog\\.runDetail,
QLabel#shell\\.closeWhileRunningDialog\\.alsoOpened {{
    color: {tokens.text_muted};
    font-size: 12px;
    background: transparent;
}}
QLabel#shell\\.closeWhileRunningDialog\\.help {{
    color: {tokens.text_primary};
    font-size: 12px;
    background: transparent;
}}
QLabel#shell\\.closeWhileRunningDialog\\.help[muted="true"] {{
    color: {tokens.text_muted};
}}
"""


class CloseWhileRunningDialog(QDialog):
    """Cancel / Stop It / Keep It Running (default)."""

    def __init__(self, parent: Optional[QWidget], summary: RunningProgramSummary) -> None:
        super().__init__(parent)
        self._choice = CloseRunChoice.CANCEL
        tokens = _resolve_tokens(self)
        self.setWindowTitle(WINDOW_TITLE)
        self.setModal(True)
        warning_color = tokens.diag_warning_color or ("#F59F00" if tokens.is_dark else "#E08E00")
        chrome = build_dialog_chrome(
            self,
            title=TITLE,
            subtitle=SUBTITLE,
            object_name=_DIALOG_OBJECT_NAME,
            icon=_warning_icon(warning_color, size=22),
        )
        self.setStyleSheet(_style_sheet(tokens))
        body = chrome.body.layout()
        assert isinstance(body, QVBoxLayout)
        body.addWidget(self._build_run_card(chrome.body, summary, tokens))
        body.addWidget(self._help_label(chrome.body, STOP_HELP))
        body.addWidget(self._help_label(chrome.body, KEEP_HELP if summary.can_keep_running else DEBUG_HELP))
        body.addWidget(self._help_label(chrome.body, CANCEL_HELP, muted=True))

        cancel = add_footer_button(chrome, "Cancel", role=FOOTER_ROLE_SECONDARY)
        add_footer_stretch(chrome)
        cancel.clicked.connect(self.reject)
        self.stop_button = add_footer_button(
            chrome,
            "Stop It",
            role=FOOTER_ROLE_DESTRUCTIVE_SECONDARY,
            default=not summary.can_keep_running,
        )
        self.stop_button.clicked.connect(lambda: self._choose(CloseRunChoice.STOP))
        self.keep_button: Optional[Any] = None
        if summary.can_keep_running:
            self.keep_button = add_footer_button(chrome, "Keep It Running", role=FOOTER_ROLE_PRIMARY, default=True)
            self.keep_button.clicked.connect(lambda: self._choose(CloseRunChoice.KEEP))
            self.keep_button.setFocus()
        self.setMinimumWidth(580)
        self.adjustSize()

    @property
    def choice(self) -> CloseRunChoice:
        return self._choice

    def _choose(self, choice: CloseRunChoice) -> None:
        self._choice = choice
        self.accept()

    def reject(self) -> None:  # type: ignore[override]
        self._choice = CloseRunChoice.CANCEL
        super().reject()

    @staticmethod
    def _help_label(parent: QWidget, html: str, *, muted: bool = False) -> QLabel:
        label = QLabel(html, parent)
        label.setObjectName(_HELP_OBJECT_NAME)
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        if muted:
            label.setProperty("muted", True)
        return label

    @staticmethod
    def _build_run_card(parent: QWidget, summary: RunningProgramSummary, tokens: ShellThemeTokens) -> QFrame:
        card = QFrame(parent)
        card.setObjectName(_CARD_OBJECT_NAME)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        dot = QLabel(card)
        dot.setPixmap(_dot_icon(tokens.test_passed_color or "#1A7F37").pixmap(14, 14))
        layout.addWidget(dot, 0, Qt.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        name = QLabel(summary.name, card)
        name.setObjectName(_RUN_NAME_OBJECT_NAME)
        name.setTextFormat(Qt.PlainText)
        text.addWidget(name)
        detail = QLabel(f"{summary.running_for}  ·  {summary.started_with}", card)
        detail.setObjectName(_RUN_DETAIL_OBJECT_NAME)
        detail.setTextFormat(Qt.PlainText)
        text.addWidget(detail)
        if summary.also_opened:
            opened = QLabel("It also opened: " + ", ".join(summary.also_opened), card)
            opened.setObjectName(_ALSO_OPENED_OBJECT_NAME)
            opened.setTextFormat(Qt.PlainText)
            opened.setWordWrap(True)
            text.addWidget(opened)
        layout.addLayout(text, 1)
        return card


def prompt_close_while_running(parent: Optional[QWidget], summary: RunningProgramSummary) -> CloseRunChoice:
    """Show the prompt and return the user's choice (Cancel on Esc / window close)."""
    dialog = CloseWhileRunningDialog(parent, summary)
    dialog.exec_()
    return dialog.choice
