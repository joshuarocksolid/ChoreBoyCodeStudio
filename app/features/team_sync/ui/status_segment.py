"""Status-bar Team segment, its popover, and the experiment segment."""

from __future__ import annotations

from typing import Callable, Optional

from app.qt.QtCore import Qt
from app.qt.QtGui import QColor
from app.qt.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.features.team_sync.api import (
    TERMINAL_NONE,
    TERMINAL_OFFLINE,
    TERMINAL_OK,
    Change,
    TeamStatus,
)
from app.features.team_sync.ui.copy import StatusView, delivery_mark, first_name
from app.features.team_sync.ui.widgets import Avatar
from app.shell.icon_provider import history_icon
from app.shell.theme_tokens import ShellThemeTokens


def _polish(widget: QWidget) -> None:
    widget.setAttribute(Qt.WA_StyledBackground, True)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def _dot(parent: QWidget, name: str) -> QWidget:
    dot = QWidget(parent)
    dot.setObjectName(name)
    dot.setFixedSize(7, 7)
    _polish(dot)
    return dot


class TeamStatusSegment(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.teamSync.statusSegment")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(19)
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 0, 6, 0)
        row.setSpacing(6)
        self._dot = _dot(self, "shell.teamSync.statusDot")
        self._dot.setObjectName("shell.teamSync.statusDot")
        self._label = QLabel("Team: Up to date", self)
        self._label.setObjectName("shell.teamSync.statusLabel")
        row.addWidget(self._dot)
        row.addWidget(self._label)
        self._view = StatusView("Team: Up to date", "ok", False)
        self.setCursor(Qt.PointingHandCursor)

    def apply(self, view: StatusView, tokens: Optional[ShellThemeTokens]) -> None:
        del tokens
        self._view = view
        self._label.setText(view.text)
        self.setVisible(view.visible)
        self._dot.setProperty("level", view.level)
        _polish(self._dot)
        _polish(self)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        self.clicked()
        super().mousePressEvent(event)

    def clicked(self) -> None:
        return None


class ExperimentSegment(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.teamSync.experimentSegment")
        self.setAttribute(Qt.WA_StyledBackground, True)
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 0, 6, 0)
        self._label = QLabel("", self)
        self._label.setObjectName("shell.teamSync.experimentLabel")
        row.addWidget(self._label)
        self.setCursor(Qt.PointingHandCursor)
        self.hide()

    def apply(self, status: TeamStatus, tokens: Optional[ShellThemeTokens]) -> None:
        del tokens
        show = bool(status.experiments)
        self.setVisible(show and status.shared)
        name = status.line
        if name.startswith("exp/"):
            name = name[4:]
        self._label.setText(name)
        _polish(self)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        self.clicked()
        super().mousePressEvent(event)

    def clicked(self) -> None:
        return None


