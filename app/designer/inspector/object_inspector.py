"""Object inspector tree for Designer widget hierarchy."""

from __future__ import annotations

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from app.designer.canvas.selection_controller import SelectionController
from app.designer.model import UIModel, WidgetNode

TREE_ROLE_OBJECT_NAME = Qt.UserRole + 1


class ObjectInspector(QWidget):
    """Tree view showing widget hierarchy with selection synchronization."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model: UIModel | None = None
        self._selection_controller: SelectionController | None = None
        self._item_by_object_name: dict[str, QTreeWidgetItem] = {}
        self._is_syncing_selection = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._tree = QTreeWidget(self)
        self._tree.setHeaderHidden(True)
        self._tree.itemSelectionChanged.connect(self._handle_tree_selection_changed)
        layout.addWidget(self._tree)

    def bind_model(self, model: UIModel) -> None:
        self._model = model
        self._tree.clear()
        self._item_by_object_name.clear()
        root_item = self._build_item(model.root_widget)
        self._tree.addTopLevelItem(root_item)
        root_item.setExpanded(True)

    def set_selection_controller(self, selection_controller: SelectionController | None) -> None:
        if self._selection_controller is selection_controller:
            return
        if self._selection_controller is not None:
            try:
                self._selection_controller.selection_changed.disconnect(self._handle_controller_selection_changed)
            except (RuntimeError, TypeError):
                pass
        self._selection_controller = selection_controller
        if self._selection_controller is not None:
            self._selection_controller.selection_changed.connect(self._handle_controller_selection_changed)

    def _build_item(self, widget: WidgetNode) -> QTreeWidgetItem:
        label = f"{widget.object_name} : {widget.class_name}"
        item = QTreeWidgetItem([label])
        item.setData(0, TREE_ROLE_OBJECT_NAME, widget.object_name)
        self._item_by_object_name[widget.object_name] = item

        for child in widget.children:
            item.addChild(self._build_item(child))
        if widget.layout is not None:
            for layout_item in widget.layout.items:
                if layout_item.widget is not None:
                    item.addChild(self._build_item(layout_item.widget))
        return item

    def _handle_tree_selection_changed(self) -> None:
        if self._is_syncing_selection:
            return
        selected_items = self._tree.selectedItems()
        selected_object_name = None
        if selected_items:
            selected_object_name = selected_items[0].data(0, TREE_ROLE_OBJECT_NAME)
        if self._selection_controller is not None:
            self._selection_controller.set_selected_object_name(selected_object_name)

    def _handle_controller_selection_changed(self, object_name: str) -> None:
        if not object_name:
            self._tree.clearSelection()
            return
        target = self._item_by_object_name.get(object_name)
        if target is None:
            return
        self._is_syncing_selection = True
        try:
            self._tree.setCurrentItem(target)
            target.setSelected(True)
        finally:
            self._is_syncing_selection = False
