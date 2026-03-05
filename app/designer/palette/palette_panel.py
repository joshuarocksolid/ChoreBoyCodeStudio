"""Widget palette panel placeholder."""

from __future__ import annotations

from PySide2.QtCore import QMimeData, QPoint, Qt, Signal
from PySide2.QtGui import QDrag, QMouseEvent
from PySide2.QtWidgets import QApplication, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from app.designer.palette.widget_registry import WidgetPaletteRegistry, default_widget_palette_registry

PALETTE_WIDGET_MIME = "application/x-cbcs-designer-class"


class _PaletteTreeWidget(QTreeWidget):
    """Tree widget that starts drag payloads for palette entries."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_start_pos = QPoint()
        self._drag_class_name: str | None = None

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
            item = self.itemAt(event.pos())
            self._drag_class_name = None if item is None else str(item.data(0, 256) or "").strip()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if not (event.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(event)
            return
        if not self._drag_class_name:
            super().mouseMoveEvent(event)
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            super().mouseMoveEvent(event)
            return
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setData(PALETTE_WIDGET_MIME, self._drag_class_name.encode("utf-8"))
        mime_data.setText(self._drag_class_name)
        drag.setMimeData(mime_data)
        drag.exec_(Qt.CopyAction)
        super().mouseMoveEvent(event)


class PalettePanel(QWidget):
    """Simple categorized widget palette view."""

    widget_insert_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None, *, registry: WidgetPaletteRegistry | None = None) -> None:
        super().__init__(parent)
        self._registry = registry or default_widget_palette_registry()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._tree = _PaletteTreeWidget(self)
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
