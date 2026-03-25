"""Unit tests for debug models and state transitions."""

from __future__ import annotations

import pytest

from app.debug.debug_models import DebugEvent, DebugExecutionState, DebugFrame, DebugSessionState, DebugVariable

pytestmark = pytest.mark.unit


def test_debug_session_state_applies_legacy_events() -> None:
    state = DebugSessionState()

    state.apply_event(DebugEvent(event_type="running", message="running"))
    assert state.execution_state == DebugExecutionState.RUNNING
    assert state.stop_reason == ""

    state.apply_event(DebugEvent(event_type="paused", message="paused"))
    assert state.execution_state == DebugExecutionState.PAUSED
    assert state.stop_reason == "breakpoint"
    assert state.last_message == "paused"

    state.apply_event(DebugEvent(event_type="exited", message="done"))
    assert state.execution_state == DebugExecutionState.EXITED
    assert state.stop_reason == ""
    assert state.last_message == "done"


def test_debug_session_state_updates_frames_variables_and_selected_frame() -> None:
    state = DebugSessionState()
    frame = DebugFrame(
        file_path="/tmp/run.py",
        line_number=12,
        function_name="main",
        frame_id=101,
        thread_id=1,
    )
    variable = DebugVariable(name="value", value_repr="42")

    state.apply_event(DebugEvent(event_type="paused", frames=[frame], variables=[variable]))

    assert state.frames == [frame]
    assert state.variables == [variable]
    assert state.selected_frame_id == 101
    assert state.selected_frame == frame


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
