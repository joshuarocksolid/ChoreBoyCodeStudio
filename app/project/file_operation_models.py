"""Project tree file operation models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ImportUpdatePolicy(str, Enum):
    """Policy for handling Python import updates during file moves/renames."""

    ASK = "ask"
    ALWAYS = "always"
    NEVER = "never"


@dataclass(frozen=True)
class FileOperationResult:
    """Result payload for filesystem mutation requests."""

    success: bool
    message: str
    source_path: str | None = None
    destination_path: str | None = None
