"""Pause loop, command dispatch, and transport helpers for runner debug."""

from __future__ import annotations

import queue
from types import FrameType, TracebackType
from typing import Mapping

from app.debug.debug_models import DebugExceptionPolicy
from app.debug.debug_protocol import build_debug_event, build_debug_response
from app.debug.debug_runtime_probe import probe_debug_runtime
from app.run.run_manifest import RunManifest
from app.runner.debug.breakpoints import BreakpointMixin
from app.runner.debug.engine import StructuredBdbDebugger
from app.runner.debug.helpers import mapping, traceback_frames
from app.runner.debug.inspector import InspectorMixin
from app.runner.debug.pause_payloads import PausePayloadMixin

_PAUSE_COMMAND_TIMEOUT_SEC = 0.5


class RunnerDebugHost(PausePayloadMixin, BreakpointMixin, InspectorMixin):
    """Runner-side structured debug host backing the socket protocol."""

    def __init__(self, manifest: RunManifest) -> None:
        if manifest.debug_transport is None:
            raise RuntimeError("python_debug manifest missing debug transport configuration.")
        from app.runner import debug_runner as debug_runner_facade

        self._manifest = manifest
        self._transport = debug_runner_facade.RunnerDebugTransportClient(
            manifest.debug_transport,
            engine_name="bdb",
            on_message=self._handle_transport_message,
            on_error=self._handle_transport_error,
        )
        self._command_queue: "queue.Queue[dict[str, object]]" = queue.Queue()
        self._source_map_by_runtime = {
            source_map.runtime_path: source_map.source_path for source_map in manifest.source_maps
        }
        self._frame_registry: dict[int, FrameType] = {}
        self._object_registry: dict[int, object] = {}
        self._selected_frame_id: int = 0
        self._paused = False
        self._transport_failed = False
        self._last_exception_identity = 0
        self.exception_policy = manifest.debug_exception_policy
        self.debugger = StructuredBdbDebugger(self)

    def connect(self) -> None:
        self._transport.connect()
        decision = probe_debug_runtime()
        self._send_event(
            "session_ready",
            {
                "engine_name": decision.chosen_engine,
                "message": "Structured debug transport connected.",
                "supports_python_threads": decision.supports_python_threads,
                "supports_qthread_breakpoints": decision.supports_qthread_breakpoints,
                "debugpy_available": decision.debugpy_available,
                "debugpy_rejection_reason": decision.debugpy_rejection_reason,
            },
        )
        self._send_event(
            "exception_policy",
            {
                "stop_on_uncaught_exceptions": self.exception_policy.stop_on_uncaught_exceptions,
                "stop_on_raised_exceptions": self.exception_policy.stop_on_raised_exceptions,
            },
        )
        self._send_event(
            "breakpoints_updated",
            {"breakpoints": self._apply_breakpoints(self._manifest.breakpoints)},
        )

    def close(self) -> None:
        self._send_event("session_ended", {"message": "Debug session ended."})
        self._transport.close()

    def _send_event(self, event_name: str, body: Mapping[str, object]) -> None:
        if self._transport_failed:
            return
        try:
            self._transport.send_message(build_debug_event(event_name, body))
        except (OSError, RuntimeError) as exc:
            self._handle_transport_error("Debug transport write failed: %s" % (exc,))

    def _send_response(
        self,
        *,
        command_name: str,
        command_id: str,
        success: bool,
        body: Mapping[str, object],
        error_message: str = "",
    ) -> None:
        if self._transport_failed:
            return
        try:
            self._transport.send_message(
                build_debug_response(
                    command_name=command_name,
                    command_id=command_id,
                    success=success,
                    body=body,
                    error_message=error_message,
                )
            )
        except (OSError, RuntimeError) as exc:
            self._handle_transport_error("Debug transport write failed: %s" % (exc,))

    def pause_at_frame(
        self,
        *,
        frame: FrameType,
        reason: str,
        exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | None,
    ) -> None:
        self._paused = True
        payload = self._build_pause_payload(frame=frame, reason=reason, exc_info=exc_info)
        self._send_event("stopped", payload)
        if self._transport_failed:
            return
        try:
            self._pause_loop(frame=frame, exc_info=exc_info, allow_stepping=True)
        finally:
            self._paused = False

    def pause_on_uncaught_exception(
        self,
        exc_info: tuple[type[BaseException], BaseException, TracebackType | None],
    ) -> None:
        if not self.exception_policy.stop_on_uncaught_exceptions:
            return
        if id(exc_info[1]) == self._last_exception_identity:
            return
        self._last_exception_identity = id(exc_info[1])
        frames = traceback_frames(exc_info[2])
        if not frames:
            return
        self._paused = True
        payload = self._build_traceback_pause_payload(frames=frames, exc_info=exc_info)
        self._send_event("stopped", payload)
        if self._transport_failed:
            return
        try:
            self._pause_loop(frame=frames[0], exc_info=exc_info, allow_stepping=False)
        finally:
            self._paused = False

    def _pause_loop(
        self,
        *,
        frame: FrameType,
        exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | None,
        allow_stepping: bool,
    ) -> None:
        while not self._transport_failed:
            try:
                message = self._command_queue.get(timeout=_PAUSE_COMMAND_TIMEOUT_SEC)
            except queue.Empty:
                continue
            command_name = str(message.get("command", "")).strip()
            arguments = mapping(message.get("arguments"))
            command_id = str(message.get("command_id", "")).strip()
            if command_name == "continue":
                self.debugger.set_continue()
                self._send_event("continued", {"message": "Debug execution running."})
                self._send_response(
                    command_name=command_name,
                    command_id=command_id,
                    success=True,
                    body={},
                )
                return
            if allow_stepping and command_name == "step_over":
                self.debugger.set_next(frame)
                self._send_event("continued", {"message": "Step over."})
                self._send_response(command_name=command_name, command_id=command_id, success=True, body={})
                return
            if allow_stepping and command_name == "step_into":
                self.debugger.set_step()
                self._send_event("continued", {"message": "Step into."})
                self._send_response(command_name=command_name, command_id=command_id, success=True, body={})
                return
            if allow_stepping and command_name == "step_out":
                self.debugger.set_return(frame)
                self._send_event("continued", {"message": "Step out."})
                self._send_response(command_name=command_name, command_id=command_id, success=True, body={})
                return
            if command_name == "select_frame":
                self._handle_select_frame(command_id=command_id, arguments=arguments)
                continue
            if command_name == "expand_variable":
                self._handle_expand_variable(command_id=command_id, arguments=arguments)
                continue
            if command_name == "evaluate":
                self._handle_evaluate(command_id=command_id, arguments=arguments)
                continue
            if command_name == "update_breakpoints":
                self._handle_update_breakpoints(command_id=command_id, arguments=arguments)
                continue
            if command_name == "update_exception_policy":
                self._handle_update_exception_policy(command_id=command_id, arguments=arguments)
                continue
            if command_name == "disconnect":
                self.debugger.set_quit()
                self._send_response(
                    command_name=command_name,
                    command_id=command_id,
                    success=True,
                    body={},
                )
                return
            self._send_response(
                command_name=command_name,
                command_id=command_id,
                success=False,
                body={},
                error_message="Unsupported debug command: %s" % (command_name,),
            )
        self.debugger.set_quit()

    def _handle_update_exception_policy(self, *, command_id: str, arguments: Mapping[str, object]) -> None:
        self.exception_policy = DebugExceptionPolicy(
            stop_on_uncaught_exceptions=bool(arguments.get("stop_on_uncaught_exceptions", True)),
            stop_on_raised_exceptions=bool(arguments.get("stop_on_raised_exceptions", False)),
        )
        body = {
            "stop_on_uncaught_exceptions": self.exception_policy.stop_on_uncaught_exceptions,
            "stop_on_raised_exceptions": self.exception_policy.stop_on_raised_exceptions,
        }
        self._send_event("exception_policy", body)
        self._send_response(
            command_name="update_exception_policy",
            command_id=command_id,
            success=True,
            body=body,
        )

    def _handle_transport_message(self, message: dict[str, object]) -> None:
        if str(message.get("kind", "")).strip() != "command":
            return
        command_name = str(message.get("command", "")).strip()
        if command_name == "pause" and not self._paused:
            self.debugger.request_pause()
            return
        self._command_queue.put(dict(message))

    def _handle_transport_error(self, _message: str) -> None:
        self._transport_failed = True
        self._command_queue.put({"command": "disconnect", "command_id": "transport_disconnect", "arguments": {}})
