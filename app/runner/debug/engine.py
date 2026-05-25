"""bdb trace engine for structured runner debug sessions."""

from __future__ import annotations

import bdb
from types import FrameType
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:

    class DebugPauseHost(Protocol):
        exception_policy: object

        def pause_at_frame(
            self,
            *,
            frame: FrameType,
            reason: str,
            exc_info: tuple[type[BaseException], BaseException, object | None] | None,
        ) -> None: ...


class StructuredBdbDebugger(bdb.Bdb):
    """`bdb` engine that delegates pause handling to a structured host."""

    def __init__(self, host: "DebugPauseHost") -> None:
        super().__init__()
        self._host = host
        self._pause_requested = False

    def request_pause(self) -> None:
        self._pause_requested = True

    def dispatch_line(self, frame: FrameType):  # type: ignore[override]
        stop_reason = ""
        if self._pause_requested:
            self._pause_requested = False
            stop_reason = "pause"
        else:
            should_stop = self.stop_here(frame)
            should_break = self.break_here(frame)
            if should_break:
                stop_reason = "breakpoint"
            elif should_stop:
                stop_reason = "step"
        if not stop_reason:
            return self.trace_dispatch
        self._host.pause_at_frame(frame=frame, reason=stop_reason, exc_info=None)
        if self.quitting:
            raise bdb.BdbQuit
        return self.trace_dispatch

    def user_return(self, frame: FrameType, _return_value: object) -> None:  # type: ignore[override]
        self._host.pause_at_frame(frame=frame, reason="step", exc_info=None)
        if self.quitting:
            raise bdb.BdbQuit

    def user_exception(self, frame: FrameType, exc_info):  # type: ignore[override,no-untyped-def]
        if self._host.exception_policy.stop_on_raised_exceptions:
            self._host.pause_at_frame(frame=frame, reason="exception", exc_info=exc_info)
            if self.quitting:
                raise bdb.BdbQuit
