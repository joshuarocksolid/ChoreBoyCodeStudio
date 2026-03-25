"""Unit tests for debug session coordinator."""

from __future__ import annotations

import pytest

from app.debug.debug_session import DebugSession

pytestmark = pytest.mark.unit


def test_debug_session_ingests_marked_output_events() -> None:
    session = DebugSession()
    paused_event = session.ingest_output_line("__CB_DEBUG_PAUSED__")
    assert paused_event is not None
    assert session.state.execution_state.value == "paused"

    running_event = session.ingest_output_line("__CB_DEBUG_RUNNING__")
    assert running_event is not None
    assert session.state.execution_state.value == "running"


def test_debug_session_mark_exited_updates_state() -> None:
    session = DebugSession()
    exit_event = session.mark_exited()
    assert exit_event.event_type == "exited"
    assert session.state.execution_state.value == "exited"
