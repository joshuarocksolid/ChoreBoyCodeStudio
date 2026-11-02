"""Share, Invite, Members, and the deleted-clash choice."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

from app.qt.QtCore import Qt
from app.qt.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.features.team_sync.api import (
    RESOLVE_DELETE,
    RESOLVE_OURS,
    Incoming,
    Invite,
    ShareRequest,
    TeamStatus,
)
from app.features.team_sync.ui.copy import first_name
from app.features.team_sync.ui.theme import button_qss, field_qss, primary_button_qss
from app.qt.qt_compat import exec_qt
from app.shell.dialog_chrome import (
    FOOTER_ROLE_PRIMARY,
    FOOTER_ROLE_SECONDARY,
    add_footer_button,
    add_footer_stretch,
    add_meta_chip,
    build_dialog_chrome,
)
from app.shell.theme_tokens import ShellThemeTokens


def _present(dialog: QDialog) -> int:
    dialog.show()
    dialog.raise_()
    if os.environ.get("CBCS_TEAM_SYNC_SHOTS"):
        return 0
    return exec_qt(dialog)


class ShareDialog(QDialog):
    def __init__(
        self,
        status: TeamStatus,
        chip: str,
        on_send: Callable[..., None],
        parent: Optional[QWidget] = None,
        tokens: Optional[ShellThemeTokens] = None,
    ) -> None:
        super().__init__(parent)
        self._on_send = on_send
        self._project_name = status.project_name or "Project"
        name = self._project_name
        self.setObjectName("shell.teamSync.shareDialog")
        chrome = build_dialog_chrome(
            self,
            title=f"Share {name}",
            object_name="shell.teamSync.shareDialog",
        )
        add_meta_chip(chrome.meta_row, chip)
        form_host = QWidget(chrome.body)
        form = QFormLayout(form_host)
        body_layout = chrome.body.layout()
        if isinstance(body_layout, QVBoxLayout):
            body_layout.addWidget(form_host)
        self._email = QLineEdit(form_host)
        self._email.setObjectName("shell.teamSync.shareEmail")
        self._shop = QLineEdit(form_host)
        self._shop.setObjectName("shell.teamSync.shareShop")
        self._message = QTextEdit(form_host)
        self._message.setObjectName("shell.teamSync.shareMessage")
        self._message.setFixedHeight(72)
        form.addRow("Email", self._email)
        form.addRow("Shop", self._shop)
        form.addRow("Message", self._message)
        self._error = QLabel("", form_host)
        self._error.setObjectName("shell.teamSync.shareError")
        self._error.setWordWrap(True)
        form.addRow("", self._error)
        if tokens is not None:
            for field in (self._email, self._shop, self._message):
                field.setStyleSheet(field_qss(tokens))
            self._error.setStyleSheet(f"color: {tokens.diag_error_color or '#9C0000'};")
        add_footer_stretch(chrome)
        cancel = add_footer_button(chrome, "Cancel", role=FOOTER_ROLE_SECONDARY)
        send = add_footer_button(chrome, "Send Invite", role=FOOTER_ROLE_PRIMARY)
        cancel.clicked.connect(self.reject)
        send.clicked.connect(self._send)
        self.resize(480, 360)

    def _send(self) -> None:
        email = self._email.text().strip()
        shop = self._shop.text().strip()
        invites = []
        if email or shop:
            invites.append(Invite(name=email.split("@", 1)[0], shop=shop, email=email))
        self._error.setText("")
        self._on_send(
            ShareRequest(
                project_name=self._project_name,
                invites=invites,
                message=self._message.toPlainText().strip(),
            ),
            self.accept,
            self._show_error,
        )

    def _show_error(self, exc: BaseException) -> None:
        self._error.setText(str(exc))


class InviteDialog(QDialog):
    def __init__(
        self,
        incoming: Incoming,
        on_open: Callable[..., None],
        parent: Optional[QWidget] = None,
        tokens: Optional[ShellThemeTokens] = None,
        project_name: str = "Invoice App",
        default_location: str = "",
        author_name: str = "",
    ) -> None:
        super().__init__(parent)
        self._on_open = on_open
        self._incoming_id = incoming.id
        if author_name:
            author = first_name(author_name)
        elif incoming.changes:
            author = first_name(incoming.changes[0].author_name)
        else:
            author = "Someone"
        self.setObjectName("shell.teamSync.inviteDialog")
        chrome = build_dialog_chrome(
            self,
            title=f"{author} invited you to {project_name}",
            object_name="shell.teamSync.inviteDialog",
        )
        if incoming.verified:
            add_meta_chip(chrome.meta_row, "✓ Verified")
        form_host = QWidget(chrome.body)
        form = QFormLayout(form_host)
        body_layout = chrome.body.layout()
        if isinstance(body_layout, QVBoxLayout):
            body_layout.addWidget(form_host)
        location_row = QWidget(form_host)
        location_layout = QHBoxLayout(location_row)
        location_layout.setContentsMargins(0, 0, 0, 0)
        self._location = QLineEdit(location_row)
        self._location.setObjectName("shell.teamSync.inviteLocation")
        self._location.setText(default_location)
        browse = QPushButton("Browse…", location_row)
        browse.setObjectName("shell.teamSync.inviteBrowse")
        browse.clicked.connect(self._browse)
        location_layout.addWidget(self._location, 1)
        location_layout.addWidget(browse)
        form.addRow("Location", location_row)
        self._error = QLabel("", form_host)
        self._error.setObjectName("shell.teamSync.inviteError")
        self._error.setWordWrap(True)
        form.addRow("", self._error)
        if tokens is not None:
            self._location.setStyleSheet(field_qss(tokens))
            self._error.setStyleSheet(f"color: {tokens.diag_error_color or '#9C0000'};")
        add_footer_stretch(chrome)
        cancel = add_footer_button(chrome, "Cancel", role=FOOTER_ROLE_SECONDARY)
        open_button = add_footer_button(chrome, "Open Project", role=FOOTER_ROLE_PRIMARY)
        cancel.clicked.connect(self.reject)
        open_button.clicked.connect(self._open)
        self.resize(520, 260)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open Project", self._location.text().strip())
        if not folder:
            return
        if _folder_has_files(folder):
            self._error.setText("Choose a new or empty folder. That one already has files.")
            return
        self._error.setText("")
        self._location.setText(folder)

    def _open(self) -> None:
        folder = self._location.text().strip()
        if folder and _folder_has_files(folder):
            self._error.setText("Choose a new or empty folder. That one already has files.")
            return
        self._error.setText("")
        self._on_open(self._incoming_id, folder, self.accept, self._show_error)

    def _show_error(self, exc: BaseException) -> None:
        self._error.setText(str(exc))


class MembersDialog(QDialog):
    def __init__(
        self,
        status: TeamStatus,
        on_remove: Callable[[str], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._on_remove = on_remove
        self.setObjectName("shell.teamSync.membersDialog")
        chrome = build_dialog_chrome(self, title="Members", object_name="shell.teamSync.membersDialog")
        self._list = QListWidget(chrome.body)
        self._list.setObjectName("shell.teamSync.membersList")
        for member in status.members:
            item = QListWidgetItem(f"{member.name} · {member.shop}")
            item.setData(Qt.UserRole, member.id)
            self._list.addItem(item)
        layout = chrome.body.layout()
        if isinstance(layout, QVBoxLayout):
            layout.addWidget(self._list)
        else:
            host = QVBoxLayout(chrome.body)
            host.addWidget(self._list)
        add_footer_stretch(chrome)
        close = add_footer_button(chrome, "Close", role=FOOTER_ROLE_SECONDARY)
        remove = add_footer_button(chrome, "Remove", role=FOOTER_ROLE_PRIMARY)
        close.clicked.connect(self.accept)
        remove.clicked.connect(self._remove)
        self.resize(420, 320)

    def _remove(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        member_id = str(item.data(Qt.UserRole) or "")
        if member_id:
            self._on_remove(member_id)
            row = self._list.row(item)
            self._list.takeItem(row)


def _folder_has_files(folder: str) -> bool:
    root = Path(folder)
    return root.exists() and (not root.is_dir() or any(root.iterdir()))


class DeletedClashDialog(QDialog):
    def __init__(
        self,
        path: str,
        chip: str,
        on_choice: Callable[[str], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._on_choice = on_choice
        self.setObjectName("shell.teamSync.deletedClashDialog")
        chrome = build_dialog_chrome(
            self,
            title=path,
            subtitle="",
            object_name="shell.teamSync.deletedClashDialog",
        )
        add_meta_chip(chrome.meta_row, chip)
        add_footer_stretch(chrome)
        keep = add_footer_button(chrome, "Keep your version", role=FOOTER_ROLE_SECONDARY)
        delete = add_footer_button(chrome, "Delete it", role=FOOTER_ROLE_PRIMARY)
        keep.clicked.connect(lambda: self._choose(RESOLVE_OURS))
        delete.clicked.connect(lambda: self._choose(RESOLVE_DELETE))
        self.resize(420, 180)

    def _choose(self, resolution: str) -> None:
        self._on_choice(resolution)
        self.accept()


def choose_usb_save(parent: QWidget) -> str:
    path, _selected = QFileDialog.getSaveFileName(parent, "Save to USB", "team.cbcsbundle", "Bundle (*.cbcsbundle)")
    return path


def choose_usb_open(parent: QWidget) -> str:
    path, _selected = QFileDialog.getOpenFileName(parent, "Open from USB", "", "Bundle (*.cbcsbundle)")
    return path


def show_share(*args, **kwargs) -> ShareDialog:  # type: ignore[no-untyped-def]
    dialog = ShareDialog(*args, **kwargs)
    _present(dialog)
    return dialog


def show_invite(*args, **kwargs) -> InviteDialog:  # type: ignore[no-untyped-def]
    dialog = InviteDialog(*args, **kwargs)
    _present(dialog)
    return dialog


def show_members(*args, **kwargs) -> MembersDialog:  # type: ignore[no-untyped-def]
    dialog = MembersDialog(*args, **kwargs)
    _present(dialog)
    return dialog


def show_deleted(*args, **kwargs) -> DeletedClashDialog:  # type: ignore[no-untyped-def]
    dialog = DeletedClashDialog(*args, **kwargs)
    _present(dialog)
    return dialog


__all__ = [
    "DeletedClashDialog",
    "InviteDialog",
    "MembersDialog",
    "ShareDialog",
    "choose_usb_open",
    "choose_usb_save",
    "show_deleted",
    "show_invite",
    "show_members",
    "show_share",
]
