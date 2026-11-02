"""Themed toast anchored to the bottom-right of a parent widget."""

from __future__ import annotations

from typing import Callable, Optional

from app.qt.QtCore import QEvent, QObject, Qt, QTimer
from app.qt.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

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
    ) -> None:
        super().__init__(parent)
        self.setObjectName("shell.toast")
        if object_name != "shell.toast":
            self.setObjectName(object_name)
        self._tokens = tokens
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 8, 8)
        layout.setSpacing(10)
        self._message = QLabel(message, self)
        self._message.setObjectName("shell.toast.message")
        self._message.setWordWrap(True)
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
        QTimer.singleShot(timeout_ms, self.dismiss)

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

    def _apply(self) -> None:
        tokens = self._tokens
        if tokens is None:
            return
        focus = tokens.focus_border_width
        self.setStyleSheet(
            f"QFrame#shell\\.toast {{ background: {tokens.popup_bg or tokens.panel_bg};"
            f" color: {tokens.text_primary}; border: 1px solid {tokens.popup_border or tokens.border};"
            f" border-radius: 8px; }}"
            f"QFrame#shell\\.toast QLabel {{ color: {tokens.text_primary}; background: transparent; }}"
            f"QFrame#shell\\.toast QPushButton {{ background: {tokens.accent}; color: {tokens.toolbar_package_fg or '#FFFFFF'};"
            f" border: none; border-radius: 4px; padding: 4px 10px; font-weight: 600; }}"
            f"QFrame#shell\\.toast QPushButton:focus {{ border: {focus}px solid {tokens.text_primary}; }}"
        )


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
) -> Toast:
    """Show one toast inside ``anchor`` (the editor area, not the whole window)."""
    toast = Toast(
        anchor,
        message,
        action_label=action_label,
        on_action=on_action,
        tokens=tokens,
        object_name=object_name,
    )
    return toast


__all__ = ["Toast", "show_toast"]
