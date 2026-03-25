"""Runner-side debug execution helpers."""

from __future__ import annotations

import bdb
import queue
import sys
import threading
from types import FrameType, TracebackType
from typing import Any, Callable, Mapping

from app.core import constants
from app.debug.debug_models import DebugBreakpoint, DebugExceptionPolicy, DebugSourceMap
from app.debug.debug_protocol import build_debug_event, build_debug_response
from app.debug.debug_runtime_probe import probe_debug_runtime
from app.debug.debug_transport import RunnerDebugTransportClient
from app.run.run_manifest import RunManifest

_MAX_TOP_LEVEL_VARS = 100
_MAX_CHILD_VARS = 100
_MAX_REPR_CHARS = 240


class StructuredBdbDebugger(bdb.Bdb):
    """`bdb` engine that delegates pause handling to a structured host."""

    def __init__(self, host: "_RunnerDebugHost") -> None:
        super().__init__()
        self._host = host
        self._pause_requested = False

    def request_pause(self) -> None:
        self._pause_requested = True

    def dispatch_line(self, frame: FrameType):  # type: ignore[override]
        stop_reason = ""
        if self._pause_requested:
            self._pause_requested = False
            stop_reason = "pause"
        else:
            should_stop = self.stop_here(frame)
            should_break = self.break_here(frame)
            if should_break:
                stop_reason = "breakpoint"
            elif should_stop:
                stop_reason = "step"
        if not stop_reason:
            return self.trace_dispatch
        self._host.pause_at_frame(frame=frame, reason=stop_reason, exc_info=None)
        if self.quitting:
            raise bdb.BdbQuit
        return self.trace_dispatch

    def user_return(self, frame: FrameType, _return_value: object) -> None:  # type: ignore[override]
        self._host.pause_at_frame(frame=frame, reason="step", exc_info=None)
        if self.quitting:
            raise bdb.BdbQuit

    def user_exception(self, frame: FrameType, exc_info):  # type: ignore[override,no-untyped-def]
        if self._host.exception_policy.stop_on_raised_exceptions:
            self._host.pause_at_frame(frame=frame, reason="exception", exc_info=exc_info)
            if self.quitting:
                raise bdb.BdbQuit


