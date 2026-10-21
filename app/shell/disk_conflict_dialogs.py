"""Dialogs for a buffer whose file changed on disk or went missing."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from PySide2.QtGui import QFontDatabase
from PySide2.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.shell.dialog_chrome import (
    FOOTER_ROLE_DESTRUCTIVE_SECONDARY,
    FOOTER_ROLE_LINK,
    FOOTER_ROLE_PRIMARY,
    FOOTER_ROLE_SECONDARY,
    add_footer_button,
    add_footer_stretch,
    add_meta_chip,
    build_dialog_chrome,
)
from app.shell.diff_view import DIFF_VIEW_MODE_SIDE_BY_SIDE, DiffView
from app.shell.editor_tab_bar import missing_marker_icon, warning_marker_icon
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette


class MissingFileDialogChoice(str, Enum):
    CLOSE_TAB = "close_tab"
    KEEP_EDITING = "keep_editing"
    SAVE_AS = "save_as"


class DiskChangedChoice(str, Enum):
    """What to do when the poller finds a dirty buffer's file changed on disk."""

    KEEP_MY_VERSION = "keep_my_version"
    COMPARE = "compare"
    RELOAD_FROM_DISK = "reload_from_disk"


class StaleSaveChoice(str, Enum):
    CANCEL = "cancel"
    COMPARE = "compare"
    RELOAD_FROM_DISK = "reload_from_disk"
    SAVE_MY_VERSION = "save_my_version"


def resolve_dialog_tokens(parent: Optional[QWidget], fallback: QWidget) -> ShellThemeTokens:
    accessor = getattr(parent, "current_theme_tokens", None)
    if callable(accessor):
        try:
            resolved = accessor()
        except Exception:  # pragma: no cover - parent in shutdown
            resolved = None
        if isinstance(resolved, ShellThemeTokens):
            return resolved
    return tokens_from_palette(fallback.palette())


def _field_row(parent: QWidget, key: str, value: str, tokens: ShellThemeTokens) -> QWidget:
    row = QWidget(parent)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    key_label = QLabel(key, row)
    key_label.setStyleSheet(f"color: {tokens.text_muted};")
    value_label = QLabel(value, row)
    value_label.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
    value_label.setStyleSheet(f"color: {tokens.text_primary};")
    value_label.setWordWrap(True)
    layout.addWidget(key_label, 0)
    layout.addWidget(value_label, 1)
    return row


def _note(parent: QWidget, text: str, tokens: ShellThemeTokens) -> QLabel:
    label = QLabel(text, parent)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {tokens.text_muted};")
    return label


