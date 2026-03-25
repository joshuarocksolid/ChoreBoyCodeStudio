"""Searchable picker for global local-history restore flows."""

from __future__ import annotations

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

from app.persistence.history_models import LocalHistoryFileSummary

HISTORY_RESTORE_ACTION_NONE = ""
HISTORY_RESTORE_ACTION_OPEN_TIMELINE = "open_timeline"
HISTORY_RESTORE_ACTION_RESTORE_LATEST = "restore_latest"


class HistoryRestorePickerDialog(QDialog):
    """Search global local-history entries before restoring them."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._entries: list[LocalHistoryFileSummary] = []
        self._entries_by_file_key: dict[str, LocalHistoryFileSummary] = {}
        self._requested_action = HISTORY_RESTORE_ACTION_NONE

        self.setWindowTitle("Global History Restore")
        self.resize(980, 620)

        summary = QLabel(
            "Search saved local-history timelines across projects, including files that were moved, renamed, or deleted. Review a timeline before restoring, or restore the latest revision directly into a buffer."
        )
        summary.setWordWrap(True)

        search_input = QLineEdit(self)
        search_input.setPlaceholderText("Search by current path, old path, label, or project")
        search_input.textChanged.connect(self._refresh_results)
        self._search_input = search_input

        results = QTreeWidget(self)
        results.setHeaderLabels(["Path", "Status", "Latest", "Label"])
        results.setAlternatingRowColors(True)
        results.setUniformRowHeights(True)
        results.itemSelectionChanged.connect(self._handle_selection_changed)
        results.itemDoubleClicked.connect(self._handle_item_double_clicked)
        self._results = results

        detail_label = QLabel(
            "Select a history-backed file to inspect its timeline or restore the newest saved revision."
        )
        detail_label.setWordWrap(True)
        detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._detail_label = detail_label

        open_timeline_button = QPushButton("Open Timeline", self)
        restore_latest_button = QPushButton("Restore Latest to Buffer", self)
        close_button = QPushButton("Close", self)
        open_timeline_button.clicked.connect(self._handle_open_timeline)
        restore_latest_button.clicked.connect(self._handle_restore_latest)
        close_button.clicked.connect(self.reject)
        self._open_timeline_button = open_timeline_button
        self._restore_latest_button = restore_latest_button

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(close_button)
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
        """Return the action chosen when the dialog was accepted."""
        return self._requested_action

    def set_entries(self, entries: list[LocalHistoryFileSummary]) -> None:
        """Load global history entries into the picker."""
        self._entries = list(entries)
        self._entries_by_file_key = {entry.file_key: entry for entry in entries}
        self._requested_action = HISTORY_RESTORE_ACTION_NONE
        self._search_input.clear()
        self._refresh_results()

    def open_dialog(self) -> int:
        """Reset focus and run the picker modally."""
        self._requested_action = HISTORY_RESTORE_ACTION_NONE
        self._search_input.setFocus()
        return self.exec_()

    def selected_entry(self) -> Optional[LocalHistoryFileSummary]:
        """Return the currently selected entry, if any."""
        item = self._results.currentItem()
        if item is None:
            return None
        file_key = item.data(0, Qt.UserRole)
        if not isinstance(file_key, str):
            return None
        return self._entries_by_file_key.get(file_key)

    def _refresh_results(self) -> None:
        search_terms = [term for term in self._search_input.text().strip().lower().split() if term]
        self._results.clear()
        matched_entries = [entry for entry in self._entries if self._matches_terms(entry, search_terms)]

        for entry in matched_entries:
            label = entry.latest_label or entry.latest_source.replace("_", " ")
            item = QTreeWidgetItem(
                [
                    entry.display_path,
                    self._status_text(entry),
                    entry.latest_checkpoint_at,
                    label,
                ]
            )
            item.setData(0, Qt.UserRole, entry.file_key)
            self._results.addTopLevelItem(item)

        if self._results.topLevelItemCount() > 0:
            self._results.setCurrentItem(self._results.topLevelItem(0))
        else:
            self._detail_label.setText("No history entries matched the current search.")
        self._refresh_button_states()

    def _matches_terms(self, entry: LocalHistoryFileSummary, search_terms: list[str]) -> bool:
        if not search_terms:
            return True
        search_blob = " ".join(
            [
                entry.display_path,
                entry.relative_path,
                entry.file_path,
                entry.latest_label,
                entry.latest_source,
                entry.project_root or "",
                " ".join(entry.path_aliases),
            ]
        ).lower()
        return all(term in search_blob for term in search_terms)

    def _status_text(self, entry: LocalHistoryFileSummary) -> str:
        if entry.is_deleted:
            return "Deleted"
        if len(entry.path_aliases) > 2:
            return "Moved/Renamed"
        return "Available"

    def _handle_selection_changed(self) -> None:
        entry = self.selected_entry()
        if entry is None:
            self._detail_label.setText("Select a history-backed file to inspect or restore.")
            self._refresh_button_states()
            return

        alias_candidates = [
            alias
            for alias in entry.path_aliases
            if alias not in {entry.display_path, entry.relative_path, entry.file_path}
        ]
        detail_lines = [
            "Current or last known path: {path}".format(path=entry.file_path),
            "Project root: {root}".format(root=entry.project_root or "Unknown / external"),
            "Saved revisions: {count}".format(count=entry.checkpoint_count),
        ]
        if alias_candidates:
            detail_lines.append("Known previous paths: {aliases}".format(aliases=", ".join(alias_candidates)))
        if entry.is_deleted:
            detail_lines.append("This file is currently deleted. Restore opens the saved content in a dirty buffer at the last known path.")
        self._detail_label.setText("\n".join(detail_lines))
        self._refresh_button_states()

    def _refresh_button_states(self) -> None:
        has_selection = self.selected_entry() is not None
        self._open_timeline_button.setEnabled(has_selection)
        self._restore_latest_button.setEnabled(has_selection)

    def _handle_item_double_clicked(self, _item: QTreeWidgetItem, _column: int) -> None:
        self._handle_open_timeline()

    def _handle_open_timeline(self) -> None:
        if self.selected_entry() is None:
            return
        self._requested_action = HISTORY_RESTORE_ACTION_OPEN_TIMELINE
        self.accept()

    def _handle_restore_latest(self) -> None:
        if self.selected_entry() is None:
            return
        self._requested_action = HISTORY_RESTORE_ACTION_RESTORE_LATEST
        self.accept()
