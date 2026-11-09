# pyright: reportAttributeAccessIssue=false
"""Pump the Qt loop until it is idle.

The handler checks and the save follow-ups run on the editor's idle turn, when
the loop is about to block. ``processEvents`` never reaches that point, so a
test that reads their result runs the loop for a short while instead.
"""

from __future__ import annotations

from app.qt.QtCore import QEventLoop, QTimer
from app.qt.qt_compat import exec_qt


def pump_until_idle(milliseconds: int = 40) -> None:
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    exec_qt(loop)
