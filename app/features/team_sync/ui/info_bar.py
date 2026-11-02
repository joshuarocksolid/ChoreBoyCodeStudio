"""Editor notice for an incoming edit or a clash on the open file."""

from __future__ import annotations

from typing import Callable, Optional

from app.qt.QtCore import Qt
from app.qt.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from app.features.team_sync.ui.theme import button_qss, primary_button_qss
from app.features.team_sync.ui.widgets import Avatar
from app.shell.theme_tokens import ShellThemeTokens


class TeamInfoBar(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.teamSync.infoBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)
        self._avatar = Avatar("", "", self, size=18)
        layout.addWidget(self._avatar)
        self._message = QLabel("", self)
        self._message.setObjectName("shell.teamSync.infoBarMessage")
        self._message.setWordWrap(True)
        layout.addWidget(self._message, 1)
        self._review = QPushButton("Review", self)
        self._review.setObjectName("shell.teamSync.infoBarReview")
        self._cancel = QPushButton("Cancel Combine", self)
        self._cancel.setObjectName("shell.teamSync.infoBarCancel")
        self._resolve = QPushButton("Resolve", self)
        self._resolve.setObjectName("shell.teamSync.infoBarResolve")
        layout.addWidget(self._review)
        layout.addWidget(self._cancel)
        layout.addWidget(self._resolve)
        self._review_cb: Optional[Callable[[], None]] = None
        self._cancel_cb: Optional[Callable[[], None]] = None
        self._resolve_cb: Optional[Callable[[], None]] = None
        self._review.clicked.connect(self._click_review)
        self._cancel.clicked.connect(self._click_cancel)
        self._resolve.clicked.connect(self._click_resolve)
        self.hide()

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self.setStyleSheet(
            f"QFrame#shell\\.teamSync\\.infoBar {{ background: {tokens.panel_bg};"
            f" border-bottom: 1px solid {tokens.border}; border-left: 3px solid {tokens.accent}; }}"
            f"QLabel {{ color: {tokens.text_primary}; background: transparent; }}"
        )
        self._review.setStyleSheet(primary_button_qss(tokens))
        self._cancel.setStyleSheet(button_qss(tokens))
        self._resolve.setStyleSheet(primary_button_qss(tokens))

    def show_incoming(
        self,
        member_id: str,
        name: str,
        message: str,
        on_review: Callable[[], None],
    ) -> None:
        self._avatar.set_person(member_id, name, 18)
        self._avatar.show()
        self._message.setText(message)
        self._review.show()
        self._cancel.hide()
        self._resolve.hide()
        self._review_cb = on_review
        self.show()

    def show_clash(
        self,
        message: str,
        on_cancel: Callable[[], None],
        on_resolve: Callable[[], None],
    ) -> None:
        self._avatar.hide()
        self._message.setText(message)
        self._review.hide()
        self._cancel.show()
        self._resolve.show()
        self._cancel_cb = on_cancel
        self._resolve_cb = on_resolve
        self.show()

    def clear(self) -> None:
        self.hide()

    def _click_review(self) -> None:
        if self._review_cb is not None:
            self._review_cb()

    def _click_cancel(self) -> None:
        if self._cancel_cb is not None:
            self._cancel_cb()

    def _click_resolve(self) -> None:
        if self._resolve_cb is not None:
            self._resolve_cb()


__all__ = ["TeamInfoBar"]
