"""Child side of the preview process (CONTRACTS.md section 10.4).

``run_form_preview.py`` isolates stdin and stdout, forces ``CBCS_QT_API=pyside6``,
then imports this module. User code, promoted classes, generated modules and
``*_rc.py`` run only here. This module does not import ``app.shell``,
``app.editors`` or ``integration``.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import threading
import traceback
from typing import IO, Optional, Sequence

from app.features.form_builder.engine.ipc.protocol import CrashReport, Ready
from app.features.form_builder.qtside.preview.child.session import ChildSession
from app.features.form_builder.qtside.preview.child.stdio import FrameWriter, StreamPair, isolate_stdio
from app.qt.QtCore import QObject, Qt, QTimer, Signal, qInstallMessageHandler, qVersion
from app.qt.QtWidgets import QApplication
from app.qt.qt_compat import IS_QT6, QT_API, exec_qt


class _Wake(QObject):
    """Queues ``drain`` onto the GUI thread from the request reader."""

    arrived = Signal()


class _StdoutLog:
    def __init__(self, session: ChildSession) -> None:
        self._session = session

    def write(self, text: str) -> int:
        self._session.log_stdout(text)
        return len(text)

    def flush(self) -> None:
        return None

    def isatty(self) -> bool:
        return False


def main(argv: Sequence[str], streams: Optional[StreamPair] = None) -> int:
    del argv
    requests, frames = streams if streams is not None else isolate_stdio()
    writer = FrameWriter(frames)
    if not IS_QT6:
        writer.send(CrashReport(message="The preview child requires PySide6.", traceback=""))
        return 1
    app = QApplication(["cbcs-form-preview"])
    session = ChildSession(writer, app)
    sys.stdout = _StdoutLog(session)  # type: ignore[assignment]
    sys.excepthook = _crash_hook(writer)
    _install_qt_log(session, writer)
    binding = sys.modules.get(QT_API)
    writer.send(
        Ready(
            child_pid=os.getpid(),
            python=sys.version.split()[0],
            qt_version=qVersion(),
            pyside_version=str(getattr(binding, "__version__", "")),
            freecadgui=importlib.util.find_spec("FreeCADGui") is not None,
        )
    )
    wake = _Wake()
    wake.arrived.connect(session.drain, Qt.QueuedConnection)
    reader = threading.Thread(
        target=_read_requests,
        args=(requests, session, wake),
        name="preview-requests",
        daemon=True,
    )
    reader.start()
    backup = QTimer()
    backup.timeout.connect(session.drain)
    backup.start(50)
    idle = QTimer()
    idle.timeout.connect(session.check_idle)
    idle.start(1000)
    exec_qt(app)
    return session.exit_code


def _read_requests(requests: IO[str], session: ChildSession, wake: _Wake) -> None:
    try:
        for line in requests:
            session.push_line(line)
            wake.arrived.emit()
    except Exception:
        session.push_line(None)
        wake.arrived.emit()
        return
    session.push_line(None)
    wake.arrived.emit()


def _crash_hook(writer: FrameWriter):
    def hook(exc_type: type, value: BaseException, tb: object) -> None:
        text = "".join(traceback.format_exception(exc_type, value, tb))  # type: ignore[arg-type]
        try:
            writer.send(CrashReport(message=str(value), traceback=text))
        finally:
            os._exit(1)

    return hook


def _install_qt_log(session: ChildSession, writer: FrameWriter) -> None:
    def handler(mode: object, context: object, message: object) -> None:
        del context
        name = str(mode)
        if "Critical" in name or "Fatal" in name:
            level = "error"
        elif "Warning" in name:
            level = "warning"
        elif "Debug" in name:
            level = "debug"
        else:
            level = "info"
        session.log_qt(level, str(message))
        if "Fatal" in name:
            writer.send(CrashReport(message=str(message), traceback=name))

    qInstallMessageHandler(handler)
