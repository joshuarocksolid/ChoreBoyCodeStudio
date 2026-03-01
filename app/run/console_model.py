"""In-memory console output model for run streams."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ConsoleLine:
    """One console output line with stream metadata."""

    timestamp: str
    stream: str
    text: str


class ConsoleModel:
    """Captures console lines for the active session."""

    def __init__(self) -> None:
        self._lines: list[ConsoleLine] = []

    def append(self, stream: str, text: str) -> ConsoleLine:
        """Append output text for a stream and return stored line metadata."""
        line = ConsoleLine(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            stream=stream,
            text=text,
        )
        self._lines.append(line)
        return line

    def clear(self) -> None:
        """Clear all buffered lines."""
        self._lines.clear()

    def lines(self) -> list[ConsoleLine]:
        """Return buffered lines in append order."""
        return list(self._lines)
