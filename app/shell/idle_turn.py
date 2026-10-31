"""Run save follow-ups when the Qt loop is about to wait.

A zero-timer runs inside the ``processEvents`` that follows the save. That
pump is still the gesture that saved. ``aboutToBlock`` does not fire for it.
"""

from __future__ import annotations

from typing import Callable, List

from app.qt.QtCore import QAbstractEventDispatcher

_pending: List[Callable[[], None]] = []
_armed = False


def run_when_idle(callback: Callable[[], None]) -> None:
    """Queue ``callback`` until the event loop is about to block.

    The running editor reaches that point once the click's posted events are
    done. A test that only pumps ``processEvents`` does not.
    """
    global _armed
    _pending.append(callback)
    if _armed:
        return
    dispatcher = QAbstractEventDispatcher.instance()
    if dispatcher is None:
        _drain()
        return

    def flush() -> None:
        global _armed
        _armed = False
        try:
            dispatcher.aboutToBlock.disconnect(flush)
        except (RuntimeError, TypeError):
            pass
        _drain()

    _armed = True
    dispatcher.aboutToBlock.connect(flush)


def _drain() -> None:
    batch = list(_pending)
    del _pending[:]
    for callback in batch:
        callback()
