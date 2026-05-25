"""Outline tree widget, delegate, and item role constants."""

from __future__ import annotations

from typing import Optional

from PySide2.QtGui import QColor, QPainter, QPalette
from PySide2.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QTreeWidget, QWidget

from app.shell.outline.outline_icons import chevron_icon

ROLE_LINE_NUMBER = 410
ROLE_END_LINE_NUMBER = 411
ROLE_QUALIFIED_NAME = 412
ROLE_KIND = 413
ROLE_NAME_LOWER = 414

SORT_POSITION = "position"
SORT_NAME = "name"
SORT_CATEGORY = "category"
_VALID_SORT_MODES = frozenset({SORT_POSITION, SORT_NAME, SORT_CATEGORY})

_CATEGORY_ORDER: dict[str, int] = {
    "class": 0,
    "constant": 1,
    "field": 2,
    "property": 3,
    "method": 4,
    "async_method": 4,
    "function": 5,
    "async_function": 5,
}


class _IndentGuideDelegate(QStyledItemDelegate):
    """Paints subtle vertical indent guides at each tree-indent level."""

    def __init__(self, tree: QTreeWidget) -> None:
        super().__init__(tree)
        self._tree = tree

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:  # type: ignore[override]
        super().paint(painter, option, index)
        depth = self._depth_of(index)
        if depth <= 0:
            return
        indent = self._tree.indentation()
        if indent <= 0:
            return
        palette = self._tree.palette()
        guide_color = QColor(palette.color(QPalette.Mid))
        guide_color.setAlpha(70)
        painter.save()
        painter.setPen(guide_color)
        rect = option.rect
        for level in range(depth):
            x = rect.left() - (depth - level) * indent + indent // 2
            painter.drawLine(x, rect.top(), x, rect.bottom())
        painter.restore()

    def _depth_of(self, index) -> int:  # type: ignore[no-untyped-def]
        depth = 0
        parent = index.parent()
        while parent.isValid():
            depth += 1
            parent = parent.parent()
        return depth


class _OutlineTreeWidget(QTreeWidget):
    """Tree widget that paints an explicit chevron for items with children."""

    _CHEVRON_SIZE = 10

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._chevron_color: str = "#808080"

    def set_chevron_color(self, color_hex: str) -> None:
        if not color_hex:
            return
        if color_hex == self._chevron_color:
            return
        self._chevron_color = color_hex
        viewport = self.viewport()
        if viewport is not None:
            viewport.update()

    def chevron_color(self) -> str:
        return self._chevron_color

    def drawBranches(self, painter: QPainter, rect, index) -> None:  # type: ignore[no-untyped-def, override]
        item = self.itemFromIndex(index)
        if item is None or item.childCount() == 0:
            super().drawBranches(painter, rect, index)
            return
        icon = chevron_icon(self._chevron_color, expanded=item.isExpanded())
        size = self._CHEVRON_SIZE
        x = rect.right() - size
        y = rect.top() + (rect.height() - size) // 2
        icon.paint(painter, x, y, size, size)
