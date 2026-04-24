"""Quick "Go to Symbol in File" dialog (Sublime/VSCode-style).

Lightweight `QDialog` showing a flat list of symbols from the active file. The
user types to filter by substring (case-insensitive), Enter commits, and
Escape cancels. While typing, a ``preview`` signal fires so the host can
scroll the editor to the candidate without committing the cursor jump.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

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

from app.intelligence.outline_service import OutlineSymbol


_LINE_NUMBER_ROLE = Qt.UserRole + 1
_QUALIFIED_NAME_ROLE = Qt.UserRole + 2


class QuickSymbolDialog(QDialog):
    """Filterable list of symbols for the active editor."""

    symbol_chosen: Any = Signal(int)
    symbol_preview: Any = Signal(int)

    def __init__(
        self, symbols: Iterable[OutlineSymbol], parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("shell.quickSymbolDialog")
        self.setWindowTitle("Go to Symbol in File")
        self.setModal(True)
        self.resize(420, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._line_edit = QLineEdit(self)
        self._line_edit.setObjectName("shell.quickSymbolDialog.input")
        self._line_edit.setPlaceholderText("Type a symbol name...")
        self._line_edit.textChanged.connect(self._on_filter_changed)
        self._line_edit.installEventFilter(self)
        layout.addWidget(self._line_edit)

        self._list = QListWidget(self)
        self._list.setObjectName("shell.quickSymbolDialog.list")
        self._list.setSelectionMode(QListWidget.SingleSelection)
        self._list.itemActivated.connect(self._commit_item)
        self._list.currentItemChanged.connect(self._on_current_changed)
        layout.addWidget(self._list, 1)

        self._symbols: tuple[OutlineSymbol, ...] = tuple(symbols)
        self._populate(self._symbols)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)
        self._line_edit.setFocus()

    # -- public API --

    def symbol_count(self) -> int:
        return self._list.count()

    def visible_count(self) -> int:
        visible = 0
        for index in range(self._list.count()):
            if not self._list.item(index).isHidden():
                visible += 1
        return visible

    def list_widget(self) -> QListWidget:
        return self._list

    def line_edit(self) -> QLineEdit:
        return self._line_edit

    # -- filter / population --

    def _populate(self, symbols: Iterable[OutlineSymbol]) -> None:
        self._list.clear()
        for symbol in symbols:
            label = symbol.name
            if symbol.detail:
                label = f"{symbol.name}  {symbol.detail}"
            label = f"{label}    Ln {symbol.line_number}"
            item = QListWidgetItem(label, self._list)
            item.setData(_LINE_NUMBER_ROLE, symbol.line_number)
            item.setData(_QUALIFIED_NAME_ROLE, symbol.qualified_name)
            item.setToolTip(symbol.qualified_name)

    def _on_filter_changed(self, text: str) -> None:
        needle = text.strip().lower()
        first_visible_row = -1
        for index in range(self._list.count()):
            item = self._list.item(index)
            qualified = (item.data(_QUALIFIED_NAME_ROLE) or "").lower()
            label = item.text().lower()
            visible = needle in qualified or needle in label
            item.setHidden(not visible)
            if visible and first_visible_row == -1:
                first_visible_row = index
        if first_visible_row >= 0:
            self._list.setCurrentRow(first_visible_row)
        else:
            self._list.setCurrentRow(-1)

    # -- selection / activation --

    def _on_current_changed(
        self, current: Optional[QListWidgetItem], _previous: Optional[QListWidgetItem]
    ) -> None:
        if current is None:
            return
        line_number = current.data(_LINE_NUMBER_ROLE)
        if line_number is None:
            return
        try:
            self.symbol_preview.emit(int(line_number))
        except (TypeError, ValueError):
            return

    def _commit_item(self, item: QListWidgetItem) -> None:
        line_number = item.data(_LINE_NUMBER_ROLE)
        if line_number is None:
            return
        try:
            resolved = int(line_number)
        except (TypeError, ValueError):
            return
        self.symbol_chosen.emit(resolved)
        self.accept()

    def commit_current(self) -> None:
        item = self._list.currentItem()
        if item is None or item.isHidden():
            return
        self._commit_item(item)

    # -- keyboard handling --

    def eventFilter(self, arg__1: Any, arg__2: Any) -> bool:  # noqa: N802, N803
        if arg__1 is self._line_edit and isinstance(arg__2, QKeyEvent) and arg__2.type() == QKeyEvent.KeyPress:
            key = arg__2.key()
            if key in (Qt.Key_Down, Qt.Key_Up, Qt.Key_PageDown, Qt.Key_PageUp):
                self._list.keyPressEvent(arg__2)
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self.commit_current()
                return True
        return super().eventFilter(arg__1, arg__2)

    def keyPressEvent(self, arg__1: Any) -> None:  # noqa: N802, N803
        if arg__1.key() == Qt.Key_Escape:
            self.reject()
            return
        if arg__1.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.commit_current()
            return
        super().keyPressEvent(arg__1)
