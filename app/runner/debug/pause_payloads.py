"""Stopped-event payload builders for runner debug sessions."""

from __future__ import annotations

import threading
from types import FrameType, TracebackType

from app.runner.debug.helpers import exception_payload, parse_int, reason_message


class PausePayloadMixin:
    """Build transport payloads when the runner enters a paused state."""

    def _build_pause_payload(
        self,
        *,
        frame: FrameType,
        reason: str,
        exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | None,
    ) -> dict[str, object]:
        self._reset_pause_state()
        thread_id = threading.get_ident()
        frames = self._collect_frame_chain(frame, thread_id=thread_id)
        self._selected_frame_id = parse_int(frames[0]["frame_id"]) if frames else 0
        scopes, scope_variables = self._build_scope_payloads(frame)
        return self._compose_pause_payload(
            reason=reason,
            exc_info=exc_info,
            thread_id=thread_id,
            frames=frames,
            scopes=scopes,
            scope_variables=scope_variables,
        )

    def _build_traceback_pause_payload(
        self,
        *,
        frames: list[FrameType],
        exc_info: tuple[type[BaseException], BaseException, TracebackType | None],
    ) -> dict[str, object]:
        self._reset_pause_state()
        thread_id = threading.get_ident()
        frame_payloads: list[dict[str, object]] = []
        for frame in frames:
            frame_id = self._register_frame(frame)
            frame_payloads.append(
                {
                    "frame_id": frame_id,
                    "thread_id": thread_id,
                    "file_path": self._display_file_path(frame.f_code.co_filename),
                    "line_number": int(frame.f_lineno),
                    "function_name": str(frame.f_code.co_name),
                }
            )
        self._selected_frame_id = parse_int(frame_payloads[0]["frame_id"]) if frame_payloads else 0
        scopes, scope_variables = self._build_scope_payloads(frames[0])
        return self._compose_pause_payload(
            reason="exception",
            exc_info=exc_info,
            thread_id=thread_id,
            frames=frame_payloads,
            scopes=scopes,
            scope_variables=scope_variables,
        )

    def _compose_pause_payload(
        self,
        *,
        reason: str,
        exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | None,
        thread_id: int,
        frames: list[dict[str, object]],
        scopes: list[dict[str, object]],
        scope_variables: dict[int, list[dict[str, object]]],
    ) -> dict[str, object]:
        return {
            "reason": reason,
            "message": reason_message(reason, exc_info),
            "threads": self._thread_payload(thread_id),
            "selected_thread_id": thread_id,
            "frames": frames,
            "selected_frame_id": self._selected_frame_id,
            "scopes": scopes,
            "scope_variables": scope_variables,
            "breakpoints": self._breakpoint_payloads(self._manifest.breakpoints),
            "exception": exception_payload(exc_info),
        }
