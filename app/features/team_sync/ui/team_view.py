"""Thread view: the Team activity-bar page."""

from __future__ import annotations

from typing import Callable, Optional

from app.qt.QtCore import Qt
from app.qt.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.features.team_sync.api import (
    FEED_CHANGE,
    FEED_INCOMING,
    FEED_NOTE,
    FEED_SYSTEM,
    FeedItem,
    TeamStatus,
)
from app.features.team_sync.ui.copy import clock, delivery_mark, first_name
from app.features.team_sync.ui.theme import button_qss, field_qss, incoming_qss, muted_qss, primary_button_qss, surface_qss
from app.features.team_sync.ui.widgets import Avatar
from app.shell.theme_tokens import ShellThemeTokens


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
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(12, 8, 12, 8)
        title = QLabel("TEAM", header)
        title.setObjectName("shell.teamSync.teamTitle")
        header_row.addWidget(title)
        header_row.addStretch(1)
        self._avatars = QHBoxLayout()
        self._avatars.setSpacing(4)
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
        self._feed_host = QWidget(self._scroll)
        self._feed_layout = QVBoxLayout(self._feed_host)
        self._feed_layout.setContentsMargins(10, 8, 10, 8)
        self._feed_layout.setSpacing(8)
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
        composer_layout.addWidget(self._files_button, 0, Qt.AlignLeft)
        self._file_list = QWidget(composer)
        self._file_list.setObjectName("shell.teamSync.composerChecklist")
        self._file_layout = QVBoxLayout(self._file_list)
        self._file_layout.setContentsMargins(0, 0, 0, 0)
        self._file_layout.setSpacing(2)
        self._file_list.hide()
        composer_layout.addWidget(self._file_list)
        self._note = QTextEdit(composer)
        self._note.setObjectName("shell.teamSync.composerNote")
        self._note.setPlaceholderText("Message")
        self._note.setFixedHeight(64)
        composer_layout.addWidget(self._note)
        send_row = QHBoxLayout()
        send_row.addStretch(1)
        self._send = QToolButton(composer)
        self._send.setObjectName("shell.teamSync.composerSend")
        self._send.setText("Send")
        self._send.setPopupMode(QToolButton.MenuButtonPopup)
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
        self.setStyleSheet(surface_qss(tokens))
        header = self.findChild(QWidget, "shell.teamSync.teamHeader")
        if header is not None:
            header.setStyleSheet(
                f"background: {tokens.panel_bg}; border-bottom: 1px solid {tokens.border};"
            )
        self._share_button.setStyleSheet(primary_button_qss(tokens))
        self._note.setStyleSheet(field_qss(tokens))
        self._send.setStyleSheet(primary_button_qss(tokens).replace("QPushButton", "QToolButton"))
        self._bring_back.setStyleSheet(button_qss(tokens))
        self._files_button.setStyleSheet(button_qss(tokens).replace("QPushButton", "QToolButton"))

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
                widget.deleteLater()
        for member in status.members:
            avatar = Avatar(member.id, member.name, self)
            avatar.setToolTip(f"{member.name} · {member.shop}")
            self._avatars.addWidget(avatar)

    def _fill_feed(self, feed: list[FeedItem], status: TeamStatus) -> None:
        while self._feed_layout.count() > 1:
            item = self._feed_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        me = status.me.id if status.me is not None else ""
        for entry in feed:
            self._feed_layout.insertWidget(self._feed_layout.count() - 1, self._feed_row(entry, me))

    def _feed_row(self, entry: FeedItem, me_id: str) -> QWidget:
        if entry.kind == FEED_SYSTEM:
            label = QLabel(f"{entry.text} · {clock(entry.when)}", self._feed_host)
            label.setAlignment(Qt.AlignCenter)
            if self._tokens is not None:
                label.setStyleSheet(muted_qss(self._tokens))
            return label
        row = QWidget(self._feed_host)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        author = self._author_name(entry, me_id)
        member_id = entry.author_id or ""
        layout.addWidget(Avatar(member_id, author, row), 0, Qt.AlignTop)
        body = QVBoxLayout()
        body.setSpacing(2)
        title = QLabel(f"{author} · {clock(entry.when)}", row)
        body.addWidget(title)
        note = QLabel(entry.text, row)
        note.setWordWrap(True)
        body.addWidget(note)
        if entry.change is not None:
            count = len(entry.change.files)
            link = QPushButton(f"{count} files" if count != 1 else "1 file", row)
            link.setFlat(True)
            change_id = entry.change.id
            incoming_id = entry.incoming.id if entry.incoming is not None else ""
            if incoming_id:
                link.clicked.connect(lambda _checked=False, ident=incoming_id: self._review(ident))
            else:
                link.clicked.connect(lambda _checked=False, ident=change_id: self._open_change(ident))
            body.addWidget(link, 0, Qt.AlignLeft)
        if entry.delivery is not None:
            mark, tip = delivery_mark(entry.delivery.state, git_names=self._git_names)
            badge = QLabel(mark, row)
            badge.setToolTip(tip)
            body.addWidget(badge, 0, Qt.AlignLeft)
        if entry.kind == FEED_INCOMING and entry.incoming is not None:
            review = QPushButton("Review", row)
            review.setObjectName("shell.teamSync.feedReview")
            incoming_id = entry.incoming.id
            review.clicked.connect(lambda _checked=False, ident=incoming_id: self._review(ident))
            if self._tokens is not None:
                review.setStyleSheet(primary_button_qss(self._tokens))
                row.setStyleSheet(incoming_qss(self._tokens))
            body.addWidget(review, 0, Qt.AlignLeft)
        elif entry.kind in (FEED_NOTE, FEED_CHANGE) and self._tokens is not None:
            row.setStyleSheet("background: transparent;")
        layout.addLayout(body, 1)
        return row

    def _author_name(self, entry: FeedItem, me_id: str) -> str:
        if entry.author_id and entry.author_id == me_id:
            return "You"
        if entry.change is not None:
            return first_name(entry.change.author_name)
        return "Team"

    def _fill_files(self, status: TeamStatus) -> None:
        while self._file_layout.count():
            item = self._file_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._checks = []
        count = len(status.pending)
        noun = "file" if count == 1 else "files"
        self._files_button.setText(f"{count} {noun}")
        for change in status.pending:
            box = QCheckBox(f"{change.kind}  {change.path}", self._file_list)
            box.setChecked(True)
            self._file_layout.addWidget(box)
            self._checks.append((box, change.path))

    def _toggle_files(self, checked: bool) -> None:
        self._file_list.setVisible(checked)

    def selected_paths(self) -> list[str]:
        if not self._checks:
            return []
        return [path for box, path in self._checks if box.isChecked()]

    def note_text(self) -> str:
        return self._note.toPlainText().strip()

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
