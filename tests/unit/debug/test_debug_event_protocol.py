"""Unit tests for debug event protocol helpers."""

from __future__ import annotations

import pytest

from app.debug.debug_event_protocol import format_debug_event, parse_debug_output_line
from app.debug.debug_models import DebugEvent, DebugFrame, DebugVariable

pytestmark = pytest.mark.unit


def test_parse_debug_output_line_for_markers() -> None:
    paused = parse_debug_output_line("__CB_DEBUG_PAUSED__")
    running = parse_debug_output_line("__CB_DEBUG_RUNNING__")
    assert paused is not None and paused.event_type == "paused"
    assert running is not None and running.event_type == "running"


def test_format_and_parse_debug_event_round_trip() -> None:
    event = DebugEvent(
        event_type="stack",
        message="stack updated",
        frames=[DebugFrame(file_path="/tmp/a.py", line_number=3, function_name="f")],
        variables=[DebugVariable(name="x", value_repr="1")],
    )
    payload_line = format_debug_event(event)
    parsed = parse_debug_output_line(payload_line)
    assert parsed is not None
    assert parsed.event_type == "stack"
    assert parsed.frames[0].line_number == 3
    assert parsed.variables[0].name == "x"
