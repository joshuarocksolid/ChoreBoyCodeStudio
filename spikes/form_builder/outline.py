"""Outline tree. It is also the keyboard editor."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLineEdit, QListWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from spikes.form_builder.canvas import content_for, item_for
from spikes.form_builder.catalog import CATALOG, fuzzy
from spikes.form_builder.commands import (
    Delete,
    InsertItem,
    MoveItem,
    Rename,
    delete_targets,
    nest_command,
    resolve_layout_item,
    unnest_command,
)
from spikes.form_builder.model import (
    Layout,
    Spacer,
    Widget,
    child_widgets,
    find_node,
    item_content,
    layout_items,
    locate,
    widget_layout,
)


class Outline(QTreeWidget):
    selection_made = Signal(list)

    def __init__(self):
        super().__init__()
        self.setHeaderLabels(["Object", "Class"])
        self.setColumnWidth(0, 170)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QTreeWidget.DragDrop)
        self.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.doc = None
        self.history = None
        self._quiet = False
        self.itemSelectionChanged.connect(self._emit_selection)
        self.itemChanged.connect(self._renamed)

    def set_document(self, doc, history):
        self.doc = doc
        self.history = history
        self.rebuild()

    def rebuild(self):
        selected = self.selected_ids()
        self._quiet = True
        self.clear()
        if self.doc is not None:
            self.addTopLevelItem(self._node_item(self.doc.root))
            self.expandAll()
        self._quiet = False
        if selected:
            self.select_ids(selected)

    def _node_item(self, node) -> QTreeWidgetItem:
        if isinstance(node, Widget):
            item = QTreeWidgetItem([node.object_name or node.class_name, node.class_name])
            item.setData(0, Qt.UserRole, node.id)
            item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)
            layout = widget_layout(node)
            if layout is not None:
                layout_item = QTreeWidgetItem([layout.object_name or layout.class_name, layout.class_name])
                layout_item.setData(0, Qt.UserRole, layout.id)
                layout_item.setFlags(layout_item.flags() | Qt.ItemIsDropEnabled)
                item.addChild(layout_item)
                for child in layout_items(layout):
                    content = item_content(child)
                    if content is not None:
                        layout_item.addChild(self._node_item(content))
            for child in child_widgets(node):
                item.addChild(self._node_item(child))
            return item
        if isinstance(node, Spacer):
            item = QTreeWidgetItem([node.name, "Spacer"])
            item.setData(0, Qt.UserRole, node.id)
            return item
        item = QTreeWidgetItem([getattr(node, "object_name", "") or getattr(node, "class_name", "?"), type(node).__name__])
        item.setData(0, Qt.UserRole, getattr(node, "id", ""))
        return item

    def selected_ids(self):
        return [item.data(0, Qt.UserRole) for item in self.selectedItems() if item.data(0, Qt.UserRole)]

    def select_ids(self, ids):
        self._quiet = True
        self.clearSelection()

        def walk(item):
            if item.data(0, Qt.UserRole) in ids:
                item.setSelected(True)
                self.setCurrentItem(item)
            for index in range(item.childCount()):
                walk(item.child(index))

        for index in range(self.topLevelItemCount()):
            walk(self.topLevelItem(index))
        self._quiet = False

    def _emit_selection(self):
        if not self._quiet:
            self.selection_made.emit(self.selected_ids())

    def _renamed(self, item, column):
        if self._quiet or column != 0 or self.history is None or self.doc is None:
            return
        node = find_node(self.doc, item.data(0, Qt.UserRole))
        if node is None:
            return
        current = node.object_name if isinstance(node, (Widget, Layout)) else getattr(node, "name", "")
        if item.text(0) != current:
            self.history.execute(Rename(item.data(0, Qt.UserRole), item.text(0)))

    def keyPressEvent(self, event):
        if self.doc is None or self.history is None:
            super().keyPressEvent(event)
            return
        ids = self.selected_ids()
        if event.key() == Qt.Key_F2 and self.currentItem() is not None:
            self.editItem(self.currentItem(), 0)
            return
        if event.text() == "/" and self.state() != QTreeWidget.EditingState:
            self.window().open_quick_insert()
            return
        if event.key() == Qt.Key_Delete and ids:
            self.history.execute(Delete(delete_targets(self.doc, ids)))
            return
        if event.key() == Qt.Key_Tab and not event.modifiers() & Qt.ShiftModifier and ids:
            command = nest_command(self.doc, ids[0])
            if command is not None:
                self.history.execute(command)
            return
        if event.key() in {Qt.Key_Backtab} or (event.key() == Qt.Key_Tab and event.modifiers() & Qt.ShiftModifier):
            if ids:
                command = unnest_command(self.doc, ids[0])
                if command is not None:
                    self.history.execute(command)
            return
        if event.key() in {Qt.Key_Up, Qt.Key_Down} and event.modifiers() & Qt.AltModifier and ids:
            self._reorder(ids[0], -1 if event.key() == Qt.Key_Up else 1)
            return
        super().keyPressEvent(event)

    def _reorder(self, node_id, delta):
        item = resolve_layout_item(self.doc, node_id)
        if item is None:
            return
        located = locate(self.doc, item.id)
        if located is None or not isinstance(located[0], Layout):
            return
        items = layout_items(located[0])
        index = items.index(item)
        target = index + delta
        if target < 0 or target >= len(items):
            return
        dest = target if delta < 0 else target + 1
        self.history.execute(MoveItem(item.id, located[0].id, dest))

    def dropEvent(self, event):
        if self.doc is None or self.history is None or self.currentItem() is None:
            event.ignore()
            return
        target = self.itemAt(event.position().toPoint())
        source_id = self.currentItem().data(0, Qt.UserRole)
        item = resolve_layout_item(self.doc, source_id)
        if item is None or target is None:
            event.ignore()
            return
        dest = find_node(self.doc, target.data(0, Qt.UserRole))
        if isinstance(dest, Layout):
            self.history.execute(MoveItem(item.id, dest.id, len(layout_items(dest))))
        elif isinstance(dest, Widget) and widget_layout(dest) is not None:
            layout = widget_layout(dest)
            self.history.execute(MoveItem(item.id, layout.id, len(layout_items(layout))))
        event.accept()

    def insert_entry(self, entry):
        if self.doc is None or self.history is None:
            return
        content = content_for(self.doc, entry)
        ids = self.selected_ids()
        if ids:
            node = find_node(self.doc, ids[0])
            if isinstance(node, Layout):
                self.history.execute(InsertItem(node.id, len(layout_items(node)), item_for(self.doc, content, {})))
                return
            if isinstance(node, Widget) and widget_layout(node) is not None:
                layout = widget_layout(node)
                self.history.execute(InsertItem(layout.id, len(layout_items(layout)), item_for(self.doc, content, {})))
                return
        layout = widget_layout(self.doc.root)
        if layout is not None:
            self.history.execute(InsertItem(layout.id, len(layout_items(layout)), item_for(self.doc, content, {})))


class QuickInsert(QWidget):
    chosen = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Insert a widget")
        self.list = QListWidget()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.edit)
        layout.addWidget(self.list)
        self.edit.textChanged.connect(self.refresh)
        self.edit.returnPressed.connect(self.accept_current)
        self.list.itemActivated.connect(lambda _item: self.accept_current())
        self.resize(280, 320)
        self.refresh("")

    def refresh(self, text):
        self.list.clear()
        for entry in CATALOG:
            if fuzzy(text, entry.label) or fuzzy(text, entry.class_name):
                self.list.addItem(entry.label)
                self.list.item(self.list.count() - 1).setData(Qt.UserRole, entry)
        if self.list.count():
            self.list.setCurrentRow(0)

    def accept_current(self):
        item = self.list.currentItem()
        if item is not None:
            self.chosen.emit(item.data(Qt.UserRole))
        self.close()

    def popup_at(self, point):
        self.move(point)
        self.show()
        self.edit.setFocus()
        self.edit.selectAll()
