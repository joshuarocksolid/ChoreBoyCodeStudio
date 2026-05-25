"""Shared helpers for runner debug inspection."""

from __future__ import annotations

from types import FrameType, TracebackType
from typing import Mapping

MAX_TOP_LEVEL_VARS = 100
MAX_CHILD_VARS = 100
MAX_REPR_CHARS = 240


def mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def parse_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def reason_message(
    reason: str,
    exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | None,
) -> str:
    if reason == "breakpoint":
        return "Paused at breakpoint."
    if reason == "pause":
        return "Pause requested."
    if reason == "step":
        return "Stepped to next location."
    if reason == "exception" and exc_info is not None:
        return "%s: %s" % (exc_info[0].__name__, exc_info[1])
    return "Paused."


def exception_payload(
    exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | None,
) -> dict[str, object] | None:
    if exc_info is None:
        return None
    return {
        "type_name": exc_info[0].__name__,
        "message": str(exc_info[1]),
    }


def traceback_frames(traceback_obj: TracebackType | None) -> list[FrameType]:
    frames: list[FrameType] = []
    current = traceback_obj
    while current is not None:
        frames.append(current.tb_frame)
        current = current.tb_next
    return list(reversed(frames))


def filtered_globals(raw_globals: Mapping[str, object]) -> dict[str, object]:
    filtered = {name: value for name, value in raw_globals.items() if not name.startswith("__")}
    return filtered or dict(raw_globals)


def safe_repr(value: object) -> str:
    try:
        rendered = repr(value)
    except Exception as exc:
        rendered = "<repr failed: %s: %s>" % (type(exc).__name__, exc)
    if len(rendered) <= MAX_REPR_CHARS:
        return rendered
    return "%s..." % (rendered[: MAX_REPR_CHARS - 3],)
