"""Hover card for the line under the pointer, plus the faint end-of-line summary."""

from __future__ import annotations

from typing import Callable, Optional

from app.qt.QtCore import QPoint, Qt
from app.qt.QtGui import QColor
from app.qt.QtWidgets import QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.features.team_sync.api import BlameLine
from app.features.team_sync.ui.copy import short_date
from app.features.team_sync.ui.widgets import Avatar
from app.shell.theme_tokens import ShellThemeTokens


class BlameCard(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, Qt.ToolTip)
        self.setObjectName("shell.teamSync.hoverCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QHBoxLayout()
        header.setContentsMargins(12, 10, 12, 8)
        header.setSpacing(8)
        self._avatar = Avatar("", "", self, size=28)
        header.addWidget(self._avatar)
        text = QVBoxLayout()
        text.setSpacing(0)
        self._title = QLabel("", self)
        self._title.setObjectName("shell.teamSync.hoverName")
        self._meta = QLabel("", self)
        self._meta.setObjectName("shell.teamSync.hoverMeta")
        text.addWidget(self._title)
        text.addWidget(self._meta)
        header.addLayout(text, 1)
        layout.addLayout(header)
        self._note = QLabel("", self)
        self._note.setObjectName("shell.teamSync.feedNote")
        self._note.setWordWrap(True)
        self._note.setContentsMargins(12, 0, 12, 8)
        layout.addWidget(self._note)
        self._diff = QLabel("", self)
        self._diff.setObjectName("shell.teamSync.peekAdded")
        self._diff.setWordWrap(True)
        self._diff.hide()
        layout.addWidget(self._diff)
        actions = QHBoxLayout()
        actions.setContentsMargins(12, 8, 12, 10)
        actions.setSpacing(6)
        self._open = QPushButton("Open Change", self)
        self._open.setObjectName("shell.teamSync.hoverOpen")
        self._history = QPushButton("File History", self)
        self._history.setObjectName("shell.teamSync.hoverHistory")
        actions.addWidget(self._open)
        actions.addWidget(self._history)
        actions.addStretch(1)
        layout.addLayout(actions)
        self._on_open: Optional[Callable[[], None]] = None
        self._on_history: Optional[Callable[[], None]] = None
        self._open.clicked.connect(self._click_open)
        self._history.clicked.connect(self._click_history)
        self.setMinimumWidth(280)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 4)
        color = QColor(tokens.popup_shadow or "#000000")
        color.setAlpha(80)
        shadow.setColor(color)
        self.setGraphicsEffect(shadow)
        self.style().unpolish(self)
        self.style().polish(self)

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
        self._avatar.set_person(line.author_id, line.author_name, 28)
        self._title.setText(line.author_name)
        self._meta.setText(" · ".join(part for part in (shop, short_date(line.when)) if part))
        self._note.setText(line.note)
        if diff_text and diff_text != line.note:
            self._diff.setText(diff_text)
            self._diff.show()
        else:
            self._diff.hide()
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
        self.setStyleSheet(
            f"color: {tokens.text_muted}; background: transparent; font-size: 11px;"
        )

    def show_text(self, text: str, x: int, y: int) -> None:
        if not text:
            self.hide()
            return
        self.setText(text)
        self.adjustSize()
        self.move(x, y)
        self.show()


__all__ = ["BlameCard", "LineSummary"]
