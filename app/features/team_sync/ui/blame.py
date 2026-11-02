"""Hover card for the line under the pointer, plus the faint end-of-line summary."""

from __future__ import annotations

from typing import Callable, Optional

from app.qt.QtCore import QPoint, Qt
from app.qt.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.features.team_sync.api import BlameLine
from app.features.team_sync.ui.copy import short_date
from app.features.team_sync.ui.theme import button_qss, surface_qss
from app.features.team_sync.ui.widgets import Avatar
from app.shell.theme_tokens import ShellThemeTokens


class BlameCard(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, Qt.ToolTip)
        self.setObjectName("shell.teamSync.hoverCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        row = QHBoxLayout()
        self._avatar = Avatar("", "", self)
        row.addWidget(self._avatar)
        self._title = QLabel("", self)
        row.addWidget(self._title, 1)
        layout.addLayout(row)
        self._note = QLabel("", self)
        self._note.setWordWrap(True)
        layout.addWidget(self._note)
        self._diff = QLabel("", self)
        self._diff.setWordWrap(True)
        layout.addWidget(self._diff)
        actions = QHBoxLayout()
        self._open = QPushButton("Open Change", self)
        self._open.setObjectName("shell.teamSync.hoverOpen")
        self._history = QPushButton("File History", self)
        self._history.setObjectName("shell.teamSync.hoverHistory")
        actions.addWidget(self._open)
        actions.addWidget(self._history)
        layout.addLayout(actions)
        self._on_open: Optional[Callable[[], None]] = None
        self._on_history: Optional[Callable[[], None]] = None
        self._open.clicked.connect(self._click_open)
        self._history.clicked.connect(self._click_history)
        self.setMinimumWidth(260)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self.setStyleSheet(
            surface_qss(tokens)
            + "QFrame#shell\\.teamSync\\.hoverCard {"
            f" border: 1px solid {tokens.border}; border-radius: 8px; }}"
        )
        self._open.setStyleSheet(button_qss(tokens))
        self._history.setStyleSheet(button_qss(tokens))

    def show_line(
        self,
        line: BlameLine,
        shop: str,
        diff_text: str,
        global_pos: QPoint,
        *,
        on_open: Callable[[], None],
        on_history: Callable[[], None],
    ) -> None:
        self._avatar.set_person(line.author_id, line.author_name)
        self._title.setText(f"{line.author_name} · {shop} · {short_date(line.when)}")
        self._note.setText(line.note)
        self._diff.setText(diff_text)
        self._on_open = on_open
        self._on_history = on_history
        self.adjustSize()
        self.move(global_pos)
        self.show()
        self.raise_()

    def _click_open(self) -> None:
        if self._on_open is not None:
            self._on_open()

    def _click_history(self) -> None:
        if self._on_history is not None:
            self._on_history()


class LineSummary(QLabel):
    """Faint end-of-line note for the cursor line. Hidden unless the setting is on."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.teamSync.lineSummary")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.hide()

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self.setStyleSheet(f"color: {tokens.text_muted}; background: transparent; font-size: 11px;")

    def show_text(self, text: str, x: int, y: int) -> None:
        if not text:
            self.hide()
            return
        self.setText(text)
        self.adjustSize()
        self.move(x, y)
        self.show()


__all__ = ["BlameCard", "LineSummary"]
