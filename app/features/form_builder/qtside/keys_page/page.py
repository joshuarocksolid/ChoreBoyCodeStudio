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
from app.qt.QtWidgets import QHeaderView, QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget


#: Widest a Keys, Where or In Qt Designer column grows before its text is elided.
_MAX_SIDE_COLUMN = 200


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
        # "Where Designer's keys went" rows carry a sentence: the stretched "What it does"
        # column elides it (full text in the tooltip) instead of widening the page into a
        # sideways scroll. Wrapping instead cost ~15 ms a filter keystroke (budget 16).
        self.table.setUniformRowHeights(True)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        header = self.table.header()
        header.setStretchLastSection(False)
        for index in range(len(COLUMNS)):
            header.setSectionResizeMode(index, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
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
                item.setToolTip(1, row.what)
            head.setExpanded(True)
        for index in (0, 2, 3):
            self.table.resizeColumnToContents(index)
            self.table.setColumnWidth(index, min(self.table.columnWidth(index), _MAX_SIDE_COLUMN))

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
