"""Traceback/problem parsing helpers for run output."""

from __future__ import annotations

from dataclasses import dataclass
import re

TRACEBACK_FILE_LINE_PATTERN = re.compile(
    r'^\s*File "(?P<path>.+)", line (?P<line>\d+)(?:, in (?P<context>.+))?$'
)
TRACEBACK_ERROR_LINE_PATTERN = re.compile(r"^[A-Za-z_][\w.]*?(?:: .*)?$")


@dataclass(frozen=True)
class ProblemEntry:
    """Structured problem summary derived from traceback output."""

    file_path: str
    line_number: int
    context: str
    message: str


def parse_traceback_problems(output_text: str) -> list[ProblemEntry]:
    """Extract navigable problem entries from traceback output text."""
    lines = output_text.splitlines()
    traceback_frames: list[tuple[str, int, str | None]] = []
    error_message = ""

    for raw_line in lines:
        match = TRACEBACK_FILE_LINE_PATTERN.match(raw_line)
        if match:
            traceback_frames.append(
                (
                    match.group("path"),
                    int(match.group("line")),
                    None if match.group("context") is None else match.group("context").strip(),
                )
            )
            continue
        normalized_line = raw_line.strip()
        if not normalized_line:
            continue
        if normalized_line.startswith("File "):
            continue
        if TRACEBACK_ERROR_LINE_PATTERN.match(normalized_line):
            error_message = normalized_line

    if not traceback_frames:
        return []

    message = error_message or "Unhandled exception"
    return [
        ProblemEntry(
            file_path=frame_path,
            line_number=frame_line,
            context=frame_context or "",
            message=message,
        )
        for frame_path, frame_line, frame_context in traceback_frames
    ]
