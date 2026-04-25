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
class DebugTransportConfig:
    """Socket transport contract for one debug session."""

    protocol: str
    host: str
    port: int
    session_token: str
    connect_timeout_ms: int = 8000


@dataclass(frozen=True)
class DebugExceptionPolicy:
    """Configurable exception stop behavior."""

    stop_on_uncaught_exceptions: bool = True
    stop_on_raised_exceptions: bool = False


@dataclass(frozen=True)
class DebugSourceMap:
    """Maps runner-side transient paths back to real editor files."""

    runtime_path: str
    source_path: str


@dataclass(frozen=True)
class DebugBreakpoint:
    """One breakpoint definition or verification result."""

    breakpoint_id: str
    file_path: str
    line_number: int
    enabled: bool = True
    condition: str = ""
    hit_condition: int | None = None
    verified: bool = False
    verification_message: str = ""


@dataclass(frozen=True)
class DebugThread:
    """One thread visible to the debug inspector."""

    thread_id: int
    name: str
    is_current: bool = False


@dataclass(frozen=True)
class DebugFrame:
    """One call-stack frame entry."""

    file_path: str
    line_number: int
    function_name: str
    frame_id: int = 0
    thread_id: int = 0


@dataclass(frozen=True)
class DebugScope:
    """One scope group for a selected frame."""

    name: str
    variables_reference: int
    expensive: bool = False


@dataclass(frozen=True)
class DebugVariable:
    """One visible debug variable."""

    name: str
    value_repr: str
    type_name: str = ""
    variables_reference: int = 0
    named_child_count: int | None = None
    indexed_child_count: int | None = None
    truncated: bool = False
    error_message: str = ""


@dataclass(frozen=True)
class DebugExceptionInfo:
    """Exception payload for paused debugger state."""

    type_name: str
    message: str


@dataclass(frozen=True)
class DebugWatchResult:
    """Evaluation result for a watch expression."""

    expression: str
    value_repr: str = ""
    type_name: str = ""
    variables_reference: int = 0
    error_message: str = ""


@dataclass(frozen=True)
class DebugEvent:
    """Normalized debug event payload for editor-side session state.

    The runner speaks over the structured debug transport; editor code and tests
    use :class:`DebugEvent` to aggregate or replay debugger updates into
    :class:`DebugSessionState`.
    """

    event_type: str
    message: str = ""
    frames: list[DebugFrame] = field(default_factory=list)
    variables: list[DebugVariable] = field(default_factory=list)


@dataclass
class DebugSessionState:
    """Mutable debug session state aggregator."""

    execution_state: DebugExecutionState = DebugExecutionState.IDLE
    last_message: str = ""
    engine_name: str = ""
    stop_reason: str = ""
    threads: list[DebugThread] = field(default_factory=list)
    selected_thread_id: int = 0
    frames: list[DebugFrame] = field(default_factory=list)
    selected_frame_id: int = 0
    scopes: list[DebugScope] = field(default_factory=list)
    variables: list[DebugVariable] = field(default_factory=list)
    variables_by_reference: dict[int, list[DebugVariable]] = field(default_factory=dict)
    watch_results: dict[str, DebugWatchResult] = field(default_factory=dict)
    breakpoints: list[DebugBreakpoint] = field(default_factory=list)
    exception_info: DebugExceptionInfo | None = None
    exception_policy: DebugExceptionPolicy = field(default_factory=DebugExceptionPolicy)

    @property
    def selected_frame(self) -> DebugFrame | None:
        for frame in self.frames:
            if self.selected_frame_id and frame.frame_id == self.selected_frame_id:
                return frame
        return self.frames[0] if self.frames else None

    def variables_for_reference(self, variables_reference: int) -> list[DebugVariable]:
        return list(self.variables_by_reference.get(int(variables_reference), []))

    def apply_event(self, event: DebugEvent) -> None:
        """Merge a :class:`DebugEvent` into live session state (frames, variables, status)."""
        if event.event_type == "paused":
            self.execution_state = DebugExecutionState.PAUSED
            self.stop_reason = "breakpoint"
        elif event.event_type == "running":
            self.execution_state = DebugExecutionState.RUNNING
            self.stop_reason = ""
        elif event.event_type == "exited":
            self.execution_state = DebugExecutionState.EXITED
            self.stop_reason = ""

        if event.frames:
            self.frames = list(event.frames)
            self.selected_frame_id = self.frames[0].frame_id
        if event.variables:
            self.variables = list(event.variables)
        if event.message:
            self.last_message = event.message
