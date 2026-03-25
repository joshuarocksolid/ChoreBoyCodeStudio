"""Local history and draft-recovery dialogs."""

from __future__ import annotations

import difflib
from typing import Callable, Optional

from PySide2.QtCore import Qt
from PySide2.QtGui import QFontDatabase
from PySide2.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.persistence.history_models import LocalHistoryCheckpoint


def build_unified_diff(before_text: str, after_text: str, *, from_label: str, to_label: str) -> str:
    """Return unified diff text for two buffer snapshots."""
    diff_lines = difflib.unified_diff(
        before_text.splitlines(),
        after_text.splitlines(),
        fromfile=from_label,
        tofile=to_label,
        lineterm="",
    )
    diff_text = "\n".join(diff_lines)
    if diff_text:
        return diff_text
    return "No textual differences found."


class DraftRecoveryDialog(QDialog):
    """Review dialog for comparing a saved file with a recovery draft."""

    def __init__(
        self,
        *,
        file_name: str,
        disk_text: str,
        draft_text: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._discard_draft = False
        self.setWindowTitle("Review Recovery Draft")
        self.resize(920, 620)

        summary = QLabel(
            f"A recovery draft is available for {file_name}. Review the diff below before restoring it to the editor buffer."
        )
        summary.setWordWrap(True)

        diff_view = QPlainTextEdit(self)
        diff_view.setReadOnly(True)
        diff_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        diff_view.setPlainText(
            build_unified_diff(
                disk_text,
                draft_text,
                from_label="Saved on Disk",
                to_label="Recovery Draft",
            )
        )
        diff_view.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self._diff_view = diff_view

        restore_button = QPushButton("Restore Draft to Buffer", self)
        keep_disk_button = QPushButton("Keep Disk Version", self)
        close_button = QPushButton("Close", self)
        restore_button.clicked.connect(self.accept)
        keep_disk_button.clicked.connect(self._handle_keep_disk_version)
        close_button.clicked.connect(self.reject)
        restore_button.setDefault(True)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(close_button)
        button_row.addWidget(keep_disk_button)
        button_row.addWidget(restore_button)

        layout = QVBoxLayout(self)
        layout.addWidget(summary)
        layout.addWidget(diff_view, 1)
        layout.addLayout(button_row)

    @property
    def discard_draft(self) -> bool:
        """Return True when the user explicitly chose disk content over the draft."""
        return self._discard_draft

    def _handle_keep_disk_version(self) -> None:
        self._discard_draft = True
        self.reject()


class LocalHistoryDialog(QDialog):
    """Revision timeline dialog for one file."""

    def __init__(
        self,
        *,
        file_name: str,
        checkpoints: list[LocalHistoryCheckpoint],
        current_text: str,
        checkpoint_content_loader: Callable[[int], Optional[str]],
        restore_to_buffer: Callable[[str], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._checkpoints = list(checkpoints)
        self._current_text = current_text
        self._checkpoint_content_loader = checkpoint_content_loader
        self._restore_to_buffer = restore_to_buffer
        self._compare_mode = "current"
        self._loaded_checkpoint_contents: dict[int, Optional[str]] = {}

        self.setWindowTitle(f"Local History — {file_name}")
        self.resize(1000, 680)

        summary = QLabel(
            "Browse saved local-history entries, compare with the current buffer or the previous revision, and restore a revision back into the editor buffer."
        )
        summary.setWordWrap(True)

        revision_tree = QTreeWidget(self)
        revision_tree.setHeaderLabels(["Timestamp", "Label"])
        revision_tree.setAlternatingRowColors(True)
        revision_tree.setUniformRowHeights(True)
        revision_tree.itemSelectionChanged.connect(self._refresh_diff_view)
        self._revision_tree = revision_tree

        diff_view = QPlainTextEdit(self)
        diff_view.setReadOnly(True)
        diff_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        diff_view.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self._diff_view = diff_view

        splitter = QSplitter(self)
        splitter.addWidget(revision_tree)
        splitter.addWidget(diff_view)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        compare_current_button = QPushButton("Compare with Current", self)
        compare_previous_button = QPushButton("Compare with Previous", self)
        restore_button = QPushButton("Restore to Buffer", self)
        close_button = QPushButton("Close", self)
        compare_current_button.clicked.connect(self._compare_with_current)
        compare_previous_button.clicked.connect(self._compare_with_previous)
        restore_button.clicked.connect(self._handle_restore)
        close_button.clicked.connect(self.reject)
        self._compare_previous_button = compare_previous_button
        self._restore_button = restore_button

        button_row = QHBoxLayout()
        button_row.addWidget(compare_current_button)
        button_row.addWidget(compare_previous_button)
        button_row.addStretch(1)
        button_row.addWidget(close_button)
        button_row.addWidget(restore_button)

        layout = QVBoxLayout(self)
        layout.addWidget(summary)
        layout.addWidget(splitter, 1)
        layout.addLayout(button_row)

        self._populate_revision_tree()
        self._refresh_button_states()
        self._refresh_diff_view()

    def _populate_revision_tree(self) -> None:
        self._revision_tree.clear()
        for checkpoint in self._checkpoints:
            label = checkpoint.label or checkpoint.source.replace("_", " ")
            item = QTreeWidgetItem([checkpoint.created_at, label])
            item.setData(0, Qt.UserRole, checkpoint.revision_id)
            self._revision_tree.addTopLevelItem(item)
        if self._revision_tree.topLevelItemCount() > 0:
            self._revision_tree.setCurrentItem(self._revision_tree.topLevelItem(0))

    def _selected_checkpoint(self) -> Optional[LocalHistoryCheckpoint]:
        current_item = self._revision_tree.currentItem()
        if current_item is None:
            return None
        revision_id = current_item.data(0, Qt.UserRole)
        for checkpoint in self._checkpoints:
            if checkpoint.revision_id == revision_id:
                return checkpoint
        return None

    def _checkpoint_before_selected(self, selected: LocalHistoryCheckpoint) -> Optional[LocalHistoryCheckpoint]:
        for index, checkpoint in enumerate(self._checkpoints):
            if checkpoint.revision_id != selected.revision_id:
                continue
            next_index = index + 1
            if next_index >= len(self._checkpoints):
                return None
            return self._checkpoints[next_index]
        return None

    def _compare_with_current(self) -> None:
        self._compare_mode = "current"
        self._refresh_button_states()
        self._refresh_diff_view()

    def _compare_with_previous(self) -> None:
        selected = self._selected_checkpoint()
        if selected is None or self._checkpoint_before_selected(selected) is None:
            return
        self._compare_mode = "previous"
        self._refresh_button_states()
        self._refresh_diff_view()

    def _refresh_button_states(self) -> None:
        selected = self._selected_checkpoint()
        has_previous = selected is not None and self._checkpoint_before_selected(selected) is not None
        self._compare_previous_button.setEnabled(has_previous)
        self._restore_button.setEnabled(selected is not None)

    def _load_checkpoint_content(self, revision_id: int) -> Optional[str]:
        if revision_id not in self._loaded_checkpoint_contents:
            self._loaded_checkpoint_contents[revision_id] = self._checkpoint_content_loader(revision_id)
        return self._loaded_checkpoint_contents[revision_id]

    def _refresh_diff_view(self) -> None:
        self._refresh_button_states()
        selected = self._selected_checkpoint()
        if selected is None:
            self._diff_view.setPlainText("No revision selected.")
            return

        selected_content = self._load_checkpoint_content(selected.revision_id)
        if selected_content is None:
            self._diff_view.setPlainText("Could not load the selected revision.")
            return

        if self._compare_mode == "previous":
            previous_checkpoint = self._checkpoint_before_selected(selected)
            if previous_checkpoint is None:
                self._diff_view.setPlainText("No previous revision is available for comparison.")
                return
            previous_content = self._load_checkpoint_content(previous_checkpoint.revision_id)
            if previous_content is None:
                self._diff_view.setPlainText("Could not load the previous revision.")
                return
            self._diff_view.setPlainText(
                build_unified_diff(
                    previous_content,
                    selected_content,
                    from_label=previous_checkpoint.created_at,
                    to_label=selected.created_at,
                )
            )
            return

        self._diff_view.setPlainText(
            build_unified_diff(
                self._current_text,
                selected_content,
                from_label="Current Buffer",
                to_label=selected.created_at,
            )
        )

    def _handle_restore(self) -> None:
        selected = self._selected_checkpoint()
        if selected is None:
            return
        selected_content = self._load_checkpoint_content(selected.revision_id)
        if selected_content is None:
            QMessageBox.warning(self, "Local History", "Could not load the selected revision.")
            return
        self._restore_to_buffer(selected_content)
        self.accept()
