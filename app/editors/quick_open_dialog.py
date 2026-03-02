"""Quick-open dialog overlay for fuzzy file-by-name search."""

from __future__ import annotations

from typing import Any

from PySide2.QtCore import Qt, Signal
from PySide2.QtGui import QKeyEvent
from PySide2.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.editors.quick_open import QuickOpenCandidate, rank_candidates


class QuickOpenDialog(QDialog):
    """Floating overlay for fuzzy file-by-name search (Ctrl+P)."""

    file_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.quickOpen")
        from PySide2.QtCore import Qt as _Qt
        self.setWindowFlags(_Qt.WindowType(int(_Qt.Popup) | int(_Qt.FramelessWindowHint)))
        self.setMinimumWidth(500)
        self.setMaximumHeight(400)
        self._candidates: list[QuickOpenCandidate] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._search_input = QLineEdit(self)
        self._search_input.setObjectName("shell.quickOpen.input")
        self._search_input.setPlaceholderText("Type a file name to open...")
        self._search_input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._search_input)

        self._results_list = QListWidget(self)
        self._results_list.setObjectName("shell.quickOpen.results")
        self._results_list.itemActivated.connect(self._on_item_activated)
        layout.addWidget(self._results_list, 1)

    def set_candidates(self, candidates: list[QuickOpenCandidate]) -> None:
        self._candidates = list(candidates)
        self._refresh_results()

    def open_dialog(self) -> None:
        self._search_input.clear()
        self._refresh_results()
        self._search_input.setFocus()
        if self.parent() is not None:
            parent_widget = self.parent()
            if hasattr(parent_widget, "rect"):
                parent_rect = parent_widget.rect()
                x = (parent_rect.width() - self.width()) // 2
                y = parent_rect.height() // 6
                global_pos = parent_widget.mapToGlobal(parent_rect.topLeft())  # type: ignore[union-attr]
                self.move(global_pos.x() + x, global_pos.y() + y)
        self.show()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.hide()
            event.accept()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._accept_current()
            event.accept()
            return
        if event.key() == Qt.Key_Down:
            row = self._results_list.currentRow()
            if row < self._results_list.count() - 1:
                self._results_list.setCurrentRow(row + 1)
            event.accept()
            return
        if event.key() == Qt.Key_Up:
            row = self._results_list.currentRow()
            if row > 0:
                self._results_list.setCurrentRow(row - 1)
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_text_changed(self, _text: str) -> None:
        self._refresh_results()

    def _refresh_results(self) -> None:
        self._results_list.clear()
        query = self._search_input.text()
        ranked = rank_candidates(self._candidates, query, limit=50)
        for candidate in ranked:
            item = QListWidgetItem(candidate.relative_path, self._results_list)
            item.setData(Qt.UserRole, candidate.absolute_path)
            item.setToolTip(candidate.absolute_path)
        if self._results_list.count() > 0:
            self._results_list.setCurrentRow(0)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        if path:
            self.file_selected.emit(str(path))
            self.hide()

    def _accept_current(self) -> None:
        current_item = self._results_list.currentItem()
        if current_item is not None:
            self._on_item_activated(current_item)
