"""Project tree widget with filesystem-aware drag/drop callback hooks."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide2.QtCore import QUrl, Qt, Signal
from PySide2.QtGui import QKeySequence
from PySide2.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem


class ProjectTreeWidget(QTreeWidget):
    """QTreeWidget extension that delegates drag/drop file moves to callback."""

    deleteRequested: Any = Signal()
    renameRequested: Any = Signal()
    copyRequested: Any = Signal()
    cutRequested: Any = Signal()
    pasteRequested: Any = Signal()

    def __init__(self, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self._drag_source_path: str | None = None
        self._drop_callback: Callable[[str, str], bool] | None = None
        self._shortcut_bindings: list[tuple[str, str]] = []
        self._shortcut_resolver: Callable[[str], str] | None = None
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)

    def configure_shortcut_bindings(
        self,
        bindings: list[tuple[str, str]] | tuple[tuple[str, str], ...],
        resolver: Callable[[str], str],
    ) -> None:
        self._shortcut_bindings = list(bindings)
        self._shortcut_resolver = resolver

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if event.key() == Qt.Key_Backspace:
            self.deleteRequested.emit()
            return
        for action_id, signal_name in self._shortcut_bindings:
            if self._event_matches_configured_shortcut(event, action_id):
                getattr(self, signal_name).emit()
                return
        super().keyPressEvent(event)

    def _event_matches_configured_shortcut(self, event: object, action_id: str) -> bool:
        if self._shortcut_resolver is None:
            return False
        shortcut_text = self._shortcut_resolver(action_id).strip()
        if not shortcut_text:
            return False
        key = event.key()  # type: ignore[attr-defined]
        modifiers = event.modifiers()  # type: ignore[attr-defined]
        pressed = QKeySequence(key | int(modifiers))
        configured = QKeySequence(shortcut_text)
        return configured.matches(pressed) == QKeySequence.ExactMatch

    def set_drop_callback(self, callback: Callable[[str, str], bool] | None) -> None:
        self._drop_callback = callback

    def mimeData(self, items: list[QTreeWidgetItem]) -> "QMimeData":  # type: ignore[override]  # noqa: N802
        """Include ``file://`` URLs so other widgets (e.g. the console) can accept tree drags."""
        data = super().mimeData(items)
        urls = []
        for item in items:
            path = str(item.data(0, 256) or "")
            if path:
                urls.append(QUrl.fromLocalFile(path))
        if urls:
            data.setUrls(urls)
        return data

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