class MissingFileDialog(QDialog):
    """`old_utils.py is not on disk any more`: Close Tab / Keep Editing / Save As..."""

    def __init__(self, file_path: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._choice = MissingFileDialogChoice.KEEP_EDITING
        tokens = resolve_dialog_tokens(parent, self)
        self.setWindowTitle("File Missing")
        chrome = build_dialog_chrome(
            self,
            title=f"{Path(file_path).name} is not on disk any more",
            subtitle="It was deleted, renamed, or moved outside CBCS. Your text is still open in this tab.",
            object_name="shell.missingFileDialog",
            icon=missing_marker_icon(tokens.diag_error_color or "#E03131", 22),
        )
        self.setObjectName("shell.missingFileDialog")
        body_layout = chrome.body.layout()
        assert isinstance(body_layout, QVBoxLayout)
        body_layout.addWidget(_field_row(chrome.body, "Was at", file_path, tokens))
        body_layout.addWidget(
            _note(
                chrome.body,
                "Keep Editing leaves the tab open and marked missing. "
                "If you save it, CBCS puts the file back where it was.",
                tokens,
            )
        )
        close_button = add_footer_button(chrome, "Close Tab", role=FOOTER_ROLE_DESTRUCTIVE_SECONDARY)
        close_button.setToolTip("Close the tab. Unsaved text in it is lost.")
        add_footer_stretch(chrome)
        keep_button = add_footer_button(chrome, "Keep Editing", role=FOOTER_ROLE_SECONDARY)
        save_as_button = add_footer_button(chrome, "Save As...", role=FOOTER_ROLE_PRIMARY, default=True)
        close_button.clicked.connect(lambda: self._finish(MissingFileDialogChoice.CLOSE_TAB))
        keep_button.clicked.connect(lambda: self._finish(MissingFileDialogChoice.KEEP_EDITING))
        save_as_button.clicked.connect(lambda: self._finish(MissingFileDialogChoice.SAVE_AS))
        self.resize(560, self.sizeHint().height())

    def choice(self) -> MissingFileDialogChoice:
        return self._choice

    def _finish(self, choice: MissingFileDialogChoice) -> None:
        self._choice = choice
        self.accept()


class StaleSaveDialog(QDialog):
    """Save on a stale tab: Cancel / Compare... / Reload from Disk / Save My Version."""

    def __init__(
        self,
        file_path: str,
        *,
        disk_changed_text: str,
        buffer_is_dirty: bool,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._choice = StaleSaveChoice.CANCEL
        tokens = resolve_dialog_tokens(parent, self)
        self.setWindowTitle("Save Changes")
        chrome = build_dialog_chrome(
            self,
            title=f"{Path(file_path).name} changed on disk",
            subtitle=(
                "The file on disk changed after you chose to keep your version. "
                "Saving now replaces the newer file on disk with your version."
            ),
            object_name="shell.staleSaveDialog",
            icon=warning_marker_icon(tokens.diag_warning_color or "#D97706", 22),
        )
        self.setObjectName("shell.staleSaveDialog")
        if disk_changed_text:
            add_meta_chip(chrome.meta_row, f"On disk: {disk_changed_text}")
        add_meta_chip(chrome.meta_row, "Your version: unsaved changes" if buffer_is_dirty else "Your version: open in CBCS")
        body_layout = chrome.body.layout()
        assert isinstance(body_layout, QVBoxLayout)
        body_layout.addWidget(_field_row(chrome.body, "File", file_path, tokens))
        body_layout.addWidget(
            _note(
                chrome.body,
                "<b>Save My Version</b> writes your text over the file on disk.<br>"
                "<b>Reload from Disk</b> throws away your changes and shows the file on disk.<br>"
                "<b>Compare...</b> shows both versions side by side before you choose.",
                tokens,
            )
        )
        cancel_button = add_footer_button(chrome, "Cancel", role=FOOTER_ROLE_SECONDARY)
        compare_button = add_footer_button(chrome, "Compare...", role=FOOTER_ROLE_LINK)
        add_footer_stretch(chrome)
        reload_button = add_footer_button(chrome, "Reload from Disk", role=FOOTER_ROLE_DESTRUCTIVE_SECONDARY)
        save_button = add_footer_button(chrome, "Save My Version", role=FOOTER_ROLE_PRIMARY, default=True)
        cancel_button.clicked.connect(self.reject)
        compare_button.clicked.connect(lambda: self._finish(StaleSaveChoice.COMPARE))
        reload_button.clicked.connect(lambda: self._finish(StaleSaveChoice.RELOAD_FROM_DISK))
        save_button.clicked.connect(lambda: self._finish(StaleSaveChoice.SAVE_MY_VERSION))
        self.resize(600, self.sizeHint().height())

    def choice(self) -> StaleSaveChoice:
        return self._choice

    def _finish(self, choice: StaleSaveChoice) -> None:
        self._choice = choice
        self.accept()


class DiskChangedDialog(QDialog):
    """The file changed on disk while the buffer has unsaved changes.

    Same layout as the stale save prompt, worded for the moment the poller
    notices the change: Compare... / Reload from Disk / Keep My Version. Keep My
    Version is the default and also what Esc or closing the window means, so
    nothing is lost by accident.
    """

    def __init__(
        self,
        file_path: str,
        *,
        disk_changed_text: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._choice = DiskChangedChoice.KEEP_MY_VERSION
        tokens = resolve_dialog_tokens(parent, self)
        self.setWindowTitle("File Changed on Disk")
        chrome = build_dialog_chrome(
            self,
            title=f"{Path(file_path).name} changed on disk",
            subtitle=(
                "Another program changed this file while you had unsaved changes in CBCS. "
                "Choose which version to keep."
            ),
            object_name="shell.diskChangedDialog",
            icon=warning_marker_icon(tokens.diag_warning_color or "#D97706", 22),
        )
        self.setObjectName("shell.diskChangedDialog")
        if disk_changed_text:
            add_meta_chip(chrome.meta_row, f"On disk: {disk_changed_text}")
        add_meta_chip(chrome.meta_row, "Your version: unsaved changes")
        body_layout = chrome.body.layout()
        assert isinstance(body_layout, QVBoxLayout)
        body_layout.addWidget(_field_row(chrome.body, "File", file_path, tokens))
        body_layout.addWidget(
            _note(
                chrome.body,
                "<b>Keep My Version</b> keeps your text. The tab is marked changed on disk, "
                "and CBCS asks again before Save replaces the file.<br>"
                "<b>Reload from Disk</b> throws away your changes and shows the file on disk. "
                "Your text is kept in Local History.<br>"
                "<b>Compare...</b> shows both versions side by side before you choose.",
                tokens,
            )
        )
        compare_button = add_footer_button(chrome, "Compare...", role=FOOTER_ROLE_LINK)
        add_footer_stretch(chrome)
        reload_button = add_footer_button(chrome, "Reload from Disk", role=FOOTER_ROLE_DESTRUCTIVE_SECONDARY)
        keep_button = add_footer_button(chrome, "Keep My Version", role=FOOTER_ROLE_PRIMARY, default=True)
        compare_button.clicked.connect(lambda: self._finish(DiskChangedChoice.COMPARE))
        reload_button.clicked.connect(lambda: self._finish(DiskChangedChoice.RELOAD_FROM_DISK))
        keep_button.clicked.connect(lambda: self._finish(DiskChangedChoice.KEEP_MY_VERSION))
        self.resize(600, self.sizeHint().height())

    def choice(self) -> DiskChangedChoice:
        return self._choice

    def reject(self) -> None:
        # Esc and the window's close button keep the user's version.
        self._choice = DiskChangedChoice.KEEP_MY_VERSION
        super().reject()

    def _finish(self, choice: DiskChangedChoice) -> None:
        self._choice = choice
        self.accept()


class DiskCompareDialog(QDialog):
    """Side-by-side diff of the file on disk and the open buffer."""

    def __init__(
        self,
        file_path: str,
        *,
        disk_text: str,
        buffer_text: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        tokens = resolve_dialog_tokens(parent, self)
        self.setWindowTitle("Compare with Disk")
        chrome = build_dialog_chrome(
            self,
            title=f"{Path(file_path).name}: file on disk and your version",
            subtitle=file_path,
            object_name="shell.diskCompareDialog",
        )
        self.setObjectName("shell.diskCompareDialog")
        body_layout = chrome.body.layout()
        assert isinstance(body_layout, QVBoxLayout)
        diff_view = DiffView(tokens, chrome.body)
        diff_view.set_mode(DIFF_VIEW_MODE_SIDE_BY_SIDE)
        diff_view.set_texts(disk_text, buffer_text, before_label="On Disk", after_label="Your Version")
        if disk_text == buffer_text:
            diff_view.set_message("The file on disk and your version are the same.")
        body_layout.addWidget(diff_view, 1)
        add_footer_stretch(chrome)
        close_button = add_footer_button(chrome, "Close", role=FOOTER_ROLE_PRIMARY, default=True)
        close_button.clicked.connect(self.accept)
        self.resize(1000, 640)


__all__ = [
    "DiskChangedChoice",
    "DiskChangedDialog",
    "DiskCompareDialog",
    "MissingFileDialog",
    "MissingFileDialogChoice",
    "StaleSaveChoice",
    "StaleSaveDialog",
]
