"""Unit tests for structured debug command helpers."""

from __future__ import annotations

import pytest

from app.debug.debug_breakpoints import build_breakpoint
from app.debug.debug_command_service import (
    continue_command,
    evaluate_command,
    expand_variable_command,
    pause_command,
    select_frame_command,
    step_into_command,
    step_out_command,
    step_over_command,
    update_breakpoints_command,
    update_exception_policy_command,
)
from app.debug.debug_models import DebugExceptionPolicy

pytestmark = pytest.mark.unit


def test_control_command_helpers_return_structured_commands() -> None:
    assert continue_command() == ("continue", {})
    assert pause_command() == ("pause", {})
    assert step_over_command() == ("step_over", {})
    assert step_into_command() == ("step_into", {})
    assert step_out_command() == ("step_out", {})
    assert select_frame_command(44) == ("select_frame", {"frame_id": 44})
    assert expand_variable_command(17) == ("expand_variable", {"variables_reference": 17})


def test_evaluate_command_trims_expression_and_carries_frame_id() -> None:
    assert evaluate_command(" value + 1 ", frame_id=22) == (
        "evaluate",
        {"expression": "value + 1", "frame_id": 22, "unsafe": False},
    )
    assert evaluate_command("  ") == ("evaluate", {"expression": "", "frame_id": 0, "unsafe": False})
    assert evaluate_command("danger()", unsafe=True) == (
        "evaluate",
        {"expression": "danger()", "frame_id": 0, "unsafe": True},
    )


def test_update_breakpoints_command_serializes_breakpoint_models() -> None:
    breakpoint = build_breakpoint(
        "/tmp/project/main.py",
        9,
        condition="x > 3",
        hit_condition=5,
    )

    command_name, payload = update_breakpoints_command([breakpoint])

    assert command_name == "update_breakpoints"
    assert payload == {
        "breakpoints": [
            {
                "breakpoint_id": breakpoint.breakpoint_id,
                "file_path": breakpoint.file_path,
                "line_number": 9,
                "enabled": True,
                "condition": "x > 3",
                "hit_condition": 5,
            }
        ]
    }


def test_update_exception_policy_command_serializes_policy_flags() -> None:
    policy = DebugExceptionPolicy(
        stop_on_uncaught_exceptions=False,
        stop_on_raised_exceptions=True,
    )

    assert update_exception_policy_command(policy) == (
        "update_exception_policy",
        {
            "stop_on_uncaught_exceptions": False,
            "stop_on_raised_exceptions": True,
        },
    )
