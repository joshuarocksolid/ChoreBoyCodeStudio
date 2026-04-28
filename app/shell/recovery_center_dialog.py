"""Recovery Center dialog for drafts and local-history timelines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

RECOVERY_ENTRY_KIND_DRAFT = "draft"
RECOVERY_ENTRY_KIND_HISTORY = "history"
RECOVERY_ACTION_NONE = ""
RECOVERY_ACTION_REVIEW_DRAFT = "review_draft"
RECOVERY_ACTION_OPEN_TIMELINE = "open_timeline"
RECOVERY_ACTION_RESTORE_LATEST = "restore_latest"


@dataclass(frozen=True)
class RecoveryCenterEntry:
    """One recoverable draft or local-history timeline."""

    kind: str
    file_key: str
    file_path: str
    display_path: str
    timestamp: str
    label: str
    status: str


class RecoveryCenterDialog(QDialog):
    """Search and choose among draft and saved-history recovery entries."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._entries: list[RecoveryCenterEntry] = []
        self._entries_by_key: dict[str, RecoveryCenterEntry] = {}
        self._requested_action = RECOVERY_ACTION_NONE

        self.setWindowTitle("Recovery Center")
        self.resize(980, 620)

        summary = QLabel(
            "Search unsaved recovery drafts and saved local-history timelines. Drafts protect crash or hot-exit buffers; local history protects saved revisions, moves, and deletes."
        )
        summary.setWordWrap(True)

        search_input = QLineEdit(self)
        search_input.setPlaceholderText("Search by path, status, or label")
        search_input.textChanged.connect(self._refresh_results)
        self._search_input = search_input

        results = QTreeWidget(self)
        results.setHeaderLabels(["Type", "Path", "Status", "Latest", "Label"])
        results.setAlternatingRowColors(True)
        results.setUniformRowHeights(True)
        results.itemSelectionChanged.connect(self._handle_selection_changed)
        results.itemDoubleClicked.connect(self._handle_item_double_clicked)
        self._results = results

        detail_label = QLabel("Select an entry to review or restore.")
        detail_label.setWordWrap(True)
        detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._detail_label = detail_label

        review_draft_button = QPushButton("Review Draft", self)
        open_timeline_button = QPushButton("Open Timeline", self)
        restore_latest_button = QPushButton("Restore Latest to Buffer", self)
        close_button = QPushButton("Close", self)
        review_draft_button.clicked.connect(self._handle_review_draft)
        open_timeline_button.clicked.connect(self._handle_open_timeline)
        restore_latest_button.clicked.connect(self._handle_restore_latest)
        close_button.clicked.connect(self.reject)
        self._review_draft_button = review_draft_button
        self._open_timeline_button = open_timeline_button
        self._restore_latest_button = restore_latest_button

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(close_button)
        button_row.addWidget(review_draft_button)
        button_row.addWidget(open_timeline_button)
        button_row.addWidget(restore_latest_button)

        layout = QVBoxLayout(self)
        layout.addWidget(summary)
        layout.addWidget(search_input)
        layout.addWidget(results, 1)
        layout.addWidget(detail_label)
        layout.addLayout(button_row)
        self._refresh_button_states()

    @property
    def requested_action(self) -> str:
        return self._requested_action

    def set_entries(self, entries: list[RecoveryCenterEntry]) -> None:
        self._entries = list(entries)
        self._entries_by_key = {self._entry_key(entry): entry for entry in self._entries}
        self._requested_action = RECOVERY_ACTION_NONE
        self._search_input.clear()
        self._refresh_results()

    def open_dialog(self) -> int:
        self._requested_action = RECOVERY_ACTION_NONE
        self._search_input.setFocus()
        return self.exec_()

    def selected_entry(self) -> Optional[RecoveryCenterEntry]:
        item = self._results.currentItem()
        if item is None:
            return None
        key = item.data(0, Qt.UserRole)
        if not isinstance(key, str):
            return None
        return self._entries_by_key.get(key)

    def _refresh_results(self) -> None:
        terms = [term for term in self._search_input.text().strip().lower().split() if term]
        self._results.clear()
        for entry in self._entries:
            if not self._matches_terms(entry, terms):
                continue
            item = QTreeWidgetItem(
                [
                    "Draft" if entry.kind == RECOVERY_ENTRY_KIND_DRAFT else "History",
                    entry.display_path,
                    entry.status,
                    entry.timestamp,
                    entry.label,
                ]
            )
            item.setData(0, Qt.UserRole, self._entry_key(entry))
            self._results.addTopLevelItem(item)
        if self._results.topLevelItemCount() > 0:
            self._results.setCurrentItem(self._results.topLevelItem(0))
        else:
            self._detail_label.setText("No recovery entries matched the current search.")
        self._refresh_button_states()

    def _matches_terms(self, entry: RecoveryCenterEntry, terms: list[str]) -> bool:
        if not terms:
            return True
        haystack = " ".join(
            [entry.kind, entry.file_path, entry.display_path, entry.status, entry.timestamp, entry.label]
        ).lower()
        return all(term in haystack for term in terms)

    def _handle_selection_changed(self) -> None:
        entry = self.selected_entry()
        if entry is None:
            self._detail_label.setText("Select an entry to review or restore.")
        elif entry.kind == RECOVERY_ENTRY_KIND_DRAFT:
            self._detail_label.setText(
                f"Unsaved draft for {entry.file_path}\nReview compares the draft with the saved file before restoring."
            )
        else:
            self._detail_label.setText(
                f"Saved history timeline for {entry.file_path}\nOpen the timeline to compare revisions or restore the latest checkpoint."
            )
        self._refresh_button_states()

    def _refresh_button_states(self) -> None:
        entry = self.selected_entry()
        is_draft = entry is not None and entry.kind == RECOVERY_ENTRY_KIND_DRAFT
        is_history = entry is not None and entry.kind == RECOVERY_ENTRY_KIND_HISTORY
        self._review_draft_button.setEnabled(is_draft)
        self._open_timeline_button.setEnabled(is_history)
        self._restore_latest_button.setEnabled(is_history)

    def _handle_item_double_clicked(self, _item: QTreeWidgetItem, _column: int) -> None:
        entry = self.selected_entry()
        if entry is None:
            return
        if entry.kind == RECOVERY_ENTRY_KIND_DRAFT:
            self._handle_review_draft()
        else:
            self._handle_open_timeline()

    def _handle_review_draft(self) -> None:
        if self.selected_entry() is None:
            return
        self._requested_action = RECOVERY_ACTION_REVIEW_DRAFT
        self.accept()

    def _handle_open_timeline(self) -> None:
        if self.selected_entry() is None:
            return
        self._requested_action = RECOVERY_ACTION_OPEN_TIMELINE
        self.accept()

    def _handle_restore_latest(self) -> None:
        if self.selected_entry() is None:
            return
        self._requested_action = RECOVERY_ACTION_RESTORE_LATEST
        self.accept()

    def _entry_key(self, entry: RecoveryCenterEntry) -> str:
        return f"{entry.kind}:{entry.file_key}:{entry.file_path}"
