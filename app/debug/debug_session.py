"""Debug session coordinator for shell-side state tracking."""

from __future__ import annotations

from typing import Mapping

from app.debug.debug_breakpoints import build_breakpoint
from app.debug.debug_event_protocol import parse_debug_output_line
from app.debug.debug_models import (
    DebugBreakpoint,
    DebugEvent,
    DebugExceptionInfo,
    DebugExceptionPolicy,
    DebugExecutionState,
    DebugFrame,
    DebugScope,
    DebugSessionState,
    DebugThread,
    DebugVariable,
    DebugWatchResult,
)


class DebugSession:
    """Tracks debug state from runner output or structured transport messages."""

    def __init__(self) -> None:
        self._state = DebugSessionState()

    @property
    def state(self) -> DebugSessionState:
        return self._state

    def ingest_output_line(self, line: str) -> DebugEvent | None:
        """Parse legacy output line and apply debug events when present."""

        event = parse_debug_output_line(line)
        if event is None:
            return None
        self._state.apply_event(event)
        return event

    def apply_protocol_message(self, payload: Mapping[str, object]) -> None:
        """Apply one structured transport message."""

        kind = str(payload.get("kind", "")).strip()
        if kind == "event":
            self._apply_event_payload(str(payload.get("event", "")), _body(payload))
            return
        if kind == "response":
            self._apply_response_payload(
                str(payload.get("command", "")),
                bool(payload.get("success", False)),
                _body(payload),
                str(payload.get("error_message", "")).strip(),
            )
            return
        if kind == "hello":
            self._state.engine_name = str(payload.get("engine_name", "")).strip()

    def mark_exited(self) -> DebugEvent:
        """Apply and return synthetic exit event."""

        event = DebugEvent(event_type="exited", message="Debug session exited.")
        self._state.apply_event(event)
        self._state.threads = []
        self._state.frames = []
        self._state.scopes = []
        self._state.variables = []
        self._state.variables_by_reference.clear()
        self._state.exception_info = None
        return event

    def _apply_event_payload(self, event_name: str, body: Mapping[str, object]) -> None:
        if event_name == "session_ready":
            self._state.engine_name = str(body.get("engine_name", "")).strip()
            if self._state.execution_state == DebugExecutionState.IDLE:
                self._state.execution_state = DebugExecutionState.RUNNING
            self._state.last_message = str(body.get("message", "")).strip() or "Debug transport ready."
            return
        if event_name == "continued":
            self._state.execution_state = DebugExecutionState.RUNNING
            self._state.stop_reason = ""
            self._state.last_message = str(body.get("message", "")).strip() or "Debug execution running."
            return
        if event_name == "session_ended":
            self.mark_exited()
            self._state.last_message = str(body.get("message", "")).strip() or "Debug session ended."
            return
        if event_name == "breakpoints_updated":
            self._state.breakpoints = _parse_breakpoints(body.get("breakpoints", []))
            return
        if event_name == "stopped":
            self._state.execution_state = DebugExecutionState.PAUSED
            self._state.stop_reason = str(body.get("reason", "")).strip()
            self._state.last_message = str(body.get("message", "")).strip() or "Debug session paused."
            self._state.threads = _parse_threads(body.get("threads", []))
            self._state.selected_thread_id = _parse_int(body.get("selected_thread_id"))
            self._state.frames = _parse_frames(body.get("frames", []))
            self._state.selected_frame_id = _parse_int(body.get("selected_frame_id"))
            self._state.scopes = _parse_scopes(body.get("scopes", []))
            self._state.variables_by_reference = _parse_scope_variables(body.get("scope_variables", {}))
            self._sync_selected_scope_variables()
            self._state.breakpoints = _parse_breakpoints(body.get("breakpoints", [])) or self._state.breakpoints
            self._state.exception_info = _parse_exception_info(body.get("exception"))
            return
        if event_name == "exception_policy":
            self._state.exception_policy = _parse_exception_policy(body)

    def _apply_response_payload(
        self,
        command_name: str,
        success: bool,
        body: Mapping[str, object],
        error_message: str,
    ) -> None:
        if not success:
            if command_name == "evaluate":
                expression = str(body.get("expression", "")).strip()
                if expression:
                    self._state.watch_results[expression] = DebugWatchResult(
                        expression=expression,
                        error_message=error_message or "Evaluation failed.",
                    )
            self._state.last_message = error_message or self._state.last_message
            return

        if command_name == "select_frame":
            self._state.selected_frame_id = _parse_int(body.get("selected_frame_id"))
            self._state.scopes = _parse_scopes(body.get("scopes", []))
            self._state.variables_by_reference.update(_parse_scope_variables(body.get("scope_variables", {})))
            self._sync_selected_scope_variables()
            return
        if command_name == "expand_variable":
            parent_reference = _parse_int(body.get("parent_reference"))
            if parent_reference > 0:
                self._state.variables_by_reference[parent_reference] = _parse_variables(body.get("variables", []))
            return
        if command_name == "evaluate":
            expression = str(body.get("expression", "")).strip()
            result_payload = body.get("result", {})
            if expression:
                variable = _parse_variable(result_payload)
                self._state.watch_results[expression] = DebugWatchResult(
                    expression=expression,
                    value_repr=variable.value_repr,
                    type_name=variable.type_name,
                    variables_reference=variable.variables_reference,
                    error_message=variable.error_message,
                )
            return
        if command_name == "update_breakpoints":
            self._state.breakpoints = _parse_breakpoints(body.get("breakpoints", []))
            return
        if command_name == "update_exception_policy":
            self._state.exception_policy = _parse_exception_policy(body)

    def _sync_selected_scope_variables(self) -> None:
        if not self._state.scopes:
            self._state.variables = []
            return
        for scope in self._state.scopes:
            if scope.variables_reference in self._state.variables_by_reference:
                self._state.variables = list(self._state.variables_by_reference[scope.variables_reference])
                return
        self._state.variables = []


