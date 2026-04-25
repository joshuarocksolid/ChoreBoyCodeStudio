"""Models used by editor completion services."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


COMPLETION_DEGRADATION_SEMANTIC_ENGINE_ERROR = "semantic_engine_error"


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
    engine: str = ""
    source: str = ""
    confidence: str = ""
    semantic_kind: str = ""


@dataclass(frozen=True)
class CompletionEnvelope:
    """Completion candidates plus request-level degradation metadata."""

    items: list[CompletionItem]
    degradation_reason: str = ""


@dataclass(frozen=True)
class CompletionRequestResult:
    """Async completion result paired with the editor request identity."""

    request_generation: int
    prefix: str
    envelope: CompletionEnvelope


@dataclass(frozen=True)
class RankedCompletionItem:
    """Completion entry paired with ranking score."""

    item: CompletionItem
    score: int
