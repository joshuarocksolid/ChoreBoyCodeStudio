"""Designer form canvas model host."""

from __future__ import annotations

from typing import Callable

from PySide2.QtCore import QItemSelectionModel, Qt, Signal
from PySide2.QtWidgets import QAbstractItemView, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from app.designer.canvas.drop_rules import can_insert_widget
from app.designer.canvas.guides import default_snapped_geometry, widget_icon_char
from app.designer.canvas.selection_controller import SelectionController
from app.designer.model import LayoutItem, PropertyValue, SpacerItem, UIModel, WidgetNode
from app.designer.palette import default_widget_palette_registry
from app.designer.palette.palette_panel import PALETTE_WIDGET_MIME
from app.designer.palette.widget_registry import PaletteWidgetDefinition

TREE_ROLE_OBJECT_NAME = Qt.UserRole + 1


class FormCanvas(QWidget):
    """Canvas host that mutates `UIModel` during insert operations."""

    insert_rejected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("designer.canvas")
        self._model: UIModel | None = None
        self._selection_controller: SelectionController | None = None
        self._item_by_object_name: dict[str, QTreeWidgetItem] = {}
        self._is_syncing_selection = False
        self._palette_registry = default_widget_palette_registry()
        self._snap_to_grid_enabled = True
        self._snap_grid_size = 8
        self._insert_request_handler: Callable[[str], tuple[bool, str]] | None = None

        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QLabel("FORM STRUCTURE", self)
        header.setObjectName("designer.canvas.headerLabel")
        layout.addWidget(header)
        self._hint_label = QLabel("Drag widgets from the palette to add them", self)
        self._hint_label.setObjectName("designer.canvas.hintLabel")
        self._canvas_tree = QTreeWidget(self)
        self._canvas_tree.setObjectName("designer.canvas.tree")
        self._canvas_tree.setHeaderHidden(True)
        self._canvas_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._canvas_tree.itemSelectionChanged.connect(self._handle_tree_selection_changed)
        layout.addWidget(self._hint_label)
        layout.addWidget(self._canvas_tree, 1)

    @property
    def model(self) -> UIModel | None:
        return self._model

    def load_model(self, model: UIModel) -> None:
        self._model = model
        self._rebuild_canvas_tree()

    def set_selection_controller(self, selection_controller: SelectionController | None) -> None:
        if self._selection_controller is selection_controller:
            return
        if self._selection_controller is not None:
            try:
                self._selection_controller.selection_changed.disconnect(self._handle_controller_selection_changed)
                self._selection_controller.selection_set_changed.disconnect(self._handle_controller_selection_set_changed)
            except (RuntimeError, TypeError):
                pass
        self._selection_controller = selection_controller
        if self._selection_controller is not None:
            self._selection_controller.selection_changed.connect(self._handle_controller_selection_changed)
            self._selection_controller.selection_set_changed.connect(self._handle_controller_selection_set_changed)

    def set_insert_request_handler(
        self,
        handler: Callable[[str], tuple[bool, str]] | None,
    ) -> None:
        self._insert_request_handler = handler

    def configure_snap_to_grid(self, *, enabled: bool, grid_size: int) -> None:
        self._snap_to_grid_enabled = bool(enabled)
        self._snap_grid_size = max(1, int(grid_size))

    def insert_palette_widget(
        self,
        *,
        parent_object_name: str,
        definition: PaletteWidgetDefinition,
    ) -> WidgetNode | SpacerItem:
        if self._model is None:
            raise ValueError("No form model loaded.")

        parent_widget = self._model.root_widget.find_by_object_name(parent_object_name)
        if parent_widget is None:
            raise ValueError(f"Parent widget not found: {parent_object_name}")

        parent_has_layout = parent_widget.layout is not None
        if not can_insert_widget(
            parent_class_name=parent_widget.class_name,
            child_class_name=definition.class_name,
            is_layout_item=definition.is_layout_item,
            parent_has_layout=parent_has_layout,
        ):
            raise ValueError(
                "Widget insertion is not allowed for the selected parent."
            )

        if definition.is_layout_item:
            spacer = SpacerItem(name=self._generate_unique_object_name(definition.default_object_name_prefix))
            assert parent_widget.layout is not None
            parent_widget.layout.items.append(LayoutItem(spacer=spacer))
            return spacer

        widget = WidgetNode(
            class_name=definition.class_name,
            object_name=self._generate_unique_object_name(definition.default_object_name_prefix),
        )
        if parent_widget.layout is not None:
            parent_widget.layout.items.append(LayoutItem(widget=widget))
        else:
            geometry = default_snapped_geometry(
                insert_index=len(parent_widget.children),
                grid_size=self._snap_grid_size if self._snap_to_grid_enabled else 1,
                class_name=widget.class_name,
            )
            widget.properties["geometry"] = PropertyValue(value_type="rect", value=geometry)
            parent_widget.children.append(widget)
        self._rebuild_canvas_tree()
        return widget

    def dragEnterEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        mime_data = event.mimeData()
        if mime_data is not None and mime_data.hasFormat(PALETTE_WIDGET_MIME):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        mime_data = event.mimeData()
        if mime_data is None or not mime_data.hasFormat(PALETTE_WIDGET_MIME):
            event.ignore()
            return
        class_name = bytes(mime_data.data(PALETTE_WIDGET_MIME)).decode("utf-8").strip()
        if not class_name:
            event.ignore()
            return
        if self._insert_request_handler is None:
            inserted, error_message = self.try_insert_widget_by_class_name(class_name)
        else:
            inserted, error_message = self._insert_request_handler(class_name)
        if not inserted:
            if error_message:
                self.insert_rejected.emit(error_message)
            event.ignore()
            return
        event.acceptProposedAction()

    def insert_widget_by_class_name(self, class_name: str) -> bool:
        inserted, _error_message = self.try_insert_widget_by_class_name(class_name)
        return inserted

    def try_insert_widget_by_class_name(self, class_name: str) -> tuple[bool, str]:
        if self._model is None:
            return False, "No form model loaded."
        definition = self._palette_registry.lookup(class_name)
        if definition is None:
            return False, "Widget insertion is not allowed for the selected parent."
        parent_name = self._resolve_insert_parent_object_name(definition)
        if not parent_name:
            return False, "Widget insertion is not allowed for the selected parent."
        try:
            inserted = self.insert_palette_widget(parent_object_name=parent_name, definition=definition)
        except ValueError as exc:
            return False, str(exc)
        inserted_name = getattr(inserted, "object_name", "")
        if inserted_name and self._selection_controller is not None:
            self._selection_controller.set_selected_object_name(inserted_name)
        return True, ""

    def _resolve_insert_parent_object_name(self, definition: PaletteWidgetDefinition) -> str | None:
        if self._model is None:
            return None
        for candidate in self._candidate_insert_parents():
            if can_insert_widget(
                parent_class_name=candidate.class_name,
                child_class_name=definition.class_name,
                is_layout_item=definition.is_layout_item,
                parent_has_layout=candidate.layout is not None,
            ):
                return candidate.object_name
        return None

    def _candidate_insert_parents(self) -> list[WidgetNode]:
        assert self._model is not None
        root = self._model.root_widget
        selected_name = None if self._selection_controller is None else self._selection_controller.selected_object_name
        if not selected_name:
            return [root]
        selection_path = self._find_selection_path(root, selected_name)
        if not selection_path:
            return [root]
        if selection_path[-1].object_name != root.object_name:
            selection_path.append(root)
        return selection_path

    def _find_selection_path(self, current: WidgetNode, target_name: str) -> list[WidgetNode]:
        if current.object_name == target_name:
            return [current]
        descendants: list[WidgetNode] = list(current.children)
        if current.layout is not None:
            descendants.extend(item.widget for item in current.layout.items if item.widget is not None)
        for child in descendants:
            if child is None:
                continue
            path = self._find_selection_path(child, target_name)
            if path:
                path.append(current)
                return path
        return []

    def _generate_unique_object_name(self, prefix: str) -> str:
        assert self._model is not None
        names = set(self._model.collect_object_names())
        if prefix not in names:
            return prefix
        index = 1
        while True:
            candidate = f"{prefix}{index}"
            if candidate not in names:
                return candidate
            index += 1

    def _rebuild_canvas_tree(self) -> None:
        self._canvas_tree.clear()
        self._item_by_object_name.clear()
        if self._model is None:
            return
        root_item = self._build_tree_item(self._model.root_widget)
        self._canvas_tree.addTopLevelItem(root_item)
        root_item.setExpanded(True)

    def _build_tree_item(self, widget: WidgetNode) -> QTreeWidgetItem:
        icon = widget_icon_char(widget.class_name)
        prefix = f"{icon} " if icon else ""
        item = QTreeWidgetItem([f"{prefix}{widget.object_name} : {widget.class_name}"])
        item.setData(0, TREE_ROLE_OBJECT_NAME, widget.object_name)
        self._item_by_object_name[widget.object_name] = item
        for child in widget.children:
            item.addChild(self._build_tree_item(child))
        if widget.layout is not None:
            for layout_item in widget.layout.items:
                if layout_item.widget is not None:
                    item.addChild(self._build_tree_item(layout_item.widget))
        return item

    def _handle_tree_selection_changed(self) -> None:
        if self._is_syncing_selection:
            return
        if self._selection_controller is None:
            return
        selected_items = self._canvas_tree.selectedItems()
        selected_names = [item.data(0, TREE_ROLE_OBJECT_NAME) for item in selected_items if item.data(0, TREE_ROLE_OBJECT_NAME)]
        self._selection_controller.set_selected_object_names(selected_names)

    def _handle_controller_selection_changed(self, object_name: str) -> None:
        if self._selection_controller is not None and len(self._selection_controller.selected_object_names) > 1:
            return
        if not object_name:
            self._canvas_tree.clearSelection()
            return
        target = self._item_by_object_name.get(object_name)
        if target is None:
            return
        self._is_syncing_selection = True
        try:
            self._canvas_tree.setCurrentItem(target)
            target.setSelected(True)
        finally:
            self._is_syncing_selection = False

    def _handle_controller_selection_set_changed(self, object_names: list[str]) -> None:
        if self._is_syncing_selection:
            return
        self._is_syncing_selection = True
        try:
            self._canvas_tree.clearSelection()
            if not object_names:
                return
            first_item = None
            for object_name in object_names:
                target = self._item_by_object_name.get(object_name)
                if target is None:
                    continue
                self._canvas_tree.selectionModel().select(
                    self._canvas_tree.indexFromItem(target),
                    QItemSelectionModel.Select | QItemSelectionModel.Rows,
                )
                if first_item is None:
                    first_item = target
            if first_item is not None:
                self._canvas_tree.setCurrentItem(first_item)
        finally:
            self._is_syncing_selection = False
