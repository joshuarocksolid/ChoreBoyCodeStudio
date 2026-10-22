"""Editor side of the preview process (CONTRACTS.md section 10.3).

One warm child, shared by every open form. Supervisor events arrive on reader
threads. A queued signal marshals them onto the GUI thread before the director
sees them. This module is the only place that turns director effects into a
process.

The child builds widgets. ``LoadForm.module_source`` is the generated module.
Until codegen is merged, hosts send ``ui_xml`` and the child uses QUiLoader.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.diagnostic_codes import fb6xx as _fb6xx
from app.features.form_builder.engine.diagnostics import (
    CODES,
    DiagnosticLocation,
    FormDiagnostic,
    Severity,
)
from app.features.form_builder.engine.ipc.director import (
    Deliver,
    KillChild,
    LogNoise,
    NoteHandshake,
    NoteLoad,
    PreviewDirector,
    SpawnChild,
    WriteFrame,
)
from app.features.form_builder.engine.ipc.protocol import (
    ChildMessage,
    ErrorReport,
    HostMessage,
    Ready,
    Response,
)
from app.features.form_builder.engine.ipc.timing import (
    BACKOFF_SCHEDULE,
    CRASH_WINDOW_SECONDS,
    HANDSHAKE_TIMEOUT_SECONDS,
    IDLE_EXIT_SECONDS,
    MISSED_PINGS_FOR_HANG,
    PING_INTERVAL_SECONDS,
    PREWARM_DEFAULT,
    REQUEST_TIMEOUT_SECONDS,
    SHUTDOWN_GRACE_SECONDS,
    DirectorConfig,
    prewarm_from_environ,
)
from app.features.form_builder.qtside.preview.launch import (
    apprun_preview_command,
    default_apprun,
    repo_root,
)
from app.qt.QtCore import QObject, Qt, QTimer, Signal
from app.run.process_supervisor import ProcessEvent, ProcessSupervisor

# Register FB601–FB605 when the editor imports the pool.
_ = _fb6xx

_LOGGER = logging.getLogger(__name__)

PoolState = str  # "stopped" | "starting" | "ready" | "backoff" | "circuit_open"

_Listener = Callable[[ChildMessage], None]


@dataclass(frozen=True)
class PoolStatus:
    state: PoolState
    child_pid: Optional[int]
    crashes_in_window: int
    next_restart_in: Optional[float]
    last_error: Optional[str]
    handshake_seconds: Optional[float] = None
    load_seconds: Optional[float] = None


class _Bridge(QObject):
    """Reader threads emit. The slot runs on the thread that constructed the pool."""

    incoming: Any = Signal(object)


class PreviewPool:
    """Process-wide preview child. Construct it on the GUI thread, after QApplication."""

    _shared: Optional["PreviewPool"] = None

    def __init__(
        self,
        *,
        command: Optional[Sequence[str]] = None,
        config: Optional[DirectorConfig] = None,
        prewarm: Optional[bool] = None,
        root: Optional[str] = None,
    ) -> None:
        resolved = config or DirectorConfig()
        if prewarm is not None:
            resolved = replace(resolved, prewarm=prewarm)
        self._config = resolved
        self._root = root or repo_root()
        self._command = (
            list(command)
            if command is not None
            else apprun_preview_command(default_apprun(), self._root)
        )
        self._director = PreviewDirector(host_pid=os.getpid(), config=resolved)
        self._supervisor = ProcessSupervisor(on_event=self._on_supervisor_event)
        self._bridge = _Bridge()
        self._bridge.incoming.connect(self._on_gui, Qt.QueuedConnection)
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timer)
        self._wake_at: Optional[float] = None
        self._callbacks: Dict[str, _Listener] = {}
        self._listeners: List[Tuple[Optional[str], _Listener]] = []
        self._diagnostics: List[FormDiagnostic] = []
        self._fb604_at: Dict[str, float] = {}
        self._stderr_lines: List[str] = []
        self._crash_noted = False
        self.spawn_monotonic: List[float] = []
        self.crash_monotonic: List[float] = []

    @classmethod
    def shared(cls) -> "PreviewPool":
        if cls._shared is None:
            cls._shared = cls(prewarm=prewarm_from_environ(os.environ))
        return cls._shared

    @classmethod
    def reset_shared(cls) -> None:
        current = cls._shared
        cls._shared = None
        if current is not None:
            current.shutdown()

    def note_form_opened(self) -> None:
        self._apply(self._director.note_form_opened(time.monotonic()))

    def request(self, message: HostMessage, on_response: _Listener) -> str:
        request_id = getattr(message, "request_id", None)
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("preview request is missing request_id")
        self._callbacks[request_id] = on_response
        self._apply(self._director.request(time.monotonic(), message))
        return request_id

    def subscribe(self, view_id: Optional[str], listener: _Listener) -> Callable[[], None]:
        entry = (view_id, listener)
        self._listeners.append(entry)

        def unsubscribe() -> None:
            try:
                self._listeners.remove(entry)
            except ValueError:
                return None

        return unsubscribe

    def status(self) -> PoolStatus:
        current = self._director.status(time.monotonic())
        pid = self._supervisor.process_id if current.child_alive else None
        return PoolStatus(
            state=current.state,
            child_pid=pid,
            crashes_in_window=current.crashes_in_window,
            next_restart_in=current.next_restart_in,
            last_error=current.last_error,
            handshake_seconds=current.handshake_seconds,
            load_seconds=current.load_seconds,
        )

    def diagnostics(self) -> Tuple[FormDiagnostic, ...]:
        return tuple(self._diagnostics)

    def stderr_tail(self) -> Tuple[str, ...]:
        return tuple(self._stderr_lines)

    def retry(self) -> None:
        self._apply(self._director.retry(time.monotonic()))

    def shutdown(self) -> None:
        self._apply(self._director.shutdown(time.monotonic()))
        self._timer.stop()
        self._wake_at = None
        if self._supervisor.is_running():
            self._supervisor.stop(terminate_timeout_seconds=self._config.shutdown_grace)

    def _on_supervisor_event(self, event: ProcessEvent) -> None:
        self._bridge.incoming.emit(event)

    def _on_gui(self, event: object) -> None:
        if not isinstance(event, ProcessEvent):
            return
        now = time.monotonic()
        if event.event_type == "output":
            text = event.text or ""
            if event.stream == "stderr":
                self._remember_stderr(text)
                effects = self._director.on_stderr(now, text)
            else:
                effects = self._director.on_stdout(now, text)
        elif event.event_type == "exit":
            code = 0 if event.return_code is None else int(event.return_code)
            effects = self._director.on_exit(now, code)
        else:
            return
        self._apply(effects)

    def _on_timer(self) -> None:
        now = time.monotonic()
        wake_before = self._director.next_wake()
        effects = self._director.advance(now)
        if (
            not effects
            and self._director.next_wake() == wake_before
            and wake_before is not None
            and wake_before <= now
        ):
            self._timer.stop()
            self._wake_at = None
            return
        self._apply(effects)

    def _apply(self, effects: Sequence[object]) -> None:
        for effect in effects:
            if isinstance(effect, SpawnChild):
                if not self._spawn():
                    return
            elif isinstance(effect, WriteFrame):
                self._write(effect.text)
            elif isinstance(effect, KillChild):
                self._kill()
            elif isinstance(effect, Deliver):
                self._deliver(effect.message)
            elif isinstance(effect, LogNoise):
                _LOGGER.debug("preview %s: %s", effect.stream, effect.text)
            elif isinstance(effect, NoteHandshake):
                _LOGGER.info("preview handshake %.3fs", effect.seconds)
            elif isinstance(effect, NoteLoad):
                _LOGGER.info("preview load %.3fs", effect.seconds)
        self._arm()

    def _spawn(self) -> bool:
        try:
            self._supervisor.start(self._command, cwd=self._root, env=self._child_env())
        except Exception as exc:
            _LOGGER.warning("preview spawn failed: %s", exc)
            self._apply(self._director.on_spawn_failed(time.monotonic(), str(exc)))
            return False
        self._crash_noted = False
        self.spawn_monotonic.append(time.monotonic())
        return True

    def _write(self, text: str) -> None:
        try:
            self._supervisor.send_input(text)
        except Exception:
            _LOGGER.exception("preview frame was not written")

    def _kill(self) -> None:
        if not self._supervisor.is_running():
            return
        self._supervisor.stop(terminate_timeout_seconds=self._config.shutdown_grace)

    def _deliver(self, message: ChildMessage) -> None:
        if isinstance(message, Ready):
            return self._fanout(message)
        if isinstance(message, ErrorReport):
            if message.code == "FB604" and not self._admit_fb604(message.view_id):
                return
            self._diagnostics.append(self._diagnostic(message.code, message.message))
            if message.code == "FB601" and not self._crash_noted:
                self._crash_noted = True
                self.crash_monotonic.append(time.monotonic())
            self._fanout(message)
            return
        if isinstance(message, Response):
            callback = self._callbacks.pop(message.request_id, None)
            if callback is not None:
                self._safe_call(callback, message)
            return
        self._fanout(message)

    def _fanout(self, message: ChildMessage) -> None:
        view_id = getattr(message, "view_id", None)
        for listener_view, listener in list(self._listeners):
            if listener_view is None or view_id is None or listener_view == view_id:
                self._safe_call(listener, message)

    def _safe_call(self, listener: _Listener, message: ChildMessage) -> None:
        try:
            listener(message)
        except Exception:
            _LOGGER.exception("preview listener failed")

    def _admit_fb604(self, view_id: Optional[str]) -> bool:
        """One FB604 diagnostic per view per second. Later ones in the window are dropped."""
        key = view_id or ""
        now = time.monotonic()
        previous = self._fb604_at.get(key)
        if previous is not None and now - previous < 1.0:
            return False
        self._fb604_at[key] = now
        return True

    def _diagnostic(self, code: str, message: str) -> FormDiagnostic:
        info = CODES.get(code)
        severity = info.severity if info is not None else Severity.ERROR
        return FormDiagnostic(
            code=code,
            severity=severity,
            message=message,
            location=DiagnosticLocation(),
            source="preview",
        )

    def _remember_stderr(self, text: str) -> None:
        for line in text.splitlines():
            cleaned = line[:-1] if line.endswith("\r") else line
            if cleaned:
                self._stderr_lines.append(cleaned)
        if len(self._stderr_lines) > 200:
            del self._stderr_lines[:-200]

    def _arm(self) -> None:
        wake = self._director.next_wake()
        if wake is None:
            self._timer.stop()
            self._wake_at = None
            return
        if self._wake_at == wake and self._timer.isActive():
            return
        self._wake_at = wake
        delay_ms = int(max(0.0, wake - time.monotonic()) * 1000)
        self._timer.start(delay_ms)

    def _child_env(self) -> Dict[str, str]:
        # The parent display wins. Tests set QT_QPA_PLATFORM=offscreen and the
        # child inherits it. Forcing offscreen here would hide a real preview.
        env = dict(os.environ)
        env["CBCS_QT_API"] = "pyside6"
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        root = self._root
        previous = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = root if not previous else root + os.pathsep + previous
        return env


__all__ = [
    "BACKOFF_SCHEDULE",
    "CRASH_WINDOW_SECONDS",
    "HANDSHAKE_TIMEOUT_SECONDS",
    "IDLE_EXIT_SECONDS",
    "MISSED_PINGS_FOR_HANG",
    "PING_INTERVAL_SECONDS",
    "PREWARM_DEFAULT",
    "REQUEST_TIMEOUT_SECONDS",
    "SHUTDOWN_GRACE_SECONDS",
    "PoolStatus",
    "PreviewPool",
]
