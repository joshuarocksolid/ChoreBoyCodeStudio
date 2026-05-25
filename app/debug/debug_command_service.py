"""Structured debug command helpers."""

from __future__ import annotations

from app.debug.debug_breakpoints import breakpoint_to_wire_dict
from app.debug.debug_models import DebugBreakpoint, DebugExceptionPolicy


def continue_command() -> tuple[str, dict[str, object]]:
    return ("continue", {})


def pause_command() -> tuple[str, dict[str, object]]:
    return ("pause", {})


def step_over_command() -> tuple[str, dict[str, object]]:
    return ("step_over", {})


def step_into_command() -> tuple[str, dict[str, object]]:
    return ("step_into", {})


def step_out_command() -> tuple[str, dict[str, object]]:
    return ("step_out", {})


def select_frame_command(frame_id: int) -> tuple[str, dict[str, object]]:
    return ("select_frame", {"frame_id": int(frame_id)})


def expand_variable_command(variables_reference: int) -> tuple[str, dict[str, object]]:
    return ("expand_variable", {"variables_reference": int(variables_reference)})


def evaluate_command(
    expression: str,
    *,
    frame_id: int = 0,
    unsafe: bool = False,
) -> tuple[str, dict[str, object]]:
    return (
        "evaluate",
        {
            "expression": expression.strip(),
            "frame_id": int(frame_id),
            "unsafe": bool(unsafe),
        },
    )


def update_breakpoints_command(breakpoints: list[DebugBreakpoint]) -> tuple[str, dict[str, object]]:
    payload = [breakpoint_to_wire_dict(breakpoint) for breakpoint in breakpoints]
    return ("update_breakpoints", {"breakpoints": payload})


def update_exception_policy_command(policy: DebugExceptionPolicy) -> tuple[str, dict[str, object]]:
    return (
        "update_exception_policy",
        {
            "stop_on_uncaught_exceptions": policy.stop_on_uncaught_exceptions,
            "stop_on_raised_exceptions": policy.stop_on_raised_exceptions,
        },
    )
