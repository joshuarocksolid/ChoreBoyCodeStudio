"""Thread-safe callback dispatching onto the Qt GUI thread."""

from __future__ import annotations

from typing import Callable

from PySide2.QtCore import QObject, Qt, Signal, Slot


class MainThreadDispatcher(QObject):
    """Dispatch callbacks to run asynchronously on the owning Qt thread."""

    _dispatch_requested: Signal = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._dispatch_requested.connect(self._execute_callback, Qt.QueuedConnection)

    def dispatch(self, callback: Callable[[], None]) -> None:
        """Queue *callback* to run on the dispatcher thread."""
        self._dispatch_requested.emit(callback)

    @Slot(object)
    def _execute_callback(self, callback: object) -> None:
        if callable(callback):
            callback()
