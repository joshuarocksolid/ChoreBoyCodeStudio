"""Debug session models and state transitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DebugExecutionState(str, Enum):
    """High-level debug execution state."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    EXITED = "exited"


@dataclass(frozen=True)
class DebugFrame:
    """One call-stack frame entry."""

    file_path: str
    line_number: int
    function_name: str


@dataclass(frozen=True)
class DebugVariable:
    """One visible debug variable."""

    name: str
    value_repr: str


@dataclass(frozen=True)
class DebugEvent:
    """Normalized debug event payload."""

    event_type: str
    message: str = ""
    frames: list[DebugFrame] = field(default_factory=list)
    variables: list[DebugVariable] = field(default_factory=list)


@dataclass
class DebugSessionState:
    """Mutable debug session state aggregator."""

    execution_state: DebugExecutionState = DebugExecutionState.IDLE
    last_message: str = ""
    frames: list[DebugFrame] = field(default_factory=list)
    variables: list[DebugVariable] = field(default_factory=list)

    def apply_event(self, event: DebugEvent) -> None:
        """Apply event into session state."""
        if event.event_type == "paused":
            self.execution_state = DebugExecutionState.PAUSED
        elif event.event_type == "running":
            self.execution_state = DebugExecutionState.RUNNING
        elif event.event_type == "exited":
            self.execution_state = DebugExecutionState.EXITED

        if event.frames:
            self.frames = list(event.frames)
        if event.variables:
            self.variables = list(event.variables)
        if event.message:
            self.last_message = event.message
