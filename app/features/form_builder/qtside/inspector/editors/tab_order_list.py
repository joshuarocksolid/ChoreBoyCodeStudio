"""The form inspector's Tab order list (UX-OVL-006, UX-MODE-003, UX-EMPTY-007).

Numbered rows "1 · nameEdit · Line edit". Drag a row, or press Alt+Up and
Alt+Down, to move it; Enter selects the widget on the canvas; "Use reading
order" deletes the form's ``<tabstops>``. The Form inspector builds one of
these in place of the plain text list it had before M5.6.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from app.features.form_builder.engine.commands.catalog_ext.tab_order import ChangeTabOrder
from app.features.form_builder.engine.query import tab_stops as q
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.qtside.canvas.banner import EnterButton
from app.features.form_builder.qtside.inspector.api import GroupBody, GroupHost, Registrar, Row
from app.features.form_builder.qtside.inspector.words import class_words
from app.qt.QtCore import QModelIndex, Qt
from app.qt.QtGui import QKeyEvent
from app.qt.QtWidgets import QAbstractItemView, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

FOLLOWS = "Follows reading order: top to bottom, left to right."
CUSTOM = "Custom order. New fields join it where they sit on the form."
EMPTY = "No fields to visit yet. Inputs join the order as you add them."
USE_READING = "Use reading order"


def row_text(number: int, name: str, qt_class: str) -> str:
    return "%d · %s · %s" % (number, name, class_words(qt_class).friendly)


class _List(QListWidget):
    """Alt+Up and Alt+Down move the current row; Enter selects its widget."""

    def __init__(self, body: "TabOrderBody") -> None:
        super().__init__(body.widget)
        self._body = body

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        if alt and key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            self._body.move_current(-1 if key == Qt.Key.Key_Up else 1)
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._body.select_current()
            return
        super().keyPressEvent(event)


class TabOrderBody:
    """Works as a form-group body: ``show(())`` repaints it from the document."""

    def __init__(self, host: GroupHost, parent: QWidget) -> None:
        self._host = host
        self._root = QWidget(parent)
        self._root.setObjectName("formBuilder.tabOrderList")
        column = QVBoxLayout(self._root)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        self._caption = QLabel(self._root)
        self._caption.setObjectName("formBuilder.tabOrderCaption")
        self._caption.setWordWrap(True)
        self._caption.setProperty("note", True)
        self._empty = QLabel(EMPTY, self._root)
        self._empty.setObjectName("formBuilder.tabOrderEmpty")
        self._empty.setWordWrap(True)
        self.list = _List(self)
        self.list.setObjectName("formBuilder.tabOrderRows")
        self.list.setAccessibleName("Tab order")
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.model().rowsMoved.connect(self._dropped)
        self.reset = EnterButton(USE_READING, self._root)
        self.reset.setObjectName("formBuilder.tabOrderReset")
        self.reset.setAccessibleName(USE_READING)
        self.reset.clicked.connect(self.use_reading_order)
        column.addWidget(self._caption)
        column.addWidget(self._empty)
        column.addWidget(self.list)
        column.addWidget(self.reset, 0, Qt.AlignmentFlag.AlignLeft)
        self._names: Tuple[str, ...] = ()
        self._painting = False

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, rows: Tuple[Row, ...]) -> None:
        del rows
        document = self._host.document
        stops = q.stops(document)
        names = tuple(stop.name for stop in stops)
        custom = document.tabstops() is not None
        self._caption.setText(CUSTOM if custom else FOLLOWS)
        self._empty.setVisible(not stops)
        self.list.setVisible(bool(stops))
        self.reset.setVisible(custom)
        if names == self._names and self.list.count() == len(names):
            return
        current = self.list.currentRow()
        self._painting = True
        self._names = names
        self.list.clear()
        for number, stop in enumerate(stops, 1):
            item = QListWidgetItem(row_text(number, stop.name, stop.qt_class))
            item.setData(Qt.ItemDataRole.UserRole, stop.name)
            self.list.addItem(item)
        self._painting = False
        if self.list.count():
            self.list.setCurrentRow(max(0, min(current, self.list.count() - 1)))
        self.list.setFixedHeight(self.list.sizeHintForRow(0) * self.list.count() + 6 if self.list.count() else 0)

    def names(self) -> Tuple[str, ...]:
        return self._names

    def _listed(self) -> List[str]:
        return [str(self.list.item(row).data(Qt.ItemDataRole.UserRole)) for row in range(self.list.count())]

    def _write(self, names: Tuple[str, ...], label: str = "Change tab order") -> None:
        if names == self._names:
            return
        self._host.run(label, [ChangeTabOrder(names)])

    def move_current(self, delta: int) -> None:
        row = self.list.currentRow()
        target = row + delta
        if row < 0 or not 0 <= target < len(self._names):
            return
        names = list(self._names)
        names.insert(target, names.pop(row))
        self._write(tuple(names))
        self.list.setCurrentRow(target)
        self.list.setFocus()

    def _dropped(self, *_args: object) -> None:
        if self._painting:
            return
        self._write(tuple(self._listed()))

    def select_current(self) -> None:
        item = self.list.currentItem()
        session = getattr(self._host, "session", None)
        if item is None or session is None:
            return
        found = self._host.document.by_name(str(item.data(Qt.ItemDataRole.UserRole)))
        if found:
            session.selection.set((found[0],), current=found[0], source=SelectionSource.INSPECTOR)

    def use_reading_order(self) -> None:
        self._host.run("Use reading order", [ChangeTabOrder(None)])

    def focus_list(self) -> None:
        target: Optional[QWidget] = self.list if self.list.isVisible() else self.reset if self.reset.isVisible() else None
        if target is not None:
            target.setFocus()
            if target is self.list and self.list.count() and self.list.currentRow() < 0:
                self.list.setCurrentRow(0)


def register(registrar: Registrar) -> None:
    del registrar
