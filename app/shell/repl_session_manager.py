"""Dedicated REPL session manager independent of the script run lifecycle.

Owns a private ``ProcessSupervisor`` so the Python Console can run
simultaneously with script/debug sessions.  Supports auto-start on
app launch and auto-restart when the REPL process exits unexpectedly.
"""

from __future__ import annotations

import logging
import socket
import threading
from datetime import datetime
from typing import Callable

from app.bootstrap.paths import PathInput
from app.intelligence.completion_models import CompletionEnvelope
from app.run.process_supervisor import ProcessEvent, ProcessSupervisor
from app.run.run_manifest import ReplControlConfig
from app.run.run_service import RunService
from app.runner.repl_protocol import (
    build_complete_request,
    build_introspect_request,
    dumps_message,
    envelope_from_dict,
    loads_message,
)

_logger = logging.getLogger(__name__)

_MAX_RAPID_RESTARTS = 5
_RAPID_RESTART_WINDOW_SECONDS = 10.0
_AUTO_RESTART_DELAY_SECONDS = 0.5


class ReplSessionManager:
    """Manages an always-on Python REPL subprocess."""

    def __init__(
        self,
        *,
        on_output: Callable[[str, str], None] | None = None,
        on_session_ended: Callable[[int | None, bool], None] | None = None,
        on_session_started: Callable[[], None] | None = None,
        run_service: RunService | None = None,
        runtime_executable: str | None = None,
        runner_boot_path: str | None = None,
        state_root: PathInput | None = None,
    ) -> None:
        self._on_output = on_output
        self._on_session_ended = on_session_ended
        self._on_session_started = on_session_started
        self._supervisor = ProcessSupervisor(on_event=self._handle_event)
        self._run_service = run_service or RunService(
            runtime_executable=runtime_executable,
            runner_boot_path=runner_boot_path,
            state_root=state_root,
        )
        self._auto_restart = True
        self._shutting_down = False
        self._recent_exit_times: list[float] = []
        self._control_config: ReplControlConfig | None = None

    @property
    def is_running(self) -> bool:
        return self._supervisor.is_running()

    def start(self) -> None:
        """Launch the REPL subprocess (no-op if already running)."""
        if self._supervisor.is_running():
            return
        self._shutting_down = False
        self._auto_restart = True
        try:
            self._launch()
        except Exception:
            _logger.exception("Failed to start REPL session")
            return
        if self._on_session_started is not None:
            self._on_session_started()

    def stop(self) -> None:
        """Stop the REPL subprocess and suppress auto-restart."""
        self._auto_restart = False
        self._shutting_down = True
        if self._supervisor.is_running():
            self._supervisor.stop()

    def restart(self) -> None:
        """Stop then re-launch the REPL subprocess."""
        self.stop()
        self._shutting_down = False
        self._auto_restart = True
        self._recent_exit_times.clear()
        try:
            self._launch()
        except Exception:
            _logger.exception("Failed to restart REPL session")
            return
        if self._on_session_started is not None:
            self._on_session_started()

    def send_input(self, text: str) -> None:
        """Send *text* to the REPL subprocess stdin."""
        if not text.endswith("\n"):
            text += "\n"
        self._supervisor.send_input(text)

    def complete(
        self,
        *,
        line_buffer: str,
        cursor_offset: int,
        trigger_kind: str,
        trigger_character: str,
        max_results: int = 100,
    ) -> CompletionEnvelope:
        """Request live completions from the active REPL control channel."""

        config = self._control_config
        if config is None or not self._supervisor.is_running():
            return CompletionEnvelope(items=[], degradation_reason="repl_unavailable")
        payload = build_complete_request(
            protocol=config.protocol,
            session_token=config.session_token,
            line_buffer=line_buffer,
            cursor_offset=cursor_offset,
            trigger_kind=trigger_kind,
            trigger_character=trigger_character,
            max_results=max_results,
        )
        timeout_seconds = max(0.1, config.connect_timeout_ms / 1000.0)
        try:
            with socket.create_connection((config.host, config.port), timeout=timeout_seconds) as sock:
                sock.settimeout(timeout_seconds)
                sock.sendall(dumps_message(payload))
                response = _read_json_line(sock)
        except OSError as exc:
            _logger.debug("REPL completion request failed: %s", exc)
            return CompletionEnvelope(items=[], degradation_reason="repl_control_unavailable")
        if not response.get("ok"):
            return CompletionEnvelope(items=[], degradation_reason=str(response.get("error") or "repl_error"))
        result = response.get("result")
        if not isinstance(result, dict):
            return CompletionEnvelope(items=[], degradation_reason="repl_invalid_response")
        return envelope_from_dict(result)

    def introspect(
        self,
        *,
        target_path: str,
        member_prefix: str = "",
        include_private: bool = True,
        max_results: int = 100,
    ) -> CompletionEnvelope:
        """Request trusted runtime member listing from the active REPL control channel."""

        config = self._control_config
        if config is None or not self._supervisor.is_running():
            return CompletionEnvelope(items=[], degradation_reason="repl_unavailable")
        payload = build_introspect_request(
            protocol=config.protocol,
            session_token=config.session_token,
            target_path=target_path,
            member_prefix=member_prefix,
            include_private=include_private,
            max_results=max_results,
        )
        timeout_seconds = max(0.1, config.connect_timeout_ms / 1000.0)
        try:
            with socket.create_connection((config.host, config.port), timeout=timeout_seconds) as sock:
                sock.settimeout(timeout_seconds)
                sock.sendall(dumps_message(payload))
                response = _read_json_line(sock)
        except OSError as exc:
            _logger.debug("REPL introspection request failed: %s", exc)
            return CompletionEnvelope(items=[], degradation_reason="repl_control_unavailable")
        if not response.get("ok"):
            return CompletionEnvelope(items=[], degradation_reason=str(response.get("error") or "repl_error"))
        result = response.get("result")
        if not isinstance(result, dict):
            return CompletionEnvelope(items=[], degradation_reason="repl_invalid_response")
        return envelope_from_dict(result)

    def shutdown(self) -> None:
        """Permanent shutdown (call during app close)."""
        self._auto_restart = False
        self._shutting_down = True
        if self._supervisor.is_running():
            self._supervisor.stop()

    def _launch(self) -> None:
        launch = self._run_service.start_repl_sidecar(supervisor=self._supervisor)
        self._control_config = launch.repl_control

    def _handle_event(self, event: ProcessEvent) -> None:
        if event.event_type == "output" and event.text:
            stream = event.stream or "stdout"
            if self._on_output is not None:
                self._on_output(event.text, stream)
            return

        if event.event_type == "exit":
            return_code = event.return_code
            terminated_by_user = event.terminated_by_user
            if self._on_session_ended is not None:
                self._on_session_ended(return_code, terminated_by_user)
            self._maybe_auto_restart(terminated_by_user)

    def _maybe_auto_restart(self, terminated_by_user: bool) -> None:
        if not self._auto_restart or self._shutting_down or terminated_by_user:
            return
        now = datetime.now().timestamp()
        self._recent_exit_times = [
            t for t in self._recent_exit_times
            if now - t < _RAPID_RESTART_WINDOW_SECONDS
        ]
        self._recent_exit_times.append(now)
        if len(self._recent_exit_times) >= _MAX_RAPID_RESTARTS:
            _logger.warning(
                "REPL crashed %d times in %.0fs — suppressing auto-restart",
                _MAX_RAPID_RESTARTS,
                _RAPID_RESTART_WINDOW_SECONDS,
            )
            return
        timer = threading.Timer(_AUTO_RESTART_DELAY_SECONDS, self._do_auto_restart)
        timer.daemon = True
        timer.start()

    def _do_auto_restart(self) -> None:
        if self._shutting_down or not self._auto_restart:
            return
        if self._supervisor.is_running():
            return
        _logger.info("Auto-restarting REPL session")
        try:
            self._launch()
        except Exception:
            _logger.exception("Auto-restart of REPL failed")
            return
        if self._on_session_started is not None:
            self._on_session_started()


def _read_json_line(sock: socket.socket) -> dict[str, object]:
    chunks: list[bytes] = []
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        if b"\n" in chunk:
            break
    raw = b"".join(chunks).split(b"\n", 1)[0] + b"\n"
    return loads_message(raw)
