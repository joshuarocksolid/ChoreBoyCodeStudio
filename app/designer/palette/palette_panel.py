"""Widget palette panel with search filter and categorized tree."""

from __future__ import annotations

from PySide2.QtCore import QMimeData, QPoint, Qt, Signal
from PySide2.QtGui import QDrag, QMouseEvent
from PySide2.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

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
    """Categorized widget palette with search filter and type indicators."""

    widget_insert_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None, *, registry: WidgetPaletteRegistry | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("designer.palette.panel")
        self._registry = registry or default_widget_palette_registry()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QLabel("WIDGETS", self)
        header.setObjectName("designer.palette.header")
        header.setContentsMargins(8, 6, 8, 4)
        layout.addWidget(header)

        # Search / filter field
        self._filter_input = QLineEdit(self)
        self._filter_input.setObjectName("designer.palette.filterInput")
        self._filter_input.setPlaceholderText("Filter widgets\u2026")
        self._filter_input.setClearButtonEnabled(True)
        self._filter_input.setContentsMargins(6, 2, 6, 2)
        self._filter_input.textChanged.connect(self._apply_filter)
        layout.addWidget(self._filter_input)

        # Tree
        self._tree = _PaletteTreeWidget(self)
        self._tree.setObjectName("designer.palette.tree")
        self._tree.setHeaderHidden(True)
        self._tree.itemDoubleClicked.connect(self._handle_item_double_clicked)
        layout.addWidget(self._tree, 1)
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
            display = f"{item.icon_char}  {item.display_name}" if item.icon_char else item.display_name
            child = QTreeWidgetItem([display])
            child.setData(0, 256, item.class_name)
            child.setToolTip(0, item.class_name)
            category_item.addChild(child)
        for category_item in categories.values():
            category_item.setExpanded(True)

    def _apply_filter(self, text: str) -> None:
        """Filter tree items by display name or class name (case-insensitive)."""
        needle = text.strip().lower()
        for cat_index in range(self._tree.topLevelItemCount()):
            category_item = self._tree.topLevelItem(cat_index)
            if category_item is None:
                continue
            any_visible = False
            for child_index in range(category_item.childCount()):
                child = category_item.child(child_index)
                if child is None:
                    continue
                class_name = str(child.data(0, 256) or "").lower()
                display_text = child.text(0).lower()
                matches = not needle or needle in class_name or needle in display_text
                child.setHidden(not matches)
                if matches:
                    any_visible = True
            category_item.setHidden(not any_visible)

    def _handle_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        class_name = str(item.data(0, 256) or "").strip()
        if not class_name:
            return
        self.widget_insert_requested.emit(class_name)
