"""Peek under a gutter change mark: the old line, the new line, and Undo Edit."""

from __future__ import annotations

from typing import Callable, Optional

from app.qt.QtCore import Qt
from app.qt.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.shell.theme_tokens import ShellThemeTokens


class GutterPeek(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.teamSync.gutterPeek")
        self.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(8, 4, 6, 4)
        head.addStretch(1)
        self._undo = QPushButton("Undo Edit", self)
        self._undo.setObjectName("shell.teamSync.gutterUndo")
        head.addWidget(self._undo)
        layout.addLayout(head)
        self._old = QLabel("", self)
        self._old.setObjectName("shell.teamSync.peekRemoved")
        self._new = QLabel("", self)
        self._new.setObjectName("shell.teamSync.peekAdded")
        layout.addWidget(self._old)
        layout.addWidget(self._new)
        self._on_undo: Optional[Callable[[], None]] = None
        self._undo.clicked.connect(self._click_undo)
        self.hide()

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        del tokens
        self.style().unpolish(self)
        self.style().polish(self)

    def show_change(
        self,
        old_line: str,
        new_line: str,
        x: int,
        y: int,
        on_undo: Callable[[], None],
    ) -> None:
        self._old.setText(old_line)
        self._new.setText(new_line)
        self._on_undo = on_undo
        self.adjustSize()
        self.move(x, y)
        self.show()
        self.raise_()

    def _click_undo(self) -> None:
        if self._on_undo is not None:
            self._on_undo()


__all__ = ["GutterPeek"]
