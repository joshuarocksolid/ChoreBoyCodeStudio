"""Project tree widget with filesystem-aware drag/drop callback hooks."""

from __future__ import annotations

from collections.abc import Callable

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QAbstractItemView, QTreeWidget


class ProjectTreeWidget(QTreeWidget):
    """QTreeWidget extension that delegates drag/drop file moves to callback."""

    def __init__(self, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self._drag_source_path: str | None = None
        self._drop_callback: Callable[[str, str], bool] | None = None
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)

    def set_drop_callback(self, callback: Callable[[str, str], bool] | None) -> None:
        self._drop_callback = callback

    def startDrag(self, supportedActions) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        current = self.currentItem()
        self._drag_source_path = None if current is None else str(current.data(0, 256) or "")
        super().startDrag(supportedActions)

    def dropEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if self._drop_callback is None or not self._drag_source_path:
            event.ignore()
            return

        target_item = self.itemAt(event.pos())
        target_path = None if target_item is None else str(target_item.data(0, 256) or "")
        if not target_path:
            event.ignore()
            return
        if self._drop_callback(self._drag_source_path, target_path):
            event.acceptProposedAction()
        else:
            event.ignore()
