"""Unit tests for structured debug session coordination."""

from __future__ import annotations

import pytest

from app.debug.debug_breakpoints import build_breakpoint
from app.debug.debug_session import DebugSession

pytestmark = pytest.mark.unit


def test_debug_session_ingests_legacy_output_markers_for_transition_path() -> None:
    session = DebugSession()

    paused_event = session.ingest_output_line("__CB_DEBUG_PAUSED__")
    running_event = session.ingest_output_line("__CB_DEBUG_RUNNING__")

    assert paused_event is not None
    assert running_event is not None
    assert session.state.execution_state.value == "running"


def test_apply_protocol_message_tracks_session_ready_and_stopped_state() -> None:
    session = DebugSession()
    breakpoint_model = build_breakpoint("/tmp/project/main.py", 12, verified=True)

    session.apply_protocol_message(
        {
            "kind": "event",
            "event": "session_ready",
            "body": {
                "engine_name": "bdb",
                "message": "Structured debug transport connected.",
            },
        }
    )
    session.apply_protocol_message(
        {
            "kind": "event",
            "event": "stopped",
            "body": {
                "reason": "breakpoint",
                "message": "Paused at breakpoint.",
                "threads": [
                    {"thread_id": 1, "name": "MainThread", "is_current": True},
                    {"thread_id": 2, "name": "worker", "is_current": False},
                ],
                "selected_thread_id": 1,
                "frames": [
                    {
                        "frame_id": 101,
                        "thread_id": 1,
                        "file_path": "/tmp/project/main.py",
                        "line_number": 12,
                        "function_name": "main",
                    }
                ],
                "selected_frame_id": 101,
                "scopes": [{"name": "Locals", "variables_reference": 1}],
                "scope_variables": {
                    "1": [
                        {
                            "name": "value",
                            "value_repr": "42",
                            "type_name": "int",
                        }
                    ]
                },
                "breakpoints": [
                    {
                        "breakpoint_id": breakpoint_model.breakpoint_id,
                        "file_path": breakpoint_model.file_path,
                        "line_number": breakpoint_model.line_number,
                        "enabled": True,
                        "verified": True,
                    }
                ],
                "exception": {"type_name": "ValueError", "message": "boom"},
            },
        }
    )

    assert session.state.engine_name == "bdb"
    assert session.state.execution_state.value == "paused"
    assert session.state.stop_reason == "breakpoint"
    assert session.state.selected_thread_id == 1
    assert session.state.selected_frame_id == 101
    assert session.state.selected_frame is not None
    assert session.state.selected_frame.function_name == "main"
    assert session.state.variables[0].name == "value"
    assert session.state.breakpoints[0].breakpoint_id == breakpoint_model.breakpoint_id
    assert session.state.exception_info is not None
    assert session.state.exception_info.type_name == "ValueError"


def test_apply_protocol_message_updates_selected_frame_and_watch_results() -> None:
    session = DebugSession()
    session.apply_protocol_message(
        {
            "kind": "response",
            "command": "select_frame",
            "success": True,
            "body": {
                "selected_frame_id": 22,
                "scopes": [{"name": "Locals", "variables_reference": 7}],
                "scope_variables": {
                    "7": [
                        {
                            "name": "name",
                            "value_repr": "'hello'",
                            "type_name": "str",
                        }
                    ]
                },
            },
        }
    )
    session.apply_protocol_message(
        {
            "kind": "response",
            "command": "evaluate",
            "success": True,
            "body": {
                "expression": "name.upper()",
                "result": {
                    "name": "name.upper()",
                    "value_repr": "'HELLO'",
                    "type_name": "str",
                    "variables_reference": 0,
                },
            },
        }
    )
    session.apply_protocol_message(
        {
            "kind": "response",
            "command": "evaluate",
            "success": False,
            "body": {"expression": "missing"},
            "error_message": "NameError: missing",
        }
    )

    assert session.state.selected_frame_id == 22
    assert session.state.variables[0].name == "name"
    assert session.state.watch_results["name.upper()"].value_repr == "'HELLO'"
    assert session.state.watch_results["missing"].error_message == "NameError: missing"


def test_apply_protocol_message_expands_variable_children_and_updates_exception_policy() -> None:
    session = DebugSession()

    session.apply_protocol_message(
        {
            "kind": "response",
            "command": "expand_variable",
            "success": True,
            "body": {
                "parent_reference": 9,
                "variables": [
                    {"name": "answer", "value_repr": "42", "type_name": "int"},
                ],
            },
        }
    )
    session.apply_protocol_message(
        {
            "kind": "event",
            "event": "exception_policy",
            "body": {
                "stop_on_uncaught_exceptions": False,
                "stop_on_raised_exceptions": True,
            },
        }
    )

    assert session.state.variables_by_reference[9][0].name == "answer"
    assert session.state.exception_policy.stop_on_uncaught_exceptions is False
    assert session.state.exception_policy.stop_on_raised_exceptions is True


def test_debug_session_mark_exited_clears_inspector_state() -> None:
    session = DebugSession()
    session.state.frames = [session.state.selected_frame] if session.state.selected_frame is not None else []
    session.state.variables_by_reference[1] = []
    session.state.scopes = []

    exit_event = session.mark_exited()

    assert exit_event.event_type == "exited"
    assert session.state.execution_state.value == "exited"
    assert session.state.frames == []
    assert session.state.variables_by_reference == {}