def _body(payload: Mapping[str, object]) -> Mapping[str, object]:
    body = payload.get("body", {})
    return body if isinstance(body, Mapping) else {}


def _parse_threads(raw_value: object) -> list[DebugThread]:
    if not isinstance(raw_value, list):
        return []
    threads: list[DebugThread] = []
    for entry in raw_value:
        if not isinstance(entry, Mapping):
            continue
        threads.append(
            DebugThread(
                thread_id=_parse_int(entry.get("thread_id")),
                name=str(entry.get("name", "")).strip() or "Thread",
                is_current=bool(entry.get("is_current", False)),
            )
        )
    return threads


def _parse_frames(raw_value: object) -> list[DebugFrame]:
    if not isinstance(raw_value, list):
        return []
    frames: list[DebugFrame] = []
    for entry in raw_value:
        if not isinstance(entry, Mapping):
            continue
        file_path = str(entry.get("file_path", "")).strip()
        function_name = str(entry.get("function_name", "")).strip() or "<frame>"
        line_number = _parse_int(entry.get("line_number"))
        if not file_path or line_number <= 0:
            continue
        frames.append(
            DebugFrame(
                file_path=file_path,
                line_number=line_number,
                function_name=function_name,
                frame_id=_parse_int(entry.get("frame_id")),
                thread_id=_parse_int(entry.get("thread_id")),
            )
        )
    return frames


def _parse_scopes(raw_value: object) -> list[DebugScope]:
    if not isinstance(raw_value, list):
        return []
    scopes: list[DebugScope] = []
    for entry in raw_value:
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("name", "")).strip()
        variables_reference = _parse_int(entry.get("variables_reference"))
        if not name or variables_reference <= 0:
            continue
        scopes.append(
            DebugScope(
                name=name,
                variables_reference=variables_reference,
                expensive=bool(entry.get("expensive", False)),
            )
        )
    return scopes


def _parse_variables(raw_value: object) -> list[DebugVariable]:
    if not isinstance(raw_value, list):
        return []
    return [_parse_variable(entry) for entry in raw_value if isinstance(entry, Mapping)]


def _parse_variable(raw_value: object) -> DebugVariable:
    if not isinstance(raw_value, Mapping):
        return DebugVariable(name="<invalid>", value_repr="<invalid variable payload>", error_message="invalid payload")
    return DebugVariable(
        name=str(raw_value.get("name", "")).strip() or "<value>",
        value_repr=str(raw_value.get("value_repr", "")).strip(),
        type_name=str(raw_value.get("type_name", "")).strip(),
        variables_reference=_parse_int(raw_value.get("variables_reference")),
        named_child_count=_parse_optional_int(raw_value.get("named_child_count")),
        indexed_child_count=_parse_optional_int(raw_value.get("indexed_child_count")),
        truncated=bool(raw_value.get("truncated", False)),
        error_message=str(raw_value.get("error_message", "")).strip(),
    )


def _parse_scope_variables(raw_value: object) -> dict[int, list[DebugVariable]]:
    if not isinstance(raw_value, Mapping):
        return {}
    variables_by_reference: dict[int, list[DebugVariable]] = {}
    for key, value in raw_value.items():
        reference = _parse_int(key)
        if reference <= 0:
            continue
        variables_by_reference[reference] = _parse_variables(value)
    return variables_by_reference


def _parse_breakpoints(raw_value: object) -> list[DebugBreakpoint]:
    if not isinstance(raw_value, list):
        return []
    breakpoints: list[DebugBreakpoint] = []
    for entry in raw_value:
        if not isinstance(entry, Mapping):
            continue
        file_path = str(entry.get("file_path", "")).strip()
        line_number = _parse_int(entry.get("line_number"))
        if not file_path or line_number <= 0:
            continue
        breakpoints.append(
            build_breakpoint(
                file_path=file_path,
                line_number=line_number,
                breakpoint_id=str(entry.get("breakpoint_id", "")).strip() or None,
                enabled=bool(entry.get("enabled", True)),
                condition=str(entry.get("condition", "")).strip(),
                hit_condition=_parse_optional_int(entry.get("hit_condition")),
                verified=bool(entry.get("verified", False)),
                verification_message=str(entry.get("verification_message", "")).strip(),
            )
        )
    return breakpoints


def _parse_exception_info(raw_value: object) -> DebugExceptionInfo | None:
    if not isinstance(raw_value, Mapping):
        return None
    type_name = str(raw_value.get("type_name", "")).strip()
    message = str(raw_value.get("message", "")).strip()
    if not type_name and not message:
        return None
    return DebugExceptionInfo(type_name=type_name, message=message)


def _parse_exception_policy(raw_value: object) -> DebugExceptionPolicy:
    if not isinstance(raw_value, Mapping):
        return DebugExceptionPolicy()
    return DebugExceptionPolicy(
        stop_on_uncaught_exceptions=bool(raw_value.get("stop_on_uncaught_exceptions", True)),
        stop_on_raised_exceptions=bool(raw_value.get("stop_on_raised_exceptions", False)),
    )


def _parse_optional_int(raw_value: object) -> int | None:
    value = _parse_int(raw_value)
    return value if value > 0 else None


def _parse_int(raw_value: object) -> int:
    if isinstance(raw_value, int) and not isinstance(raw_value, bool):
        return int(raw_value)
    try:
        return int(str(raw_value))
    except (TypeError, ValueError):
        return 0
