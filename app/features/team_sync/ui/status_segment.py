"""Status-bar Team segment, its popover, and the experiment segment."""

from __future__ import annotations

from typing import Callable, Optional

from app.qt.QtCore import Qt
from app.qt.QtWidgets import (
    QFrame,
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
from app.features.team_sync.ui.copy import StatusView, delivery_mark, first_name, status_view
from app.features.team_sync.ui.theme import button_qss, level_color, muted_qss, surface_qss
from app.features.team_sync.ui.widgets import Avatar
from app.qt.qt_compat import exec_qt
from app.shell.theme_tokens import ShellThemeTokens


class TeamStatusSegment(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.teamSync.statusSegment")
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 0, 8, 0)
        row.setSpacing(6)
        self._dot = QLabel("●", self)
        self._dot.setObjectName("shell.teamSync.statusDot")
        self._label = QLabel("Team: Up to date", self)
        self._label.setObjectName("shell.teamSync.statusLabel")
        row.addWidget(self._dot)
        row.addWidget(self._label)
        self._view = StatusView("Team: Up to date", "ok", False)
        self._locked = False
        self.setCursor(Qt.PointingHandCursor)

    def apply(self, view: StatusView, tokens: Optional[ShellThemeTokens]) -> None:
        self._view = view
        self._label.setText(view.text)
        self.setVisible(view.visible)
        if not self._locked:
            width = self.fontMetrics().horizontalAdvance("Team: Terminal offline") + 36
            self.setFixedWidth(width)
            self._locked = True
        if tokens is not None:
            self._dot.setStyleSheet(f"color: {level_color(tokens, view.level)}; background: transparent;")
            self._label.setStyleSheet(f"color: {tokens.text_primary}; background: transparent;")

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        self.clicked()
        super().mousePressEvent(event)

    def clicked(self) -> None:
        return None


class ExperimentSegment(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.teamSync.experimentSegment")
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 0, 8, 0)
        self._label = QLabel("", self)
        row.addWidget(self._label)
        self.setCursor(Qt.PointingHandCursor)
        self.hide()

    def apply(self, status: TeamStatus, tokens: Optional[ShellThemeTokens]) -> None:
        show = bool(status.experiments)
        self.setVisible(show and status.shared)
        name = status.line
        if name.startswith("exp/"):
            name = name[4:]
        self._label.setText(name)
        if tokens is not None:
            self._label.setStyleSheet(f"color: {tokens.text_primary}; background: transparent;")

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        self.clicked()
        super().mousePressEvent(event)

    def clicked(self) -> None:
        return None


class StatusPopover(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.teamSync.statusPopover")
        self.setWindowFlags(Qt.Popup)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        self._members = QVBoxLayout()
        layout.addLayout(self._members)
        self._delivery = QLabel("", self)
        self._delivery.setWordWrap(True)
        layout.addWidget(self._delivery)
        self._waiting = QVBoxLayout()
        layout.addLayout(self._waiting)
        self._terminal = QLabel("", self)
        layout.addWidget(self._terminal)
        self._unverified = QLabel("", self)
        layout.addWidget(self._unverified)
        actions = QHBoxLayout()
        self._history = QPushButton("History", self)
        self._history.setObjectName("shell.teamSync.statusHistory")
        self._more = QToolButtonMenu(self)
        actions.addWidget(self._history)
        actions.addWidget(self._more)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.setMinimumWidth(280)
        self._on_review: Optional[Callable[[str], None]] = None
        self._on_history: Optional[Callable[[], None]] = None
        self._history.clicked.connect(self._history_clicked)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self.setStyleSheet(
            surface_qss(tokens)
            + "QFrame#shell\\.teamSync\\.statusPopover {"
            f" border: 1px solid {tokens.border}; border-radius: 8px; }}"
        )
        self._history.setStyleSheet(button_qss(tokens))
        self._terminal.setStyleSheet(muted_qss(tokens))

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
        self._clear(self._members)
        for member in status.members:
            row = QWidget(self)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(Avatar(member.id, member.name, row))
            row_layout.addWidget(QLabel(f"{member.name} · {member.shop}", row), 1)
            self._members.addWidget(row)
        if status.last_delivery is not None and last_change is not None:
            mark, tip = delivery_mark(status.last_delivery.state, git_names=git_names)
            self._delivery.setText(f"{last_change.note}  {mark}")
            self._delivery.setToolTip(tip)
            self._delivery.show()
        else:
            self._delivery.hide()
        self._clear(self._waiting)
        for incoming_id, label in waiting:
            button = QPushButton(f"{label}  Review", self)
            button.clicked.connect(lambda _checked=False, ident=incoming_id: self._review(ident))
            self._waiting.addWidget(button)
        terminal = {
            TERMINAL_OK: "Terminal healthy",
            TERMINAL_OFFLINE: "Terminal offline",
            TERMINAL_NONE: "No FaxMail mailbox found",
        }.get(status.terminal, status.terminal)
        self._terminal.setText(terminal)
        if status.unverified:
            self._unverified.setText(f"{status.unverified} message couldn't be verified")
            self._unverified.show()
        else:
            self._unverified.hide()
        self._on_history = on_history
        self._more.set_actions(
            [
                ("Members", on_members),
                ("Save to USB", on_save_usb),
                ("Open from USB", on_open_usb),
            ]
        )
        self.adjustSize()
        self.move(anchor.mapToGlobal(anchor.rect().topLeft()).x(), anchor.mapToGlobal(anchor.rect().topLeft()).y() - self.sizeHint().height())
        self.show()

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
                widget.deleteLater()


class QToolButtonMenu(QPushButton):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("⋯", parent)
        self.setObjectName("shell.teamSync.statusMenu")
        self._menu = QMenu(self)
        self.clicked.connect(lambda: exec_qt(self._menu))

    def set_actions(self, actions: list[tuple[str, Callable[[], None]]]) -> None:
        self._menu.clear()
        for label, callback in actions:
            self._menu.addAction(label, callback)


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
