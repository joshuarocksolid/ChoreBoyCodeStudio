"""Peek under a gutter change mark: the old line, the new line, and Undo Edit."""

from __future__ import annotations

from typing import Callable, Optional

from app.qt.QtCore import Qt
from app.qt.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.features.team_sync.ui.theme import button_qss, surface_qss
from app.shell.theme_tokens import ShellThemeTokens


class GutterPeek(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.teamSync.gutterPeek")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        self._old = QLabel("", self)
        self._new = QLabel("", self)
        layout.addWidget(self._old)
        layout.addWidget(self._new)
        row = QHBoxLayout()
        row.addStretch(1)
        self._undo = QPushButton("Undo Edit", self)
        self._undo.setObjectName("shell.teamSync.gutterUndo")
        row.addWidget(self._undo)
        layout.addLayout(row)
        self._on_undo: Optional[Callable[[], None]] = None
        self._undo.clicked.connect(self._click_undo)
        self.hide()

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self.setStyleSheet(
            surface_qss(tokens)
            + "QFrame#shell\\.teamSync\\.gutterPeek {"
            f" border: 1px solid {tokens.border}; border-radius: 6px; }}"
            f"QLabel {{ color: {tokens.text_primary}; background: transparent; }}"
        )
        self._undo.setStyleSheet(button_qss(tokens))

    def show_change(
        self,
        old_line: str,
        new_line: str,
        x: int,
        y: int,
        on_undo: Callable[[], None],
    ) -> None:
        self._old.setText(f"- {old_line}")
        self._new.setText(f"+ {new_line}")
        self._on_undo = on_undo
        self.adjustSize()
        self.move(x, y)
        self.show()
        self.raise_()

    def _click_undo(self) -> None:
        if self._on_undo is not None:
            self._on_undo()


__all__ = ["GutterPeek"]
