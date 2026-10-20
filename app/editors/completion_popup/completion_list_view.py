"""List view used by the completion popup."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from PySide2.QtCore import QModelIndex, Qt, Signal
from PySide2.QtGui import QPaintEvent
from PySide2.QtWidgets import QAbstractItemView, QFrame, QListView

from app.editors.completion_popup.completion_item_delegate import CompletionItemDelegate
from app.editors.completion_popup.completion_item_model import ItemRole
from app.intelligence.completion_models import CompletionItem
from app.shell.theme_tokens import ShellThemeTokens

VISIBLE_ROWS = 10
PAGE_ROWS = 10


class CompletionListView(QListView):
    """List view with the row delegate and a current-item-changed signal."""

    current_item_changed: Any = Signal(object)

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFrameShape(QFrame.NoFrame)
        self._delegate = CompletionItemDelegate(self)
        self.setItemDelegate(self._delegate)
        self.last_paint_at = 0.0
        self._paint_probe: Optional[Tuple[Dict[str, Any], float]] = None

    def delegate(self) -> CompletionItemDelegate:
        return self._delegate

    def setModel(self, model: object) -> None:  # noqa: N802
        previous = self.selectionModel()
        if previous is not None:
            try:
                previous.currentRowChanged.disconnect(self._on_current_row_changed)
            except (RuntimeError, TypeError):
                pass
        super().setModel(model)
        selection_model = self.selectionModel()
        if selection_model is not None:
            selection_model.currentRowChanged.connect(self._on_current_row_changed)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._delegate.apply_theme(tokens)
        bg = tokens.popup_bg or tokens.panel_bg
        self.setStyleSheet(
            f"""
            QListView {{
                background-color: {bg};
                color: {tokens.text_primary};
                border: none;
                outline: 0;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {tokens.border};
                min-height: 24px;
                border-radius: 4px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            """
        )
        self.viewport().update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        super().paintEvent(event)
        self.last_paint_at = time.perf_counter()
        probe = self._paint_probe
        if probe is not None:
            self._paint_probe = None
            entry, started_at = probe
            entry["to_paint_ms"] = round((self.last_paint_at - started_at) * 1000.0, 3)

    def measure_next_paint(self, entry: Dict[str, Any], started_at: float) -> None:
        """Record in ``entry`` how long it took from ``started_at`` to the next paint."""

        self._paint_probe = (entry, started_at)

    def height_for_rows(self, rows: int) -> int:
        return self._delegate.row_height() * max(1, min(VISIBLE_ROWS, rows)) + 2 * self.frameWidth()

    def select_row(self, row: int) -> None:
        model = self.model()
        if model is None or model.rowCount() == 0:
            return
        row = max(0, min(row, model.rowCount() - 1))
        index = model.index(row, 0)
        if index == self.currentIndex():
            self._on_current_row_changed(index, QModelIndex())
        self.setCurrentIndex(index)
        self.scrollTo(index, QAbstractItemView.EnsureVisible)

    def move_selection(self, key: int) -> None:
        """Up/Down wrap around; PageUp/PageDown move ten rows and stop at the ends."""

        model = self.model()
        if model is None or model.rowCount() == 0:
            return
        count = model.rowCount()
        row = self.currentIndex().row() if self.currentIndex().isValid() else 0
        if key == Qt.Key_Down:
            row = (row + 1) % count
        elif key == Qt.Key_Up:
            row = (row - 1) % count
        elif key == Qt.Key_PageDown:
            row = min(count - 1, row + PAGE_ROWS)
        elif key == Qt.Key_PageUp:
            row = max(0, row - PAGE_ROWS)
        self.select_row(row)

    def current_item(self) -> CompletionItem | None:
        index = self.currentIndex()
        if not index.isValid():
            return None
        item = index.data(ItemRole)
        return item if isinstance(item, CompletionItem) else None

    def _on_current_row_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        item = current.data(ItemRole) if current.isValid() else None
        self.current_item_changed.emit(item if isinstance(item, CompletionItem) else None)
