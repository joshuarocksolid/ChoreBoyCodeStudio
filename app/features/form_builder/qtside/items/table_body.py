"""Table cells, rows and columns (UX-ITEM-005)."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Tuple

from app.features.form_builder.qtside.items.model import (
    Draft,
    Origin,
    add_header,
    headers_from_list,
    clear_cell,
    delete_header,
    move_header,
    paste_cells,
    set_cell_text,
    set_header_text,
)
from app.features.form_builder.qtside.inspector.editors._list_editor import ListEditor
from app.qt.QtCore import QEvent, QObject, Qt
from app.qt.QtGui import QGuiApplication
from app.qt.QtWidgets import QAbstractItemView, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from app.features.form_builder.qtside.items.editor import ItemEditor


class TableBody(QWidget):
    def __init__(self, editor: "ItemEditor") -> None:
        super().__init__(editor)
        self._editor = editor
        self._before = (len(editor.draft.rows), len(editor.draft.columns))
        tabs = QTabWidget(self)
        self._cells = _Cells(editor, self)
        self._rows = _Axis(editor, "row", self)
        self._columns = _Axis(editor, "column", self)
        tabs.addTab(self._cells, "Cells")
        tabs.addTab(self._rows, "Rows")
        tabs.addTab(self._columns, "Columns")
        # Each tab shows the draft as it is now: a paste in Cells can add rows.
        tabs.currentChanged.connect(self._refresh)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(tabs)

    def focus_first(self) -> None:
        self._cells.focus_first()

    def _refresh(self, _index: int) -> None:
        self._cells.fill()
        self._rows.refresh()
        self._columns.refresh()

    def trimmed(self, draft: Draft) -> Draft:
        """Drop the empty row and column opening an empty table added."""
        for axis, before in (("row", self._before[0]), ("column", self._before[1])):
            while True:
                slot = draft.rows if axis == "row" else draft.columns
                last = len(slot) - 1
                if last < before or slot[last].text_at(0) or any(_int(cell, axis) == last for cell in draft.cells):
                    break
                draft = delete_header(draft, axis, last)
        return draft


class _Cells(QWidget):
    def __init__(self, editor: "ItemEditor", parent: QWidget) -> None:
        super().__init__(parent)
        self._editor = editor
        self._grid = QTableWidget(self)
        self._grid.setObjectName("formBuilder.itemCells")
        # Typing replaces the cell's text; F2 and double-click keep it (UX-ITEM-005).
        triggers = QAbstractItemView.EditTrigger
        self._grid.setEditTriggers(triggers.AnyKeyPressed | triggers.EditKeyPressed | triggers.DoubleClicked)
        self._filling = False
        self._grid.cellChanged.connect(self._changed)
        self._filter = _GridKeys(self)
        self._grid.installEventFilter(self._filter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._grid)
        self.fill()

    def focus_first(self) -> None:
        if self._grid.rowCount() == 0:
            self._editor.replace(add_header(self._editor.draft, "row", -1))
        if self._grid.columnCount() == 0:
            self._editor.replace(add_header(self._editor.draft, "column", -1))
        self.fill()
        self._grid.setCurrentCell(0, 0)
        self._grid.setFocus()

    def fill(self) -> None:
        draft = self._editor.draft
        self._filling = True
        self._grid.setRowCount(max(1, len(draft.rows)) if draft.rows or draft.cells else max(len(draft.rows), 1))
        self._grid.setColumnCount(max(1, len(draft.columns)) if draft.columns or draft.cells else max(len(draft.columns), 1))
        rows = max(len(draft.rows), 1)
        cols = max(len(draft.columns), 1)
        for cell in draft.cells:
            row = _int(cell, "row")
            column = _int(cell, "column")
            rows = max(rows, row + 1)
            cols = max(cols, column + 1)
        self._grid.setRowCount(rows)
        self._grid.setColumnCount(cols)
        labels = [item.text_at(0) or str(index + 1) for index, item in enumerate(draft.columns)]
        if labels:
            self._grid.setHorizontalHeaderLabels(labels)
        self._grid.clearContents()
        for cell in draft.cells:
            row = _int(cell, "row")
            column = _int(cell, "column")
            if row < 0 or column < 0:
                continue
            self._grid.setItem(row, column, QTableWidgetItem(cell.text_at(0)))
        self._filling = False

    def _changed(self, row: int, column: int) -> None:
        if self._filling:
            return
        item = self._grid.item(row, column)
        text = "" if item is None else item.text()
        self._editor.replace(set_cell_text(self._editor.draft, row, column, text))

    def paste(self) -> None:
        app = QGuiApplication.clipboard() if QGuiApplication.instance() is not None else None
        if app is None:
            return
        raw = app.text()
        grid = [line.split("\t") for line in raw.splitlines()]
        if not grid:
            return
        row = max(self._grid.currentRow(), 0)
        column = max(self._grid.currentColumn(), 0)
        self._editor.replace(paste_cells(self._editor.draft, row, column, grid))
        self.fill()

    def clear_current(self) -> None:
        row = self._grid.currentRow()
        column = self._grid.currentColumn()
        if row < 0 or column < 0:
            return
        self._editor.replace(clear_cell(self._editor.draft, row, column))
        self.fill()


class _GridKeys(QObject):
    def __init__(self, cells: _Cells) -> None:
        super().__init__(cells)
        self._cells = cells

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        press = getattr(getattr(QEvent, "Type", QEvent), "KeyPress", QEvent.KeyPress)
        if event.type() != press:
            return False
        key = event.key()  # type: ignore[attr-defined]
        mods = event.modifiers()  # type: ignore[attr-defined]
        ctrl = bool(mods & getattr(Qt, "ControlModifier"))
        if key == getattr(Qt, "Key_Delete") and not ctrl:
            self._cells.clear_current()
            return True
        if key == getattr(Qt, "Key_V") and ctrl:
            self._cells.paste()
            return True
        grid = self._cells._grid
        editing = grid.state() == getattr(QAbstractItemView.State, "EditingState")
        if key in (getattr(Qt, "Key_Return"), getattr(Qt, "Key_Enter")) and not editing:
            # Enter edits the cell keeping its text, like F2 (UX-ITEM-005).
            item = grid.currentItem()
            if item is None and grid.currentRow() >= 0 and grid.currentColumn() >= 0:
                item = QTableWidgetItem("")
                self._cells._filling = True
                grid.setItem(grid.currentRow(), grid.currentColumn(), item)
                self._cells._filling = False
            if item is not None:
                grid.editItem(item)
                return True
        return False


class _Axis(QWidget):
    def __init__(self, editor: "ItemEditor", axis: str, parent: QWidget) -> None:
        super().__init__(parent)
        self._editor = editor
        self._axis = axis
        self._list = ListEditor(name=axis, parent=self)
        self._list.set_on_rows(self._rows)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._list)
        self._fill()

    def _fill(self) -> None:
        slot = self._editor.draft.rows if self._axis == "row" else self._editor.draft.columns
        self._list.set_texts(tuple(item.text_at(0) for item in slot))

    def refresh(self) -> None:
        self._fill()

    def _rows(self, texts: Tuple[str, ...], origin: Origin) -> None:
        self._editor.replace(headers_from_list(self._editor.draft, self._axis, texts, origin))


def _slot(draft: Draft, axis: str) -> Tuple[object, ...]:
    return draft.rows if axis == "row" else draft.columns


def _int(item: object, name: str) -> int:
    for key, value in getattr(item, "fields", ()):
        if key == name and isinstance(value, int) and not isinstance(value, bool):
            return value
    return -1


_ = (move_header, List, Optional)
