"""Unit tests for debug models and state transitions."""

from __future__ import annotations

import pytest

from app.debug.debug_models import DebugExecutionState, DebugFrame, DebugSessionState, DebugVariable

pytestmark = pytest.mark.unit


def test_debug_session_state_mark_exited_clears_inspector() -> None:
    state = DebugSessionState(
        execution_state=DebugExecutionState.PAUSED,
        stop_reason="breakpoint",
        frames=[DebugFrame(file_path="/tmp/run.py", line_number=12, function_name="main", frame_id=101)],
        selected_frame_id=101,
        variables=[DebugVariable(name="value", value_repr="42")],
        variables_by_reference={7: [DebugVariable(name="child", value_repr="1")]},
    )

    state.mark_exited(message="done")

    assert state.execution_state == DebugExecutionState.EXITED
    assert state.stop_reason == ""
    assert state.last_message == "done"
    assert state.frames == []
    assert state.variables == []
    assert state.variables_by_reference == {}
    assert state.selected_frame_id == 0


def test_selected_frame_falls_back_to_first_frame_when_selection_missing() -> None:
    first = DebugFrame(file_path="/tmp/a.py", line_number=3, function_name="first", frame_id=11)
    second = DebugFrame(file_path="/tmp/b.py", line_number=5, function_name="second", frame_id=22)
    state = DebugSessionState(frames=[first, second], selected_frame_id=999)

    assert state.selected_frame == first


def test_variables_for_reference_returns_copy_of_reference_bucket() -> None:
    variable = DebugVariable(name="child", value_repr="1")
    state = DebugSessionState(variables_by_reference={7: [variable]})

    resolved = state.variables_for_reference(7)
    resolved.append(DebugVariable(name="other", value_repr="2"))

    assert state.variables_by_reference[7] == [variable]
