"""Debug session coordinator for shell-side state tracking."""

from __future__ import annotations

from app.debug.debug_event_protocol import parse_debug_output_line
from app.debug.debug_models import DebugEvent, DebugSessionState


class DebugSession:
    """Tracks debug state from runner output events."""

    def __init__(self) -> None:
        self._state = DebugSessionState()

    @property
    def state(self) -> DebugSessionState:
        return self._state

    def ingest_output_line(self, line: str) -> DebugEvent | None:
        """Parse output line and apply debug events when present."""
        event = parse_debug_output_line(line)
        if event is None:
            return None
        self._state.apply_event(event)
        return event

    def mark_exited(self) -> DebugEvent:
        """Apply and return synthetic exit event."""
        event = DebugEvent(event_type="exited", message="Debug session exited.")
        self._state.apply_event(event)
        return event
