"""Unit tests for debug models and state transitions."""

from __future__ import annotations

import pytest

from app.debug.debug_models import DebugEvent, DebugExecutionState, DebugFrame, DebugSessionState, DebugVariable

pytestmark = pytest.mark.unit


def test_debug_session_state_applies_running_and_paused_events() -> None:
    state = DebugSessionState()
    state.apply_event(DebugEvent(event_type="running", message="running"))
    assert state.execution_state == DebugExecutionState.RUNNING
    state.apply_event(DebugEvent(event_type="paused", message="paused"))
    assert state.execution_state == DebugExecutionState.PAUSED
    assert state.last_message == "paused"


def test_debug_session_state_updates_frames_and_variables() -> None:
    state = DebugSessionState()
    frame = DebugFrame(file_path="/tmp/run.py", line_number=12, function_name="main")
    variable = DebugVariable(name="value", value_repr="42")
    state.apply_event(DebugEvent(event_type="paused", frames=[frame], variables=[variable]))
    assert state.frames == [frame]
    assert state.variables == [variable]