class _RunnerDebugHost:
    """Runner-side structured debug host backing the socket protocol."""

    def __init__(self, manifest: RunManifest) -> None:
        if manifest.debug_transport is None:
            raise RuntimeError("python_debug manifest missing debug transport configuration.")
        self._manifest = manifest
        self._transport = RunnerDebugTransportClient(
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
        self._selected_frame_id = 0
        self._paused = False
        self._transport_failed = False
        self._last_exception_identity = 0
        self.exception_policy = manifest.debug_exception_policy
        self.debugger = StructuredBdbDebugger(self)

    def connect(self) -> None:
        self._transport.connect()
        decision = probe_debug_runtime()
        self._transport.send_message(
            build_debug_event(
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
        )
        self._transport.send_message(
            build_debug_event(
                "exception_policy",
                {
                    "stop_on_uncaught_exceptions": self.exception_policy.stop_on_uncaught_exceptions,
                    "stop_on_raised_exceptions": self.exception_policy.stop_on_raised_exceptions,
                },
            )
        )
        self._transport.send_message(
            build_debug_event(
                "breakpoints_updated",
                {"breakpoints": self._apply_breakpoints(self._manifest.breakpoints)},
            )
        )

    def close(self) -> None:
        try:
            self._transport.send_message(
                build_debug_event("session_ended", {"message": "Debug session ended."})
            )
        except Exception:
            pass
        self._transport.close()

    def pause_at_frame(
        self,
        *,
        frame: FrameType,
        reason: str,
        exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | None,
    ) -> None:
        self._paused = True
        payload = self._build_pause_payload(frame=frame, reason=reason, exc_info=exc_info)
        self._transport.send_message(build_debug_event("stopped", payload))
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
        frames = _traceback_frames(exc_info[2])
        if not frames:
            return
        self._paused = True
        payload = self._build_traceback_pause_payload(frames=frames, exc_info=exc_info)
        self._transport.send_message(build_debug_event("stopped", payload))
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
        while True:
            message = self._command_queue.get()
            command_name = str(message.get("command", "")).strip()
            arguments = _mapping(message.get("arguments"))
            command_id = str(message.get("command_id", "")).strip()
            if command_name == "continue":
                self.debugger.set_continue()
                self._transport.send_message(build_debug_event("continued", {"message": "Debug execution running."}))
                self._transport.send_message(
                    build_debug_response(
                        command_name=command_name,
                        command_id=command_id,
                        success=True,
                        body={},
                    )
                )
                return
            if allow_stepping and command_name == "step_over":
                self.debugger.set_next(frame)
                self._transport.send_message(build_debug_event("continued", {"message": "Step over."}))
                self._transport.send_message(
                    build_debug_response(command_name=command_name, command_id=command_id, success=True, body={})
                )
                return
            if allow_stepping and command_name == "step_into":
                self.debugger.set_step()
                self._transport.send_message(build_debug_event("continued", {"message": "Step into."}))
                self._transport.send_message(
                    build_debug_response(command_name=command_name, command_id=command_id, success=True, body={})
                )
                return
            if allow_stepping and command_name == "step_out":
                self.debugger.set_return(frame)
                self._transport.send_message(build_debug_event("continued", {"message": "Step out."}))
                self._transport.send_message(
                    build_debug_response(command_name=command_name, command_id=command_id, success=True, body={})
                )
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
                self._transport.send_message(
                    build_debug_response(command_name=command_name, command_id=command_id, success=True, body={})
                )
                return
            self._transport.send_message(
                build_debug_response(
                    command_name=command_name,
                    command_id=command_id,
                    success=False,
                    body={},
                    error_message="Unsupported debug command: %s" % (command_name,),
                )
            )

    def _handle_select_frame(self, *, command_id: str, arguments: Mapping[str, object]) -> None:
        frame_id = _parse_int(arguments.get("frame_id"))
        frame = self._frame_registry.get(frame_id)
        if frame is None:
            self._transport.send_message(
                build_debug_response(
                    command_name="select_frame",
                    command_id=command_id,
                    success=False,
                    body={},
                    error_message="Unknown frame id.",
                )
            )
            return
        self._selected_frame_id = frame_id
        scopes, scope_variables = self._build_scope_payloads(frame)
        self._transport.send_message(
            build_debug_response(
                command_name="select_frame",
                command_id=command_id,
                success=True,
                body={
                    "selected_frame_id": frame_id,
                    "scopes": scopes,
                    "scope_variables": scope_variables,
                },
            )
        )

    def _handle_expand_variable(self, *, command_id: str, arguments: Mapping[str, object]) -> None:
        parent_reference = _parse_int(arguments.get("variables_reference"))
        target = self._object_registry.get(parent_reference)
        if target is None:
            self._transport.send_message(
                build_debug_response(
                    command_name="expand_variable",
                    command_id=command_id,
                    success=False,
                    body={"parent_reference": parent_reference},
                    error_message="Unknown variable reference.",
                )
            )
            return
        variables = self._serialize_children(target)
        self._transport.send_message(
            build_debug_response(
                command_name="expand_variable",
                command_id=command_id,
                success=True,
                body={
                    "parent_reference": parent_reference,
                    "variables": variables,
                },
            )
        )

    def _handle_evaluate(self, *, command_id: str, arguments: Mapping[str, object]) -> None:
        expression = str(arguments.get("expression", "")).strip()
        frame_id = _parse_int(arguments.get("frame_id")) or self._selected_frame_id
        frame = self._frame_registry.get(frame_id)
        if not expression:
            self._transport.send_message(
                build_debug_response(
                    command_name="evaluate",
                    command_id=command_id,
                    success=False,
                    body={"expression": expression},
                    error_message="Expression cannot be empty.",
                )
            )
            return
        if frame is None:
            self._transport.send_message(
                build_debug_response(
                    command_name="evaluate",
                    command_id=command_id,
                    success=False,
                    body={"expression": expression},
                    error_message="Unknown frame id for evaluation.",
                )
            )
            return
        try:
            value = eval(expression, frame.f_globals, frame.f_locals)  # noqa: S307 - debugger evaluate context
            result = self._serialize_variable(expression, value)
            self._transport.send_message(
                build_debug_response(
                    command_name="evaluate",
                    command_id=command_id,
                    success=True,
                    body={"expression": expression, "result": result},
                )
            )
        except Exception as exc:
            self._transport.send_message(
                build_debug_response(
                    command_name="evaluate",
                    command_id=command_id,
                    success=False,
                    body={"expression": expression},
                    error_message="%s: %s" % (type(exc).__name__, exc),
                )
            )

    def _handle_update_breakpoints(self, *, command_id: str, arguments: Mapping[str, object]) -> None:
        breakpoints = _parse_breakpoints(arguments.get("breakpoints", []))
        self._manifest.breakpoints[:] = breakpoints  # type: ignore[misc]
        updated = self._apply_breakpoints(breakpoints)
        self._transport.send_message(
            build_debug_event("breakpoints_updated", {"breakpoints": updated})
        )
        self._transport.send_message(
            build_debug_response(
                command_name="update_breakpoints",
                command_id=command_id,
                success=True,
                body={"breakpoints": updated},
            )
        )

    def _handle_update_exception_policy(self, *, command_id: str, arguments: Mapping[str, object]) -> None:
        self.exception_policy = DebugExceptionPolicy(
            stop_on_uncaught_exceptions=bool(arguments.get("stop_on_uncaught_exceptions", True)),
            stop_on_raised_exceptions=bool(arguments.get("stop_on_raised_exceptions", False)),
        )
        body = {
            "stop_on_uncaught_exceptions": self.exception_policy.stop_on_uncaught_exceptions,
            "stop_on_raised_exceptions": self.exception_policy.stop_on_raised_exceptions,
        }
        self._transport.send_message(build_debug_event("exception_policy", body))
        self._transport.send_message(
            build_debug_response(
                command_name="update_exception_policy",
                command_id=command_id,
                success=True,
                body=body,
            )
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

    def _build_pause_payload(
        self,
        *,
        frame: FrameType,
        reason: str,
        exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | None,
    ) -> dict[str, object]:
        self._reset_pause_state()
        thread_id = threading.get_ident()
        frames = self._collect_frame_chain(frame, thread_id=thread_id)
        self._selected_frame_id = frames[0]["frame_id"] if frames else 0
        scopes, scope_variables = self._build_scope_payloads(frame)
        return {
            "reason": reason,
            "message": _reason_message(reason, exc_info),
            "threads": self._thread_payload(thread_id),
            "selected_thread_id": thread_id,
            "frames": frames,
            "selected_frame_id": self._selected_frame_id,
            "scopes": scopes,
            "scope_variables": scope_variables,
            "breakpoints": self._breakpoint_payloads(self._manifest.breakpoints),
            "exception": _exception_payload(exc_info),
        }

    def _build_traceback_pause_payload(
        self,
        *,
        frames: list[FrameType],
        exc_info: tuple[type[BaseException], BaseException, TracebackType | None],
    ) -> dict[str, object]:
        self._reset_pause_state()
        thread_id = threading.get_ident()
        frame_payloads: list[dict[str, object]] = []
        for frame in frames:
            frame_id = self._register_frame(frame)
            frame_payloads.append(
                {
                    "frame_id": frame_id,
                    "thread_id": thread_id,
                    "file_path": self._display_file_path(frame.f_code.co_filename),
                    "line_number": int(frame.f_lineno),
                    "function_name": str(frame.f_code.co_name),
                }
            )
        self._selected_frame_id = frame_payloads[0]["frame_id"] if frame_payloads else 0  # type: ignore[index]
        scopes, scope_variables = self._build_scope_payloads(frames[0])
        return {
            "reason": "exception",
            "message": _reason_message("exception", exc_info),
            "threads": self._thread_payload(thread_id),
            "selected_thread_id": thread_id,
            "frames": frame_payloads,
            "selected_frame_id": self._selected_frame_id,
            "scopes": scopes,
            "scope_variables": scope_variables,
            "breakpoints": self._breakpoint_payloads(self._manifest.breakpoints),
            "exception": _exception_payload(exc_info),
        }

    def _build_scope_payloads(self, frame: FrameType) -> tuple[list[dict[str, object]], dict[int, list[dict[str, object]]]]:
        scopes: list[dict[str, object]] = []
        scope_variables: dict[int, list[dict[str, object]]] = {}

        locals_reference = self._register_object(dict(frame.f_locals))
        locals_variables = self._serialize_named_mapping(dict(frame.f_locals), limit=_MAX_TOP_LEVEL_VARS)
        scopes.append({"name": "Locals", "variables_reference": locals_reference})
        scope_variables[locals_reference] = locals_variables

        globals_view = _filtered_globals(frame.f_globals)
        globals_reference = self._register_object(globals_view)
        globals_variables = self._serialize_named_mapping(globals_view, limit=_MAX_TOP_LEVEL_VARS)
        scopes.append({"name": "Globals", "variables_reference": globals_reference, "expensive": True})
        scope_variables[globals_reference] = globals_variables

        return scopes, scope_variables

    def _collect_frame_chain(self, frame: FrameType, *, thread_id: int) -> list[dict[str, object]]:
        frames: list[dict[str, object]] = []
        current_frame: FrameType | None = frame
        while current_frame is not None:
            frame_id = self._register_frame(current_frame)
            frames.append(
                {
                    "frame_id": frame_id,
                    "thread_id": thread_id,
                    "file_path": self._display_file_path(current_frame.f_code.co_filename),
                    "line_number": int(current_frame.f_lineno),
                    "function_name": str(current_frame.f_code.co_name),
                }
            )
            current_frame = current_frame.f_back
        return frames

    def _thread_payload(self, current_thread_id: int) -> list[dict[str, object]]:
        payload: list[dict[str, object]] = []
        for thread in threading.enumerate():
            payload.append(
                {
                    "thread_id": int(thread.ident or 0),
                    "name": thread.name,
                    "is_current": int(thread.ident or 0) == current_thread_id,
                }
            )
        if not payload:
            payload.append({"thread_id": current_thread_id, "name": "MainThread", "is_current": True})
        return payload

    def _apply_breakpoints(self, breakpoints: list[DebugBreakpoint]) -> list[dict[str, object]]:
        self.debugger.clear_all_breaks()
        verified_payloads: list[dict[str, object]] = []
        for breakpoint in breakpoints:
            if not breakpoint.enabled:
                verified_payloads.append(
                    {
                        "breakpoint_id": breakpoint.breakpoint_id,
                        "file_path": self._display_file_path(breakpoint.file_path),
                        "line_number": breakpoint.line_number,
                        "enabled": breakpoint.enabled,
                        "condition": breakpoint.condition,
                        "hit_condition": breakpoint.hit_condition,
                        "verified": True,
                        "verification_message": "Disabled",
                    }
                )
                continue
            try:
                result = self.debugger.set_break(
                    breakpoint.file_path,
                    breakpoint.line_number,
                    cond=breakpoint.condition or None,
                )
                if result:
                    verified_payloads.append(
                        {
                            "breakpoint_id": breakpoint.breakpoint_id,
                            "file_path": self._display_file_path(breakpoint.file_path),
                            "line_number": breakpoint.line_number,
                            "enabled": breakpoint.enabled,
                            "condition": breakpoint.condition,
                            "hit_condition": breakpoint.hit_condition,
                            "verified": False,
                            "verification_message": str(result),
                        }
                    )
                    continue
                if breakpoint.hit_condition is not None and breakpoint.hit_condition > 1:
                    canonical_file = self.debugger.canonic(breakpoint.file_path)
                    active_breakpoint = bdb.Breakpoint.bplist[canonical_file, breakpoint.line_number][-1]
                    active_breakpoint.ignore = breakpoint.hit_condition - 1
                verified_payloads.append(
                    {
                        "breakpoint_id": breakpoint.breakpoint_id,
                        "file_path": self._display_file_path(breakpoint.file_path),
                        "line_number": breakpoint.line_number,
                        "enabled": breakpoint.enabled,
                        "condition": breakpoint.condition,
                        "hit_condition": breakpoint.hit_condition,
                        "verified": True,
                        "verification_message": "",
                    }
                )
            except Exception as exc:
                verified_payloads.append(
                    {
                        "breakpoint_id": breakpoint.breakpoint_id,
                        "file_path": self._display_file_path(breakpoint.file_path),
                        "line_number": breakpoint.line_number,
                        "enabled": breakpoint.enabled,
                        "condition": breakpoint.condition,
                        "hit_condition": breakpoint.hit_condition,
                        "verified": False,
                        "verification_message": str(exc),
                    }
                )
        return verified_payloads

    def _breakpoint_payloads(self, breakpoints: list[DebugBreakpoint]) -> list[dict[str, object]]:
        return [
            {
                "breakpoint_id": breakpoint.breakpoint_id,
                "file_path": self._display_file_path(breakpoint.file_path),
                "line_number": breakpoint.line_number,
                "enabled": breakpoint.enabled,
                "condition": breakpoint.condition,
                "hit_condition": breakpoint.hit_condition,
                "verified": breakpoint.verified,
                "verification_message": breakpoint.verification_message,
            }
            for breakpoint in breakpoints
        ]

    def _serialize_named_mapping(self, mapping: Mapping[str, object], *, limit: int) -> list[dict[str, object]]:
        items = sorted(mapping.items(), key=lambda item: item[0])[:limit]
        return [self._serialize_variable(name, value) for name, value in items]

    def _serialize_children(self, value: object) -> list[dict[str, object]]:
        children: list[dict[str, object]] = []
        if isinstance(value, dict):
            items = list(value.items())[:_MAX_CHILD_VARS]
            for child_key, child_value in items:
                children.append(self._serialize_variable(repr(child_key), child_value))
            return children
        if isinstance(value, (list, tuple)):
            for index, child_value in enumerate(list(value)[:_MAX_CHILD_VARS]):
                children.append(self._serialize_variable("[%s]" % (index,), child_value))
            return children
        if isinstance(value, set):
            sorted_values = sorted([repr(item) for item in value])[:_MAX_CHILD_VARS]
            for index, child_value in enumerate(sorted_values):
                children.append(self._serialize_variable("{%s}" % (index,), child_value))
            return children
        if hasattr(value, "__dict__"):
            attributes = sorted(vars(value).items(), key=lambda item: item[0])[:_MAX_CHILD_VARS]
            for child_name, child_value in attributes:
                children.append(self._serialize_variable(child_name, child_value))
        return children

    def _serialize_variable(self, name: str, value: object) -> dict[str, object]:
        type_name = type(value).__name__
        value_repr = _safe_repr(value)
        named_child_count = None
        indexed_child_count = None
        variables_reference = 0
        if isinstance(value, dict):
            named_child_count = len(value)
            variables_reference = self._register_object(value) if value else 0
        elif isinstance(value, (list, tuple)):
            indexed_child_count = len(value)
            variables_reference = self._register_object(value) if value else 0
        elif isinstance(value, set):
            indexed_child_count = len(value)
            variables_reference = self._register_object(value) if value else 0
        elif hasattr(value, "__dict__"):
            named_child_count = len(vars(value))
            variables_reference = self._register_object(value) if vars(value) else 0
        return {
            "name": str(name),
            "value_repr": value_repr,
            "type_name": type_name,
            "variables_reference": variables_reference,
            "named_child_count": named_child_count,
            "indexed_child_count": indexed_child_count,
            "truncated": len(value_repr) >= _MAX_REPR_CHARS,
            "error_message": "",
        }

    def _register_frame(self, frame: FrameType) -> int:
        frame_id = len(self._frame_registry) + 1
        self._frame_registry[frame_id] = frame
        return frame_id

    def _register_object(self, value: object) -> int:
        reference = len(self._object_registry) + 1
        self._object_registry[reference] = value
        return reference

    def _reset_pause_state(self) -> None:
        self._frame_registry.clear()
        self._object_registry.clear()
        self._selected_frame_id = 0

    def _display_file_path(self, runtime_file_path: str) -> str:
        normalized = str(runtime_file_path)
        return self._source_map_by_runtime.get(normalized, normalized)


def run_debug_session(manifest: RunManifest, entry_callable: Callable[[str], None], entry_script_path: str) -> int:
    """Run entry script under structured debugger control."""

    host = _RunnerDebugHost(manifest)
    host.connect()
    threading.settrace(host.debugger.trace_dispatch)
    host.debugger.reset()
    host.debugger._set_stopinfo(None, None, -1)  # noqa: SLF001 - keep tracing active without first-line stop
    try:
        sys.settrace(host.debugger.trace_dispatch)
        entry_callable(entry_script_path)
        return constants.RUN_EXIT_SUCCESS
    except bdb.BdbQuit:
        return constants.RUN_EXIT_TERMINATED_BY_USER
    except Exception:
        exc_info = sys.exc_info()
        if (
            exc_info[0] is not None
            and exc_info[1] is not None
            and exc_info[2] is not None
            and host.exception_policy.stop_on_uncaught_exceptions
        ):
            host.pause_on_uncaught_exception(exc_info)  # type: ignore[arg-type]
        raise
    finally:
        threading.settrace(None)
        sys.settrace(None)
        host.close()


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _parse_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _parse_breakpoints(raw_value: object) -> list[DebugBreakpoint]:
    if not isinstance(raw_value, list):
        return []
    breakpoints: list[DebugBreakpoint] = []
    for entry in raw_value:
        if not isinstance(entry, Mapping):
            continue
        file_path = entry.get("file_path")
        line_number = entry.get("line_number")
        if not isinstance(file_path, str) or not isinstance(line_number, int):
            continue
        breakpoints.append(
            DebugBreakpoint(
                breakpoint_id=str(entry.get("breakpoint_id", "")).strip() or "%s:%s" % (file_path, line_number),
                file_path=file_path,
                line_number=line_number,
                enabled=bool(entry.get("enabled", True)),
                condition=str(entry.get("condition", "")).strip(),
                hit_condition=_parse_int(entry.get("hit_condition")) or None,
                verified=False,
                verification_message="",
            )
        )
    return breakpoints


def _reason_message(
    reason: str,
    exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | None,
) -> str:
    if reason == "breakpoint":
        return "Paused at breakpoint."
    if reason == "pause":
        return "Pause requested."
    if reason == "step":
        return "Stepped to next location."
    if reason == "exception" and exc_info is not None:
        return "%s: %s" % (exc_info[0].__name__, exc_info[1])
    return "Paused."


def _exception_payload(
    exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | None,
) -> dict[str, object] | None:
    if exc_info is None:
        return None
    return {
        "type_name": exc_info[0].__name__,
        "message": str(exc_info[1]),
    }


def _traceback_frames(traceback_obj: TracebackType | None) -> list[FrameType]:
    frames: list[FrameType] = []
    current = traceback_obj
    while current is not None:
        frames.append(current.tb_frame)
        current = current.tb_next
    return list(reversed(frames))


def _filtered_globals(raw_globals: Mapping[str, object]) -> dict[str, object]:
    filtered = {name: value for name, value in raw_globals.items() if not name.startswith("__")}
    return filtered or dict(raw_globals)


def _safe_repr(value: object) -> str:
    try:
        rendered = repr(value)
    except Exception as exc:
        rendered = "<repr failed: %s: %s>" % (type(exc).__name__, exc)
    if len(rendered) <= _MAX_REPR_CHARS:
        return rendered
    return "%s..." % (rendered[: _MAX_REPR_CHARS - 3],)
