"""Run save follow-ups when the Qt loop is about to wait.

A zero-timer runs inside the ``processEvents`` that follows the save. That
pump is still the gesture that saved. ``aboutToBlock`` does not fire for it.
"""

from __future__ import annotations

from typing import Callable, List

from app.bootstrap.logging_setup import get_subsystem_logger
from app.qt.QtCore import QAbstractEventDispatcher, QCoreApplication, QTimer

_LOGGER = get_subsystem_logger("shell")

_pending: List[Callable[[], None]] = []
_armed = False
_quit_hooked = False


def run_when_idle(callback: Callable[[], None]) -> None:
    """Queue ``callback`` until the event loop is about to block.

    The running editor reaches that point once the click's posted events are
    done. A test that only pumps ``processEvents`` does not.
    """
    global _armed
    _pending.append(callback)
    _hook_quit()
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
        # Leave the dispatcher's signal before running the work. The queued
        # call wakes the loop, so it runs before the loop waits for input.
        QTimer.singleShot(0, _drain)

    _armed = True
    dispatcher.aboutToBlock.connect(flush)


def _hook_quit() -> None:
    # A save just before quit still writes its history checkpoint.
    global _quit_hooked
    if _quit_hooked:
        return
    app = QCoreApplication.instance()
    if app is None:
        return
    _quit_hooked = True
    app.aboutToQuit.connect(_drain)


def _drain() -> None:
    batch = list(_pending)
    del _pending[:]
    for callback in batch:
        # One follow-up that fails, such as work for a window that has closed,
        # must not drop the ones queued behind it.
        try:
            callback()
        except Exception:
            _LOGGER.warning("An idle follow-up failed.", exc_info=True)
