"""Object inspector tree for Designer widget hierarchy."""

from __future__ import annotations

from collections.abc import Callable
from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from app.designer.canvas.drop_rules import is_parent_drop_target
from app.designer.canvas.selection_controller import SelectionController
from app.designer.model import UIModel, WidgetNode

TREE_ROLE_OBJECT_NAME = Qt.UserRole + 1


class _ObjectTreeWidget(QTreeWidget):
    """Object tree with callback-driven drag/drop reparenting."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_source_object_name: str | None = None
        self._drop_callback: Callable[[str, str], bool] | None = None
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)

    def set_drop_callback(self, callback: Callable[[str, str], bool] | None) -> None:
        self._drop_callback = callback

    def startDrag(self, supportedActions) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        current = self.currentItem()
        self._drag_source_object_name = None if current is None else str(current.data(0, TREE_ROLE_OBJECT_NAME) or "")
        super().startDrag(supportedActions)

    def dropEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if self._drop_callback is None or not self._drag_source_object_name:
            event.ignore()
            return
        target = self.itemAt(event.pos())
        target_object_name = None if target is None else str(target.data(0, TREE_ROLE_OBJECT_NAME) or "")
        if not target_object_name:
            event.ignore()
            return
        if self._drop_callback(self._drag_source_object_name, target_object_name):
            event.acceptProposedAction()
        else:
            event.ignore()


class ObjectInspector(QWidget):
    """Tree view showing widget hierarchy with selection synchronization."""

    reparent_applied = Signal(str, str)
    reparent_rejected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model: UIModel | None = None
        self._selection_controller: SelectionController | None = None
        self._item_by_object_name: dict[str, QTreeWidgetItem] = {}
        self._is_syncing_selection = False
        self._reparent_callback: Callable[[str, str], bool] | None = None
        self._last_reparent_error = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._tree = _ObjectTreeWidget(self)
        self._tree.setHeaderHidden(True)
        self._tree.itemSelectionChanged.connect(self._handle_tree_selection_changed)
        self._tree.set_drop_callback(self._handle_drop_reparent)
        layout.addWidget(self._tree)

    def set_reparent_callback(self, callback: Callable[[str, str], bool] | None) -> None:
        self._reparent_callback = callback

    @property
    def last_reparent_error(self) -> str:
        return self._last_reparent_error

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

    def _handle_drop_reparent(self, source_object_name: str, target_object_name: str) -> bool:
        if self._reparent_callback is not None:
            return self._reparent_callback(source_object_name, target_object_name)
        return self.reparent_widget(source_object_name, target_object_name)

    def reparent_widget(self, source_object_name: str, target_object_name: str) -> bool:
        if self._model is None:
            self._set_reparent_error("No model bound.")
            return False
        if source_object_name == target_object_name:
            self._set_reparent_error("Cannot reparent onto the same widget.")
            return False
        source_widget = self._model.root_widget.find_by_object_name(source_object_name)
        target_widget = self._model.root_widget.find_by_object_name(target_object_name)
        if source_widget is None or target_widget is None:
            self._set_reparent_error("Source or target widget was not found.")
            return False
        if self._is_descendant(source_widget, potential_ancestor=target_widget):
            self._set_reparent_error("Cannot reparent a widget into one of its descendants.")
            return False
        if not is_parent_drop_target(target_widget.class_name):
            self._set_reparent_error("Selected target cannot accept child widgets.")
            return False

        if not self._detach_widget(source_object_name):
            self._set_reparent_error("Failed to detach source widget from current parent.")
            return False
        if target_widget.layout is not None:
            from app.designer.model import LayoutItem

            target_widget.layout.items.append(LayoutItem(widget=source_widget))
        else:
            target_widget.children.append(source_widget)
        self._set_reparent_error("")
        self.bind_model(self._model)
        if self._selection_controller is not None:
            self._selection_controller.set_selected_object_name(source_object_name)
        self.reparent_applied.emit(source_object_name, target_object_name)
        return True

    def _detach_widget(self, source_object_name: str) -> bool:
        if self._model is None:
            return False
        if self._model.root_widget.object_name == source_object_name:
            return False
        return self._detach_widget_from_subtree(self._model.root_widget, source_object_name)

    def _detach_widget_from_subtree(self, parent: WidgetNode, source_object_name: str) -> bool:
        for index, child in enumerate(list(parent.children)):
            if child.object_name == source_object_name:
                parent.children.pop(index)
                return True
            if self._detach_widget_from_subtree(child, source_object_name):
                return True
        if parent.layout is not None:
            for index, item in enumerate(list(parent.layout.items)):
                child_widget = item.widget
                if child_widget is None:
                    continue
                if child_widget.object_name == source_object_name:
                    parent.layout.items.pop(index)
                    return True
                if self._detach_widget_from_subtree(child_widget, source_object_name):
                    return True
        return False

    def _is_descendant(self, source_widget: WidgetNode, *, potential_ancestor: WidgetNode) -> bool:
        if source_widget.object_name == potential_ancestor.object_name:
            return True
        for child in source_widget.children:
            if self._is_descendant(child, potential_ancestor=potential_ancestor):
                return True
        if source_widget.layout is not None:
            for item in source_widget.layout.items:
                if item.widget is None:
                    continue
                if self._is_descendant(item.widget, potential_ancestor=potential_ancestor):
                    return True
        return False

    def _set_reparent_error(self, message: str) -> None:
        self._last_reparent_error = message
        if message:
            self.reparent_rejected.emit(message)
