"""Simple signals/slots connection list panel."""

from __future__ import annotations

from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.designer.model import ConnectionModel


class ConnectionEditorPanel(QWidget):
    """List connections and expose add/remove actions."""

    add_requested = Signal()
    remove_requested = Signal(int)
    connection_edited = Signal(int, str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._connections: list[ConnectionModel] = []
        self._is_populating = False
        self._summary_label = QLabel("No signal/slot connections.", self)
        self._table = QTableWidget(0, 4, self)
        self._table.setObjectName("designer.connections.table")
        self._table.setHorizontalHeaderLabels(["Sender", "Signal", "Receiver", "Slot"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
        self._table.itemChanged.connect(self._handle_item_changed)

        self._add_button = QPushButton("Add Default Connection", self)
        self._add_button.clicked.connect(self.add_requested.emit)
        self._remove_button = QPushButton("Remove Selected", self)
        self._remove_button.clicked.connect(self._emit_remove_selected)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(6)
        button_row.addWidget(self._add_button, 0)
        button_row.addWidget(self._remove_button, 0)
        button_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self._summary_label, 0)
        layout.addWidget(self._table, 1)
        layout.addLayout(button_row, 0)
        self._refresh_summary()

    def bind_connections(self, connections: list[ConnectionModel]) -> None:
        self._is_populating = True
        self._connections = list(connections)
        self._table.setRowCount(len(self._connections))
        for row, connection in enumerate(self._connections):
            self._set_table_item(row, 0, connection.sender)
            self._set_table_item(row, 1, connection.signal)
            self._set_table_item(row, 2, connection.receiver)
            self._set_table_item(row, 3, connection.slot)
        self._is_populating = False
        self._refresh_summary()

    def _set_table_item(self, row: int, col: int, value: str) -> None:
        item = QTableWidgetItem(value)
        item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable)
        self._table.setItem(row, col, item)

    def _refresh_summary(self) -> None:
        count = len(self._connections)
        if count == 0:
            self._summary_label.setText("No signal/slot connections.")
            self._remove_button.setEnabled(False)
            return
        self._summary_label.setText(f"{count} connection(s)")
        self._remove_button.setEnabled(True)

    def _emit_remove_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._connections):
            return
        self.remove_requested.emit(row)

    def _handle_item_changed(self, item: QTableWidgetItem) -> None:
        if self._is_populating:
            return
        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self._connections):
            return
        column_names = {
            0: "sender",
            1: "signal",
            2: "receiver",
            3: "slot",
        }
        field_name = column_names.get(col)
        if field_name is None:
            return
        self.connection_edited.emit(row, field_name, item.text())