class StatusPopover(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.teamSync.statusPopover")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setWindowFlags(Qt.Popup)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        header = QHBoxLayout()
        header.setSpacing(8)
        self._stack = QHBoxLayout()
        self._stack.setSpacing(-6)
        header.addLayout(self._stack)
        self._title = QLabel("", self)
        self._title.setObjectName("shell.teamSync.popoverTitle")
        header.addWidget(self._title, 1)
        layout.addLayout(header)
        self._rows = QVBoxLayout()
        self._rows.setSpacing(0)
        layout.addLayout(self._rows)
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 6, 0, 0)
        footer.setSpacing(8)
        self._history = QPushButton("History", self)
        self._history.setObjectName("shell.teamSync.statusHistory")
        self._history.setCursor(Qt.PointingHandCursor)
        footer.addWidget(self._history)
        footer.addStretch(1)
        self._terminal_dot = _dot(self, "shell.teamSync.terminalDot")
        self._terminal = QLabel("", self)
        self._terminal.setObjectName("shell.teamSync.terminalText")
        footer.addWidget(self._terminal_dot)
        footer.addWidget(self._terminal)
        self._more = QToolButtonMenu(self)
        footer.addWidget(self._more)
        layout.addLayout(footer)
        self.setMinimumWidth(280)
        self._on_review: Optional[Callable[[str], None]] = None
        self._on_history: Optional[Callable[[], None]] = None
        self._history.clicked.connect(self._history_clicked)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._history.setIcon(history_icon(tokens.text_primary))
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 4)
        color = QColor(tokens.popup_shadow or "#000000")
        color.setAlpha(80)
        shadow.setColor(color)
        self.setGraphicsEffect(shadow)
        _polish(self)

    def present(
        self,
        anchor: QWidget,
        status: TeamStatus,
        last_change: Optional[Change],
        waiting: list[tuple[str, str]],
        *,
        git_names: bool,
        on_history: Callable[[], None],
        on_members: Callable[[], None],
        on_save_usb: Callable[[], None],
        on_open_usb: Callable[[], None],
        on_review: Callable[[str], None],
    ) -> None:
        self._on_review = on_review
        self._fill_stack(status)
        self._title.setText(status.project_name or "Project")
        self._clear(self._rows)
        if status.last_delivery is not None and last_change is not None:
            mark, tip = delivery_mark(status.last_delivery.state, git_names=git_names)
            self._rows.addWidget(self._change_row(last_change, mark, tip))
        for incoming_id, label in waiting:
            self._rows.addWidget(self._review_row(incoming_id, label))
        if status.unverified:
            note = QLabel(f"{status.unverified} message couldn't be verified", self)
            note.setObjectName("shell.teamSync.popoverMuted")
            self._rows.addWidget(note)
        health, level = _terminal_health(status.terminal)
        self._terminal.setText(health)
        self._terminal_dot.setProperty("level", level)
        _polish(self._terminal_dot)
        self._on_history = on_history
        self._more.set_actions(
            [
                ("Members", on_members),
                ("Save to USB", on_save_usb),
                ("Open from USB", on_open_usb),
            ]
        )
        self.adjustSize()
        origin = anchor.mapToGlobal(anchor.rect().topLeft())
        self.move(origin.x(), origin.y() - self.sizeHint().height() - 4)
        self.show()

    def _fill_stack(self, status: TeamStatus) -> None:
        while self._stack.count():
            item = self._stack.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        for member in status.members:
            avatar = Avatar(member.id, member.name, self, size=18)
            avatar.setToolTip(f"{member.name} · {member.shop}")
            self._stack.addWidget(avatar)

    def _change_row(self, change: Change, mark: str, tip: str) -> QWidget:
        row = QWidget(self)
        row.setObjectName("shell.teamSync.popoverRow")
        row.setFixedHeight(28)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(Avatar(change.author_id, change.author_name, row, size=18))
        note = QLabel(change.note, row)
        note.setObjectName("shell.teamSync.feedNote")
        layout.addWidget(note, 1)
        badge = QLabel(mark, row)
        badge.setObjectName("shell.teamSync.feedMark")
        badge.setToolTip(tip)
        state = "delivered" if "✓✓" in mark else "sent" if mark == "✓" else "queued"
        badge.setProperty("delivery", state)
        _polish(badge)
        layout.addWidget(badge)
        return row

    def _review_row(self, incoming_id: str, label: str) -> QWidget:
        row = QWidget(self)
        row.setObjectName("shell.teamSync.popoverRow")
        row.setFixedHeight(28)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        note = QLabel(label, row)
        note.setObjectName("shell.teamSync.feedNote")
        layout.addWidget(note, 1)
        button = QPushButton("Review", row)
        button.setObjectName("shell.teamSync.feedReview")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(lambda _checked=False, ident=incoming_id: self._review(ident))
        layout.addWidget(button)
        return row

    def _history_clicked(self) -> None:
        self.hide()
        if self._on_history is not None:
            self._on_history()

    def _review(self, incoming_id: str) -> None:
        self.hide()
        if self._on_review is not None:
            self._on_review(incoming_id)

    def _clear(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()


class QToolButtonMenu(QPushButton):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("⋯", parent)
        self.setObjectName("shell.teamSync.statusMenu")
        self.setFixedSize(22, 22)
        self.setCursor(Qt.PointingHandCursor)
        self._menu = QMenu(self)
        self.clicked.connect(self._open)

    def _open(self) -> None:
        self._menu.popup(self.mapToGlobal(self.rect().bottomLeft()))

    def set_actions(self, actions: list[tuple[str, Callable[[], None]]]) -> None:
        self._menu.clear()
        for label, callback in actions:
            self._menu.addAction(label, callback)


def _terminal_health(terminal: str) -> tuple[str, str]:
    if terminal == TERMINAL_OK:
        return ("FaxMail terminal working", "ok")
    if terminal == TERMINAL_OFFLINE:
        return ("FaxMail terminal not responding", "warn")
    if terminal == TERMINAL_NONE:
        return ("No FaxMail mailbox", "warn")
    return (terminal, "info")


def other_shop(status: TeamStatus) -> str:
    if status.me is None:
        return ""
    for member in status.members:
        if member.id != status.me.id:
            return member.shop
    return ""


def waiting_rows(incoming: list) -> list[tuple[str, str]]:  # type: ignore[type-arg]
    rows = []
    for item in incoming:
        note = item.changes[0].note if item.changes else "Change"
        author = first_name(item.changes[0].author_name) if item.changes else "Someone"
        rows.append((item.id, f"{author}: {note}"))
    return rows


__all__ = [
    "ExperimentSegment",
    "StatusPopover",
    "TeamStatusSegment",
    "other_shop",
    "waiting_rows",
]
