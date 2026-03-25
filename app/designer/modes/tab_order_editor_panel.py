"""Tab-order editing panel for designer mode."""

from __future__ import annotations

from PySide2.QtCore import Signal
from PySide2.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class TabOrderEditorPanel(QWidget):
    """Shows focus chain order and allows reordering."""

    tab_order_changed = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("designer.tabOrder.panel")
        self._summary_label = QLabel("No tab stops configured.", self)
        self._summary_label.setObjectName("designer.tabOrder.summary")
        self._list = QListWidget(self)
        self._list.setObjectName("designer.tabOrder.list")

        self._move_up_button = QPushButton("Move Up", self)
        self._move_up_button.setObjectName("designer.tabOrder.btn.moveUp")
        self._move_up_button.clicked.connect(self._move_selected_up)
        self._move_down_button = QPushButton("Move Down", self)
        self._move_down_button.setObjectName("designer.tabOrder.btn.moveDown")
        self._move_down_button.clicked.connect(self._move_selected_down)
        self._reset_button = QPushButton("Reset to Traversal Order", self)
        self._reset_button.setObjectName("designer.tabOrder.btn.reset")
        self._reset_button.clicked.connect(self._emit_current_order)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(6)
        button_row.addWidget(self._move_up_button, 0)
        button_row.addWidget(self._move_down_button, 0)
        button_row.addWidget(self._reset_button, 0)
        button_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self._summary_label, 0)
        layout.addWidget(self._list, 1)
        layout.addLayout(button_row, 0)
        self._refresh_summary()

    def bind_tab_order(self, ordered_object_names: list[str]) -> None:
        self._list.clear()
        for object_name in ordered_object_names:
            self._list.addItem(QListWidgetItem(object_name))
        if self._list.count() > 0:
            self._list.setCurrentRow(0)
        self._refresh_summary()

    def current_order(self) -> list[str]:
        return [self._list.item(index).text() for index in range(self._list.count())]

    def _move_selected_up(self) -> None:
        row = self._list.currentRow()
        if row <= 0:
            return
        item = self._list.takeItem(row)
        self._list.insertItem(row - 1, item)
        self._list.setCurrentRow(row - 1)
        self._emit_current_order()

    def _move_selected_down(self) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= self._list.count() - 1:
            return
        item = self._list.takeItem(row)
        self._list.insertItem(row + 1, item)
        self._list.setCurrentRow(row + 1)
        self._emit_current_order()

    def _emit_current_order(self) -> None:
        self._refresh_summary()
        self.tab_order_changed.emit(self.current_order())

    def _refresh_summary(self) -> None:
        count = self._list.count()
        if count == 0:
            self._summary_label.setText("No tab stops configured.")
            self._move_up_button.setEnabled(False)
            self._move_down_button.setEnabled(False)
            self._reset_button.setEnabled(False)
            return
        self._summary_label.setText(f"{count} tab stop(s)")
        self._move_up_button.setEnabled(True)
        self._move_down_button.setEnabled(True)
        self._reset_button.setEnabled(True)
