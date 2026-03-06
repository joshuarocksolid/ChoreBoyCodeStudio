"""Debug event protocol parsing helpers."""

from __future__ import annotations

import json

from app.debug.debug_models import DebugEvent, DebugFrame, DebugVariable

DEBUG_EVENT_PREFIX = "__CB_DEBUG_EVENT__"
DEBUG_PAUSED_MARKER = "__CB_DEBUG_PAUSED__"
DEBUG_RUNNING_MARKER = "__CB_DEBUG_RUNNING__"


def parse_debug_output_line(line: str) -> DebugEvent | None:
    """Parse one output line into debug event when marker is present."""
    stripped = line.strip()
    if not stripped:
        return None
    if stripped == DEBUG_PAUSED_MARKER:
        return DebugEvent(event_type="paused", message="Paused at breakpoint.")
    if stripped == DEBUG_RUNNING_MARKER:
        return DebugEvent(event_type="running", message="Debug execution running.")
    if not stripped.startswith(DEBUG_EVENT_PREFIX):
        return None

    payload_text = stripped[len(DEBUG_EVENT_PREFIX) :]
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return DebugEvent(event_type="protocol_error", message="Malformed debug event payload.")

    if not isinstance(payload, dict):
        return DebugEvent(event_type="protocol_error", message="Debug event payload must be an object.")

    event_type = str(payload.get("event_type", "")).strip() or "unknown"
    message = str(payload.get("message", "")).strip()
    frames = _parse_frames(payload.get("frames", []))
    variables = _parse_variables(payload.get("variables", []))
    return DebugEvent(event_type=event_type, message=message, frames=frames, variables=variables)


def format_debug_event(event: DebugEvent) -> str:
    """Serialize debug event to protocol output marker line."""
    payload = {
        "event_type": event.event_type,
        "message": event.message,
        "frames": [
            {"file_path": frame.file_path, "line_number": frame.line_number, "function_name": frame.function_name}
            for frame in event.frames
        ],
        "variables": [{"name": variable.name, "value_repr": variable.value_repr} for variable in event.variables],
    }
    return f"{DEBUG_EVENT_PREFIX}{json.dumps(payload, sort_keys=True)}"


def _parse_frames(raw_frames: object) -> list[DebugFrame]:
    if not isinstance(raw_frames, list):
        return []
    frames: list[DebugFrame] = []
    for frame in raw_frames:
        if not isinstance(frame, dict):
            continue
        file_path = frame.get("file_path")
        function_name = frame.get("function_name")
        line_number = frame.get("line_number")
        if not isinstance(file_path, str) or not isinstance(function_name, str) or not isinstance(line_number, int):
            continue
        frames.append(DebugFrame(file_path=file_path, line_number=line_number, function_name=function_name))
    return frames


def _parse_variables(raw_variables: object) -> list[DebugVariable]:
    if not isinstance(raw_variables, list):
        return []
    variables: list[DebugVariable] = []
    for variable in raw_variables:
        if not isinstance(variable, dict):
            continue
        name = variable.get("name")
        value_repr = variable.get("value_repr")
        if not isinstance(name, str) or not isinstance(value_repr, str):
            continue
        variables.append(DebugVariable(name=name, value_repr=value_repr))
    return variables
