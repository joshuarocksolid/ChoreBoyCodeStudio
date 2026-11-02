"""Thread view: the Team activity-bar page."""

from __future__ import annotations

from typing import Callable, Optional

from app.qt.QtCore import QSize, Qt
from app.qt.QtGui import QFont
from app.qt.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.features.team_sync.api import (
    DELIVERY_ACCEPTED,
    DELIVERY_DELIVERED,
    DELIVERY_QUEUED,
    DELIVERY_SENT,
    DELIVERY_WAITING_TERMINAL,
    FEED_INCOMING,
    FEED_SYSTEM,
    FeedItem,
    TeamStatus,
)
from app.features.team_sync.ui.copy import clock, delivery_mark, first_name
from app.shell.icon_provider import send_icon
from app.features.team_sync.ui.widgets import Avatar
from app.shell.theme_tokens import ShellThemeTokens


def _polish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def _delivery_key(state: str) -> str:
    if state in (DELIVERY_QUEUED, DELIVERY_WAITING_TERMINAL):
        return "queued"
    if state == DELIVERY_SENT:
        return "sent"
    if state in (DELIVERY_DELIVERED, DELIVERY_ACCEPTED):
        return "delivered"
    return "queued"


class TeamView(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.teamSync.teamView")
        self._tokens: Optional[ShellThemeTokens] = None
        self._on_share: Optional[Callable[[], None]] = None
        self._on_send: Optional[Callable[[str, list[str]], None]] = None
        self._on_save_only: Optional[Callable[[str, list[str]], None]] = None
        self._on_set_aside: Optional[Callable[[str], None]] = None
        self._on_bring_back: Optional[Callable[[int], None]] = None
        self._on_review: Optional[Callable[[str], None]] = None
        self._on_open_change: Optional[Callable[[str], None]] = None
        self._git_names = False
        self._checks: list[tuple[QCheckBox, str]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget(self)
        header.setObjectName("shell.teamSync.teamHeader")
        header.setFixedHeight(30)
        header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(10, 0, 8, 0)
        header_row.setSpacing(6)
        title = QLabel("TEAM", header)
        title.setObjectName("shell.leftRegion.title")
        header_row.addWidget(title)
        header_row.addStretch(1)
        self._avatars = QHBoxLayout()
        self._avatars.setSpacing(-6)
        self._avatars.setAlignment(Qt.AlignVCenter)
        header_row.addLayout(self._avatars)
        root.addWidget(header)

        self._empty = QWidget(self)
        self._empty.setObjectName("shell.teamSync.empty")
        empty_layout = QVBoxLayout(self._empty)
        empty_layout.addStretch(1)
        empty_label = QLabel("Not shared", self._empty)
        empty_label.setAlignment(Qt.AlignCenter)
        empty_label.setObjectName("shell.teamSync.emptyLabel")
        empty_layout.addWidget(empty_label)
        self._share_button = QPushButton("Share Project…", self._empty)
        self._share_button.setObjectName("shell.teamSync.shareButton")
        self._share_button.clicked.connect(self._share)
        empty_layout.addWidget(self._share_button, 0, Qt.AlignHCenter)
        empty_layout.addStretch(1)
        root.addWidget(self._empty, 1)

        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("shell.teamSync.feed")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.viewport().setObjectName("shell.teamSync.feedViewport")
        self._scroll.viewport().setAttribute(Qt.WA_StyledBackground, True)
        self._feed_host = QWidget(self._scroll)
        self._feed_host.setAttribute(Qt.WA_StyledBackground, True)
        self._feed_host.setObjectName("shell.teamSync.feedHost")
        self._feed_layout = QVBoxLayout(self._feed_host)
        self._feed_layout.setContentsMargins(10, 6, 10, 12)
        self._feed_layout.setSpacing(14)
        self._feed_layout.addStretch(1)
        self._scroll.setWidget(self._feed_host)
        root.addWidget(self._scroll, 1)

        self._set_aside_row = QWidget(self)
        self._set_aside_row.setObjectName("shell.teamSync.setAside")
        aside = QHBoxLayout(self._set_aside_row)
        aside.setContentsMargins(10, 6, 10, 6)
        self._set_aside_label = QLabel("", self._set_aside_row)
        aside.addWidget(self._set_aside_label, 1)
        self._bring_back = QPushButton("Bring Back", self._set_aside_row)
        self._bring_back.setObjectName("shell.teamSync.bringBack")
        self._bring_back.clicked.connect(self._bring_back_clicked)
        aside.addWidget(self._bring_back)
        self._set_aside_index = 0
        root.addWidget(self._set_aside_row)

        composer = QWidget(self)
        composer.setObjectName("shell.teamSync.composer")
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(10, 8, 10, 10)
        composer_layout.setSpacing(6)
        self._files_button = QToolButton(composer)
        self._files_button.setObjectName("shell.teamSync.composerFiles")
        self._files_button.setCheckable(True)
        self._files_button.setText("0 files")
        self._files_button.toggled.connect(self._toggle_files)
        self._files_button.hide()
        composer_layout.addWidget(self._files_button, 0, Qt.AlignLeft)
        self._file_list = QWidget(composer)
        self._file_list.setObjectName("shell.teamSync.composerChecklist")
        self._file_layout = QVBoxLayout(self._file_list)
        self._file_layout.setContentsMargins(0, 0, 0, 0)
        self._file_layout.setSpacing(2)
        self._file_list.hide()
        composer_layout.addWidget(self._file_list)
        send_row = QHBoxLayout()
        send_row.setSpacing(6)
        self._note = QLineEdit(composer)
        self._note.setObjectName("shell.teamSync.composerNote")
        self._note.setPlaceholderText("Message")
        self._note.setFixedHeight(28)
        send_row.addWidget(self._note, 1)
        self._send = QToolButton(composer)
        self._send.setObjectName("shell.teamSync.composerSend")
        self._send.setFixedSize(28, 28)
        self._send.setIconSize(QSize(14, 14))
        self._send.setToolTip("Send")
        self._send.setPopupMode(QToolButton.DelayedPopup)
        self._send.clicked.connect(self._send_clicked)
        menu = QMenu(self._send)
        menu.setObjectName("shell.teamSync.composerMenu")
        menu.addAction("Send", self._send_clicked)
        menu.addAction("Save Only", self._save_only_clicked)
        menu.addAction("Set Aside", self._set_aside_clicked)
        self._tidy_action = menu.addAction("Tidy, then Send", self._send_clicked)
        self._tidy_action.setVisible(False)
        self._send.setMenu(menu)
        send_row.addWidget(self._send)
        composer_layout.addLayout(send_row)
        root.addWidget(composer)
        self._composer = composer
        self._shared = False

    def bind(
        self,
        *,
        on_share: Callable[[], None],
        on_send: Callable[[str, list[str]], None],
        on_save_only: Callable[[str, list[str]], None],
        on_set_aside: Callable[[str], None],
        on_bring_back: Callable[[int], None],
        on_review: Callable[[str], None],
        on_open_change: Callable[[str], None],
    ) -> None:
        self._on_share = on_share
        self._on_send = on_send
        self._on_save_only = on_save_only
        self._on_set_aside = on_set_aside
        self._on_bring_back = on_bring_back
        self._on_review = on_review
        self._on_open_change = on_open_change

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._tokens = tokens
        color = tokens.toolbar_package_fg or "#FFFFFF"
        self._send.setIcon(send_icon(color))
        _polish(self)

    def apply(
        self,
        status: TeamStatus,
        feed: list[FeedItem],
        *,
        git_names: bool,
        dormant: bool,
        tidy: bool,
    ) -> None:
        self._git_names = git_names
        self._shared = status.shared
        self._tidy_action.setVisible(tidy)
        self._empty.setVisible(not status.shared)
        self._scroll.setVisible(status.shared)
        self._composer.setVisible(status.shared)
        self._share_button.setEnabled(status.shared is False and not dormant)
        self._fill_avatars(status)
        self._fill_feed(feed, status)
        self._fill_files(status)
        if status.set_aside:
            item = status.set_aside[0]
            self._set_aside_index = item.index
            self._set_aside_label.setText(item.name)
            self._set_aside_row.show()
        else:
            self._set_aside_row.hide()

    def _fill_avatars(self, status: TeamStatus) -> None:
        while self._avatars.count():
            item = self._avatars.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        for member in status.members:
            avatar = Avatar(member.id, member.name, self, size=18)
            avatar.setToolTip(f"{member.name} · {member.shop}")
            self._avatars.addWidget(avatar)

    def _fill_feed(self, feed: list[FeedItem], status: TeamStatus) -> None:
        while self._feed_layout.count() > 1:
            item = self._feed_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        me = status.me.id if status.me is not None else ""
        for entry in feed:
            self._feed_layout.insertWidget(self._feed_layout.count() - 1, self._feed_row(entry, me))

    def _feed_row(self, entry: FeedItem, me_id: str) -> QWidget:
        if entry.kind == FEED_SYSTEM:
            label = QLabel(f"{entry.text} · {clock(entry.when)}", self._feed_host)
            label.setObjectName("shell.teamSync.feedSystem")
            label.setAlignment(Qt.AlignCenter)
            return label
        incoming = entry.kind == FEED_INCOMING and entry.incoming is not None
        row = QWidget(self._feed_host)
        row.setObjectName("shell.teamSync.feedMessage")
        row.setProperty("incoming", True if incoming else False)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 8, 8, 8) if incoming else layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        author = self._author_name(entry, me_id)
        layout.addWidget(Avatar(entry.author_id or "", author, row, size=20), 0, Qt.AlignTop)
        body = QVBoxLayout()
        body.setSpacing(2)
        body.setContentsMargins(0, 0, 0, 0)
        title = QHBoxLayout()
        title.setSpacing(6)
        name = QLabel(author, row)
        name.setObjectName("shell.teamSync.feedName")
        when = QLabel(clock(entry.when), row)
        when.setObjectName("shell.teamSync.feedTime")
        title.addWidget(name)
        title.addWidget(when)
        title.addStretch(1)
        body.addLayout(title)
        note = QLabel(entry.text, row)
        note.setObjectName("shell.teamSync.feedNote")
        note.setWordWrap(True)
        body.addWidget(note)
        meta = QHBoxLayout()
        meta.setContentsMargins(0, 4, 0, 0)
        meta.setSpacing(8)
        if entry.change is not None:
            count = len(entry.change.files)
            link = QPushButton(f"{count} file" if count == 1 else f"{count} files", row)
            link.setObjectName("shell.teamSync.feedFiles")
            link.setFlat(True)
            link.setCursor(Qt.PointingHandCursor)
            change_id = entry.change.id
            incoming_id = entry.incoming.id if entry.incoming is not None else ""
            if incoming_id:
                link.clicked.connect(lambda _checked=False, ident=incoming_id: self._review(ident))
            else:
                link.clicked.connect(lambda _checked=False, ident=change_id: self._open_change(ident))
            meta.addWidget(link, 0, Qt.AlignLeft)
        meta.addStretch(1)
        if entry.delivery is not None:
            mark, tip = delivery_mark(entry.delivery.state, git_names=self._git_names)
            badge = QLabel(mark, row)
            badge.setObjectName("shell.teamSync.feedMark")
            badge.setProperty("delivery", _delivery_key(entry.delivery.state))
            badge.setToolTip(tip)
            font = QFont(badge.font())
            font.setLetterSpacing(QFont.AbsoluteSpacing, -0.4)
            badge.setFont(font)
            _polish(badge)
            meta.addWidget(badge, 0, Qt.AlignRight)
        if incoming and entry.incoming is not None:
            review = QPushButton("Review", row)
            review.setObjectName("shell.teamSync.feedReview")
            review.setCursor(Qt.PointingHandCursor)
            incoming_id = entry.incoming.id
            review.clicked.connect(lambda _checked=False, ident=incoming_id: self._review(ident))
            meta.addWidget(review, 0, Qt.AlignRight)
        body.addLayout(meta)
        layout.addLayout(body, 1)
        _polish(row)
        return row

    def _author_name(self, entry: FeedItem, me_id: str) -> str:
        if entry.author_id and entry.author_id == me_id:
            return "You"
        if entry.change is not None:
            return first_name(entry.change.author_name)
        if entry.incoming is not None and entry.incoming.changes:
            return first_name(entry.incoming.changes[0].author_name)
        return "Team"

    def _fill_files(self, status: TeamStatus) -> None:
        while self._file_layout.count():
            item = self._file_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._checks = []
        count = len(status.pending)
        noun = "file" if count == 1 else "files"
        self._files_button.setText(f"{count} {noun}")
        self._files_button.setVisible(count > 0)
        if count == 0:
            self._files_button.setChecked(False)
            self._file_list.hide()
        for change in status.pending:
            box = QCheckBox(f"{change.kind}  {change.path}", self._file_list)
            box.setChecked(True)
            self._file_layout.addWidget(box)
            self._checks.append((box, change.path))

    def _toggle_files(self, checked: bool) -> None:
        self._file_list.setVisible(checked and bool(self._checks))

    def selected_paths(self) -> list[str]:
        if not self._checks:
            return []
        return [path for box, path in self._checks if box.isChecked()]

    def note_text(self) -> str:
        return self._note.text().strip()

    def _share(self) -> None:
        if self._on_share is not None:
            self._on_share()

    def _send_clicked(self) -> None:
        if self._on_send is not None:
            self._on_send(self.note_text(), self.selected_paths())

    def _save_only_clicked(self) -> None:
        if self._on_save_only is not None:
            self._on_save_only(self.note_text(), self.selected_paths())

    def _set_aside_clicked(self) -> None:
        if self._on_set_aside is not None:
            self._on_set_aside(self.note_text() or "Set aside")

    def _bring_back_clicked(self) -> None:
        if self._on_bring_back is not None:
            self._on_bring_back(self._set_aside_index)

    def _review(self, incoming_id: str) -> None:
        if self._on_review is not None:
            self._on_review(incoming_id)

    def _open_change(self, change_id: str) -> None:
        if self._on_open_change is not None:
            self._on_open_change(change_id)


__all__ = ["TeamView"]
