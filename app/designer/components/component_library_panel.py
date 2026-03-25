"""Component library panel for browsing reusable designer components."""

from __future__ import annotations

from PySide2.QtCore import Signal
from PySide2.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ComponentLibraryPanel(QWidget):
    """Simple component browser with insert and refresh actions."""

    insert_requested = Signal(str)
    refresh_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("designer.components.panel")
        self._summary_label = QLabel("No reusable components.", self)
        self._summary_label.setObjectName("designer.components.summary")
        self._list = QListWidget(self)
        self._list.setObjectName("designer.components.list")
        self._list.itemDoubleClicked.connect(lambda item: self.insert_requested.emit(item.text()))

        self._insert_button = QPushButton("Insert Selected", self)
        self._insert_button.setObjectName("designer.components.btn.insert")
        self._insert_button.clicked.connect(self._emit_insert_selected)
        self._refresh_button = QPushButton("Refresh", self)
        self._refresh_button.setObjectName("designer.components.btn.refresh")
        self._refresh_button.clicked.connect(self.refresh_requested.emit)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(6)
        button_row.addWidget(self._insert_button, 0)
        button_row.addWidget(self._refresh_button, 0)
        button_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self._summary_label, 0)
        layout.addWidget(self._list, 1)
        layout.addLayout(button_row, 0)

    def bind_components(self, component_names: list[str]) -> None:
        self._list.clear()
        self._list.addItems(component_names)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)
        self._refresh_summary()

    def _emit_insert_selected(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        self.insert_requested.emit(item.text())

    def _refresh_summary(self) -> None:
        count = self._list.count()
        if count == 0:
            self._summary_label.setText("No reusable components.")
            self._insert_button.setEnabled(False)
            return
        self._summary_label.setText(f"{count} reusable component(s)")
        self._insert_button.setEnabled(True)
