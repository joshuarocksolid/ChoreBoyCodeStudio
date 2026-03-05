"""Widget palette panel placeholder."""

from __future__ import annotations

from PySide2.QtCore import Signal
from PySide2.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from app.designer.palette.widget_registry import WidgetPaletteRegistry, default_widget_palette_registry


class PalettePanel(QWidget):
    """Simple categorized widget palette view."""

    widget_insert_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None, *, registry: WidgetPaletteRegistry | None = None) -> None:
        super().__init__(parent)
        self._registry = registry or default_widget_palette_registry()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._tree = QTreeWidget(self)
        self._tree.setHeaderHidden(True)
        self._tree.itemDoubleClicked.connect(self._handle_item_double_clicked)
        layout.addWidget(self._tree)
        self._rebuild_tree()

    def _rebuild_tree(self) -> None:
        self._tree.clear()
        categories: dict[str, QTreeWidgetItem] = {}
        for item in self._registry.list_all():
            category_item = categories.get(item.category)
            if category_item is None:
                category_item = QTreeWidgetItem([item.category])
                self._tree.addTopLevelItem(category_item)
                categories[item.category] = category_item
            child = QTreeWidgetItem([item.display_name])
            child.setData(0, 256, item.class_name)
            category_item.addChild(child)
        for category_item in categories.values():
            category_item.setExpanded(True)

    def _handle_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        class_name = str(item.data(0, 256) or "").strip()
        if not class_name:
            return
        self.widget_insert_requested.emit(class_name)
