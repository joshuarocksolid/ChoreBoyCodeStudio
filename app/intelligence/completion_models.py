"""Models used by editor completion services."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CompletionKind(str, Enum):
    """Categorizes completion entries for ranking and display."""

    KEYWORD = "keyword"
    BUILTIN = "builtin"
    SYMBOL = "symbol"
    MODULE = "module"


@dataclass(frozen=True)
class CompletionItem:
    """One completion candidate returned to the editor."""

    label: str
    insert_text: str
    kind: CompletionKind
    detail: str = ""
    source_file_path: str | None = None


@dataclass(frozen=True)
class RankedCompletionItem:
    """Completion entry paired with ranking score."""

    item: CompletionItem
    score: int
