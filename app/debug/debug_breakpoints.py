"""Breakpoint models and helper utilities."""

from __future__ import annotations

from hashlib import sha1
from pathlib import Path

from app.debug.debug_models import DebugBreakpoint


def breakpoint_key(file_path: str, line_number: int) -> tuple[str, int]:
    """Return normalized lookup key for one breakpoint."""

    normalized_path = str(Path(file_path).expanduser().resolve())
    return (normalized_path, int(line_number))


def make_breakpoint_id(file_path: str, line_number: int) -> str:
    """Build a stable breakpoint identifier from file path and line number."""

    normalized_path, normalized_line = breakpoint_key(file_path, line_number)
    digest = sha1(f"{normalized_path}:{normalized_line}".encode("utf-8")).hexdigest()[:10]
    return "bp_%s_%s" % (normalized_line, digest)


def build_breakpoint(
    file_path: str,
    line_number: int,
    *,
    breakpoint_id: str | None = None,
    enabled: bool = True,
    condition: str = "",
    hit_condition: int | None = None,
    verified: bool = False,
    verification_message: str = "",
) -> DebugBreakpoint:
    """Build one normalized breakpoint model."""

    normalized_path, normalized_line = breakpoint_key(file_path, line_number)
    normalized_hit = None if hit_condition is None or int(hit_condition) <= 0 else int(hit_condition)
    return DebugBreakpoint(
        breakpoint_id=breakpoint_id or make_breakpoint_id(normalized_path, normalized_line),
        file_path=normalized_path,
        line_number=normalized_line,
        enabled=bool(enabled),
        condition=str(condition or "").strip(),
        hit_condition=normalized_hit,
        verified=bool(verified),
        verification_message=str(verification_message or "").strip(),
    )


def update_breakpoint_verification(
    breakpoint: DebugBreakpoint,
    *,
    verified: bool,
    verification_message: str = "",
) -> DebugBreakpoint:
    """Return a copy with updated verification state."""

    return DebugBreakpoint(
        breakpoint_id=breakpoint.breakpoint_id,
        file_path=breakpoint.file_path,
        line_number=breakpoint.line_number,
        enabled=breakpoint.enabled,
        condition=breakpoint.condition,
        hit_condition=breakpoint.hit_condition,
        verified=bool(verified),
        verification_message=str(verification_message or "").strip(),
    )


def breakpoint_to_manifest_payload(
    breakpoint: DebugBreakpoint,
    *,
    runtime_file_path: str | None = None,
) -> dict[str, object]:
    """Serialize breakpoint for run-manifest transport."""

    file_path = breakpoint.file_path if runtime_file_path is None else str(Path(runtime_file_path).expanduser().resolve())
    payload: dict[str, object] = {
        "breakpoint_id": breakpoint.breakpoint_id,
        "file_path": file_path,
        "line_number": breakpoint.line_number,
        "enabled": breakpoint.enabled,
    }
    if breakpoint.condition:
        payload["condition"] = breakpoint.condition
    if breakpoint.hit_condition is not None:
        payload["hit_condition"] = breakpoint.hit_condition
    return payload
