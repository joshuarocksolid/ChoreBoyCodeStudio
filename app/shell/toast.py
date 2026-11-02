"""Themed toast anchored to the bottom-right of a parent widget."""

from __future__ import annotations

from typing import Callable, Optional

import time

from app.qt.QtCore import QEvent, QObject, Qt, QTimer
from app.qt.QtGui import QColor
from app.qt.QtWidgets import QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton, QWidget

from app.shell.theme_tokens import ShellThemeTokens


class Toast(QFrame):
    """One quiet notice with an optional action. It dismisses itself."""

    def __init__(
        self,
        parent: QWidget,
        message: str,
        *,
        action_label: str = "",
        on_action: Optional[Callable[[], None]] = None,
        tokens: Optional[ShellThemeTokens] = None,
        object_name: str = "shell.toast",
        timeout_ms: int = 8000,
        word_wrap: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("shell.toast")
        if object_name != "shell.toast":
            self.setObjectName(object_name)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._tokens = tokens
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 8, 8)
        layout.setSpacing(10)
        self._message = QLabel(message, self)
        self._message.setObjectName("shell.toast.message")
        self._message.setWordWrap(word_wrap)
        layout.addWidget(self._message, 1)
        self._action: Optional[QPushButton] = None
        if action_label:
            button = QPushButton(action_label, self)
            button.setObjectName("shell.toast.action")
            button.setAutoDefault(False)
            if on_action is not None:
                button.clicked.connect(on_action)
            button.clicked.connect(self.dismiss)
            layout.addWidget(button)
            self._action = button
        self._apply()
        self.adjustSize()
        self.setMinimumWidth(280)
        self.setMaximumWidth(420)
        parent.installEventFilter(_ResizeFilter(parent, self))
        self._place()
        self.show()
        self.raise_()
        self._deadline = 0.0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self._arm(timeout_ms)

    def dismiss(self) -> None:
        self.hide()
        self.deleteLater()

    def _place(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        margin = 16
        self.move(
            max(margin, parent.width() - self.width() - margin),
            max(margin, parent.height() - self.height() - margin),
        )

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt signature
        self._timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt signature
        left = int((self._deadline - time.monotonic()) * 1000)
        if left <= 0:
            self.dismiss()
        else:
            self._timer.start(left)
        super().leaveEvent(event)

    def _arm(self, timeout_ms: int) -> None:
        self._deadline = time.monotonic() + (timeout_ms / 1000.0)
        self._timer.start(timeout_ms)

    def _apply(self) -> None:
        tokens = self._tokens
        if tokens is None:
            return
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 4)
        color = QColor(tokens.popup_shadow or "#000000")
        color.setAlpha(90)
        shadow.setColor(color)
        self.setGraphicsEffect(shadow)


class _ResizeFilter(QObject):
    def __init__(self, parent: QWidget, toast: Toast) -> None:
        super().__init__(parent)
        self._toast = toast

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Resize:
            toast = self._toast
            if toast is not None and not toast.isHidden():
                toast._place()
        return False


def show_toast(
    anchor: QWidget,
    message: str,
    *,
    action_label: str = "",
    on_action: Optional[Callable[[], None]] = None,
    tokens: Optional[ShellThemeTokens] = None,
    object_name: str = "shell.toast",
    timeout_ms: int = 8000,
    word_wrap: bool = True,
) -> Toast:
    """Show one toast inside ``anchor`` (the editor area, not the whole window)."""
    toast = Toast(
        anchor,
        message,
        action_label=action_label,
        on_action=on_action,
        tokens=tokens,
        object_name=object_name,
        timeout_ms=timeout_ms,
        word_wrap=word_wrap,
    )
    return toast


__all__ = ["Toast", "show_toast"]
