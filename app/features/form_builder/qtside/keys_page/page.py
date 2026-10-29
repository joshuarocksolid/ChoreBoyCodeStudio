"""Form designer keys: a filter field and the table of UX-MODE-005. The model is ``model.py``."""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from app.features.form_builder.qtside.keys_page.model import (
    COLUMNS,
    SEARCH_PLACEHOLDER,
    TITLE,
    KeyGroup,
    KeyRow,
    filter_groups,
)
from app.qt.QtCore import Qt
from app.qt.QtGui import QKeyEvent
from app.qt.QtWidgets import QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget


class KeysPage(QWidget):
    """The filter has focus when the page opens. Down moves to the table, Esc clears the filter, then closes."""

    def __init__(self, groups: Sequence[KeyGroup], parent: Optional[QWidget] = None, on_close: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.keysPage")
        self.setAccessibleName(TITLE)
        self._groups = tuple(groups)
        self._on_close = on_close
        self.filter = QLineEdit(self)
        self.filter.setObjectName("formBuilder.keysFilter")
        self.filter.setPlaceholderText(SEARCH_PLACEHOLDER)
        self.filter.setAccessibleName(SEARCH_PLACEHOLDER)
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._refill)
        self.table = QTreeWidget(self)
        self.table.setObjectName("formBuilder.keysTable")
        self.table.setAccessibleName(TITLE)
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHeaderLabels(list(COLUMNS))
        self.table.setRootIsDecorated(False)
        self.table.setUniformRowHeights(True)
        self.table.setAlternatingRowColors(False)
        column = QVBoxLayout(self)
        column.setContentsMargins(12, 12, 12, 12)
        column.setSpacing(8)
        column.addWidget(self.filter)
        column.addWidget(self.table, 1)
        self.setFocusProxy(self.filter)
        self._refill()

    def focus_filter(self) -> None:
        self.filter.setFocus()
        self.filter.selectAll()

    def visible_rows(self) -> Sequence[KeyRow]:
        return tuple(row for group in filter_groups(self._groups, self.filter.text()) for row in group.rows)

    def first_row_keys(self) -> str:
        rows = self.visible_rows()
        return rows[0].keys if rows else ""

    def _refill(self) -> None:
        self.table.clear()
        for group in filter_groups(self._groups, self.filter.text()):
            head = QTreeWidgetItem(self.table, [group.title])
            font = head.font(0)
            font.setBold(True)
            head.setFont(0, font)
            head.setFirstColumnSpanned(True)
            head.setFlags(Qt.ItemFlag.ItemIsEnabled)
            for row in group.rows:
                item = QTreeWidgetItem(head, [row.keys, row.what, row.where, row.designer])
                item.setData(0, Qt.ItemDataRole.UserRole, row.command_id)
            head.setExpanded(True)
        for index in range(len(COLUMNS)):
            self.table.resizeColumnToContents(index)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            if self.filter.text():
                self.filter.clear()
            elif self._on_close is not None:
                self._on_close()
            return
        if event.key() == Qt.Key.Key_Down and self.filter.hasFocus():
            first = self.table.topLevelItem(0)
            if first is not None and first.childCount():
                self.table.setFocus()
                self.table.setCurrentItem(first.child(0))
            return
        super().keyPressEvent(event)
