"""Editor notice for an incoming edit or a clash on the open file."""

from __future__ import annotations

from typing import Callable, Optional

from app.qt.QtCore import Qt
from app.qt.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from app.features.team_sync.ui.widgets import Avatar
from app.shell.icon_provider import warning_icon
from app.shell.theme_tokens import ShellThemeTokens


def _polish(widget: QWidget) -> None:
    widget.setAttribute(Qt.WA_StyledBackground, True)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class TeamInfoBar(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.teamSync.infoBar")
        self.setFixedHeight(34)
        _polish(self)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(10)
        self._avatar = Avatar("", "", self, size=18)
        layout.addWidget(self._avatar)
        self._warning = QLabel(self)
        self._warning.setFixedSize(16, 16)
        self._warning.hide()
        layout.addWidget(self._warning)
        self._message = QLabel("", self)
        self._message.setObjectName("shell.teamSync.infoBarMessage")
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
        self._tokens: Optional[ShellThemeTokens] = None
        self.hide()

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._tokens = tokens
        self._warning.setPixmap(warning_icon(tokens.diag_warning_color or "#D97706").pixmap(16, 16))
        _polish(self)

    def show_incoming(
        self,
        member_id: str,
        name: str,
        message: str,
        on_review: Callable[[], None],
    ) -> None:
        self.setProperty("teamNotice", "incoming")
        self._avatar.set_person(member_id, name, 18)
        self._avatar.show()
        self._warning.hide()
        self._message.setText(message)
        self._review.show()
        self._cancel.hide()
        self._resolve.hide()
        self._review_cb = on_review
        _polish(self)
        self.show()

    def show_clash(
        self,
        message: str,
        on_cancel: Callable[[], None],
        on_resolve: Callable[[], None],
    ) -> None:
        self.setProperty("teamNotice", "clash")
        self._avatar.hide()
        self._warning.show()
        self._message.setText(message)
        self._review.hide()
        self._cancel.show()
        self._resolve.show()
        self._cancel_cb = on_cancel
        self._resolve_cb = on_resolve
        _polish(self)
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
