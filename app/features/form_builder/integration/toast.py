"""One form toast. It confirms a command the user might want back.

The note records the undo label and the log depth that announced it. Undo
runs only while that command is still the top of the log.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from app.qt.QtCore import QEvent, Qt, QTimer
from app.qt.QtGui import QColor
from app.qt.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from app.shell.theme_tokens import ShellThemeTokens

_WITH_ACTION_MS = 8000
_PLAIN_MS = 6000


@dataclass(frozen=True)
class ToastNote:
    """What the toast is offering to undo."""

    text: str
    action: Optional[str]
    command: str
    depth: int


def notice_for(label: str) -> Optional[str]:
    """The command label when it is one the toast should confirm."""
    folded = " ".join(label.strip().lower().split())
    if not folded:
        return None
    if "unwrap" in folded:
        return label.strip()
    if "remove layout" in folded or "break layout" in folded:
        return label.strip()
    if "change layout" in folded or "change widget" in folded or "morph" in folded:
        return label.strip()
    if "delete" in folded or folded == "cut" or folded.startswith("cut "):
        return label.strip()
    if "wrap" in folded:
        return label.strip()
    return None


def toast_duration_ms(has_action: bool) -> int:
    return _WITH_ACTION_MS if has_action else _PLAIN_MS


def undo_matches(note: ToastNote, label: Optional[str], depth: int) -> bool:
    return label == note.command and depth == note.depth


class CommandToast(QFrame):
    """Level-2 notice at the bottom centre of the form surface. It does not take focus."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.commandToast")
        self.setAccessibleName("Notice")
        self.setFocusPolicy(_no_focus())
        self.setMaximumWidth(480)
        self.setAttribute(_attr("WA_ShowWithoutActivating"), True)
        self._note: Optional[ToastNote] = None
        self._on_action: Optional[Callable[[ToastNote], None]] = None
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 8, 8)
        row.setSpacing(8)
        self._text = QLabel(self)
        self._text.setObjectName("formBuilder.toastText")
        self._text.setWordWrap(True)
        self._text.setFocusPolicy(_no_focus())
        row.addWidget(self._text, 1)
        self._action = QPushButton(self)
        self._action.setObjectName("formBuilder.toastUndo")
        self._action.setFocusPolicy(_no_focus())
        self._action.clicked.connect(self._activate)
        self._action.hide()
        row.addWidget(self._action, 0)
        close = QPushButton("\u00d7", self)
        close.setObjectName("formBuilder.toastClose")
        close.setAccessibleName("Close")
        close.setFocusPolicy(_no_focus())
        close.clicked.connect(self.dismiss)
        row.addWidget(close, 0)
        self._timer = QTimer(self)
        self._timer.setObjectName("formBuilder.toastTimer")
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self.hide()

    def show_note(self, note: ToastNote, on_action: Callable[[ToastNote], None]) -> None:
        self._note = note
        self._on_action = on_action
        self._text.setText(note.text)
        self._text.setAccessibleName(note.text)
        if note.action:
            self._action.setText(note.action)
            self._action.setAccessibleName(note.action)
            self._action.show()
        else:
            self._action.hide()
        self._arm()
        self.show()
        self.raise_()
        self.place()

    def dismiss(self) -> None:
        self._timer.stop()
        self._note = None
        self._on_action = None
        self.hide()

    def place(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        width = min(480, max(self.sizeHint().width(), 160), max(1, parent.width() - 16))
        height = max(self.sizeHint().height(), 32)
        self.resize(width, height)
        self.move(max(0, (parent.width() - width) // 2), max(0, parent.height() - height - 16))

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        fill = tokens.popup_bg or tokens.panel_bg
        border = tokens.popup_border or tokens.border
        width = tokens.focus_border_width or 1
        self.setStyleSheet(
            "QFrame#formBuilder\\.commandToast { background: %s; color: %s;"
            " border: %dpx solid %s; border-radius: 6px; }"
            "QLabel { background: transparent; color: %s; border: none; }"
            "QPushButton { background: transparent; color: %s; border: none; padding: 2px 6px; }"
            % (fill, tokens.text_primary, width, border, tokens.text_primary, tokens.text_primary)
        )
        if tokens.is_high_contrast:
            self.setGraphicsEffect(None)
            return
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 41))
        self.setGraphicsEffect(shadow)

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802
        self._timer.stop()
        super().enterEvent(event)  # type: ignore[arg-type]

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        if self.isVisible():
            self._arm()
        super().leaveEvent(event)  # type: ignore[arg-type]

    def _activate(self) -> None:
        note = self._note
        action = self._on_action
        if note is None or action is None:
            return
        action(note)

    def _arm(self) -> None:
        self._timer.start(toast_duration_ms(not self._action.isHidden()))


def _no_focus() -> Qt.FocusPolicy:
    return getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus")


def _attr(name: str) -> Qt.WidgetAttribute:
    return getattr(getattr(Qt, "WidgetAttribute", Qt), name)
