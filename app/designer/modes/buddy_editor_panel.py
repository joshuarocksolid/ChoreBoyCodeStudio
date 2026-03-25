"""Buddy-assignment editing panel for designer mode."""

from __future__ import annotations

from collections.abc import Sequence

from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import (
    QComboBox,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class BuddyEditorPanel(QWidget):
    """Assign label buddies through a table UI."""

    buddy_assignment_changed = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._is_populating = False
        self._summary_label = QLabel("No label buddy assignments available.", self)
        self._table = QTableWidget(0, 2, self)
        self._table.setObjectName("designer.buddy.table")
        self._table.setHorizontalHeaderLabels(["Label", "Buddy"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self._summary_label, 0)
        layout.addWidget(self._table, 1)

    def bind_buddy_rows(
        self,
        rows: Sequence[tuple[str, str]],
        buddy_candidates: Sequence[str],
    ) -> None:
        self._is_populating = True
        try:
            self._table.setRowCount(len(rows))
            for row_index, (label_name, current_buddy) in enumerate(rows):
                label_item = QTableWidgetItem(label_name)
                label_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self._table.setItem(row_index, 0, label_item)

                combo = QComboBox(self._table)
                combo.addItem("(none)", "")
                for candidate in buddy_candidates:
                    if candidate == label_name:
                        continue
                    combo.addItem(candidate, candidate)
                combo_index = combo.findData(current_buddy)
                if combo_index >= 0:
                    combo.setCurrentIndex(combo_index)
                combo.currentIndexChanged.connect(
                    lambda _idx, source=label_name, editor=combo: self._emit_assignment(source, editor)
                )
                self._table.setCellWidget(row_index, 1, combo)
        finally:
            self._is_populating = False
        self._refresh_summary()

    def _emit_assignment(self, label_object_name: str, combo: QComboBox) -> None:
        if self._is_populating:
            return
        buddy_name = str(combo.currentData() or "")
        self.buddy_assignment_changed.emit(label_object_name, buddy_name)

    def _refresh_summary(self) -> None:
        count = self._table.rowCount()
        if count == 0:
            self._summary_label.setText("No label buddy assignments available.")
            return
        self._summary_label.setText(f"{count} label(s) available for buddy assignment")
