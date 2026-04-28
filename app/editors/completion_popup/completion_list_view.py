"""List view used by the completion popup.

Thin wrapper around :class:`QListView` that:

* uses the custom :class:`CompletionItemDelegate` for row rendering;
* emits :pyattr:`current_item_changed` when the highlighted row changes; and
* applies a small style sheet derived from the active :class:`ShellThemeTokens`.
"""

from __future__ import annotations

from typing import Any

from PySide2.QtCore import QModelIndex, Qt, Signal
from PySide2.QtWidgets import QAbstractItemView, QFrame, QListView

from app.editors.completion_popup.completion_item_delegate import CompletionItemDelegate
from app.editors.completion_popup.completion_item_model import (
    CompletionItemModel,
    ItemRole,
)
from app.intelligence.completion_models import CompletionItem
from app.shell.theme_tokens import ShellThemeTokens


_VISIBLE_ROW_COUNT = 12
_MIN_WIDTH = 320
_WIDTH_PADDING = 24


class CompletionListView(QListView):
    """List view with custom delegate and a current-item-changed signal."""

    current_item_changed: Any = Signal(object)

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFrameShape(QFrame.NoFrame)
        self._delegate = CompletionItemDelegate(self)
        self.setItemDelegate(self._delegate)

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
        """Forward theme tokens to the delegate and restyle scrollbars."""
        self._delegate.apply_theme(tokens)
        bg = tokens.popup_bg or tokens.panel_bg or "#FFFFFF"
        text = tokens.text_primary or "#212529"
        scrollbar_handle = tokens.border or "#DEE2E6"
        scrollbar_hover = tokens.text_muted or "#6C757D"
        self.setStyleSheet(
            f"""
            QListView {{
                background-color: {bg};
                color: {text};
                border: none;
                outline: 0;
                padding: 4px 0;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {scrollbar_handle};
                min-height: 24px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {scrollbar_hover};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            """
        )
        self.viewport().update()

    def width_hint(self) -> int:
        """Return a width that fits the longest visible row."""
        column_hint = self.sizeHintForColumn(0) if self.model() is not None else 0
        return max(_MIN_WIDTH, column_hint + _WIDTH_PADDING)

    def height_hint(self) -> int:
        """Return a height that shows up to ``_VISIBLE_ROW_COUNT`` rows."""
        model = self.model()
        if model is None:
            return self._delegate.row_height() * 4
        rows = min(_VISIBLE_ROW_COUNT, max(1, model.rowCount()))
        return self._delegate.row_height() * rows + 8

    def select_first_row(self) -> None:
        model = self.model()
        if model is None or model.rowCount() == 0:
            return
        index = model.index(0, 0)
        self.setCurrentIndex(index)
        self._on_current_row_changed(index, QModelIndex())

    def current_item(self) -> CompletionItem | None:
        index = self.currentIndex()
        if not index.isValid():
            return None
        item = index.data(ItemRole)
        return item if isinstance(item, CompletionItem) else None

    def _on_current_row_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not current.isValid():
            self.current_item_changed.emit(None)
            return
        item = current.data(ItemRole)
        self.current_item_changed.emit(item if isinstance(item, CompletionItem) else None)
