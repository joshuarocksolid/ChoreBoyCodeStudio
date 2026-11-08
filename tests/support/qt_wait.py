"""Wait on the Qt event loop on both bindings.

PySide2's ``QTest`` has no ``qWait``. ``processEvents`` also skips
``DeferredDelete`` posted while no loop is running, so a popup that
closes with ``WA_DeleteOnClose`` stays reachable until a loop turn.
"""

from __future__ import annotations


def qt_wait(milliseconds: int) -> None:
    """Run the event loop for ``milliseconds`` so timers and deletes happen."""
    from app.qt.QtCore import QEventLoop, QTimer
    from app.qt.qt_compat import exec_qt

    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    exec_qt(loop)
