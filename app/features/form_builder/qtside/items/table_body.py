"""Table cells, rows and columns (UX-ITEM-005)."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Tuple

from app.features.form_builder.qtside.items.model import (
    Draft,
    add_header,
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
from app.qt.QtWidgets import QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from app.features.form_builder.qtside.items.editor import ItemEditor


class TableBody(QWidget):
    def __init__(self, editor: "ItemEditor") -> None:
        super().__init__(editor)
        self._editor = editor
        tabs = QTabWidget(self)
        self._cells = _Cells(editor, self)
        self._rows = _Axis(editor, "row", self)
        self._columns = _Axis(editor, "column", self)
        tabs.addTab(self._cells, "Cells")
        tabs.addTab(self._rows, "Rows")
        tabs.addTab(self._columns, "Columns")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(tabs)

    def focus_first(self) -> None:
        self._cells.focus_first()

    def trimmed(self, draft: Draft) -> Draft:
        return draft


class _Cells(QWidget):
    def __init__(self, editor: "ItemEditor", parent: QWidget) -> None:
        super().__init__(parent)
        self._editor = editor
        self._grid = QTableWidget(self)
        self._grid.setObjectName("formBuilder.itemCells")
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
        text = event.text()  # type: ignore[attr-defined]
        if text and not ctrl and key not in (getattr(Qt, "Key_Return"), getattr(Qt, "Key_Enter"), getattr(Qt, "Key_Tab")):
            row = self._cells._grid.currentRow()
            column = self._cells._grid.currentColumn()
            if row >= 0 and column >= 0 and self._cells._grid.state() != getattr(QTableWidget, "EditingState", None):
                self._cells._editor.replace(set_cell_text(self._cells._editor.draft, row, column, text))
                self._cells.fill()
                self._cells._grid.setCurrentCell(row, column)
                return True
        return False


class _Axis(QWidget):
    def __init__(self, editor: "ItemEditor", axis: str, parent: QWidget) -> None:
        super().__init__(parent)
        self._editor = editor
        self._axis = axis
        self._list = ListEditor(name=axis, parent=self)
        self._list.set_on_texts(self._texts)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._list)
        self._fill()

    def _fill(self) -> None:
        slot = self._editor.draft.rows if self._axis == "row" else self._editor.draft.columns
        self._list.set_texts(tuple(item.text_at(0) for item in slot))

    def _texts(self, texts: Tuple[str, ...]) -> None:
        draft = self._editor.draft
        for index, text in enumerate(texts):
            draft = set_header_text(draft, self._axis, index, text)
        while len(_slot(draft, self._axis)) > len(texts):
            draft = delete_header(draft, self._axis, len(_slot(draft, self._axis)) - 1)
        self._editor.replace(draft)


def _slot(draft: Draft, axis: str) -> Tuple[object, ...]:
    return draft.rows if axis == "row" else draft.columns


def _int(item: object, name: str) -> int:
    for key, value in getattr(item, "fields", ()):
        if key == name and isinstance(value, int) and not isinstance(value, bool):
            return value
    return -1


_ = (move_header, List, Optional)
