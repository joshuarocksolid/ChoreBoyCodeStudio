"""Models used by editor completion services."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


COMPLETION_DEGRADATION_SEMANTIC_ENGINE_ERROR = "semantic_engine_error"


class CompletionKind(str, Enum):
    """Categorizes completion entries for ranking and display."""

    KEYWORD = "keyword"
    BUILTIN = "builtin"
    SYMBOL = "symbol"
    MODULE = "module"
    FUNCTION = "function"
    METHOD = "method"
    PROPERTY = "property"
    ATTRIBUTE = "attribute"
    CLASS = "class"
    SNIPPET = "snippet"
    TEXT = "text"


@dataclass(frozen=True)
class CompletionItem:
    """One completion candidate returned to the editor."""

    label: str
    insert_text: str
    kind: CompletionKind
    detail: str = ""
    documentation: str = ""
    signature: str = ""
    return_type: str = ""
    source_file_path: str | None = None
    engine: str = ""
    source: str = ""
    confidence: str = ""
    semantic_kind: str = ""
    replacement_start: int | None = None
    replacement_end: int | None = None
    trigger_kind: str = ""
    trigger_character: str = ""
    side_effect_risk: str = ""
    item_id: str = ""
    context_fingerprint: str = ""
    resolve_provider: str = ""
    resolvable_fields: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompletionEnvelope:
    """Completion candidates plus request-level degradation metadata."""

    items: list[CompletionItem]
    degradation_reason: str = ""
    source: str = ""
    confidence: str = ""
    source_phase: str = ""
    request_id: str = ""
    buffer_revision: int | None = None
    context_fingerprint: str = ""
    is_incomplete: bool = False
    valid_for: object | None = None
    latency_breakdown: dict[str, float] = field(default_factory=dict)
    stale_reason: str = ""


@dataclass(frozen=True)
class CompletionRequestResult:
    """Async completion result paired with the editor request identity."""

    request_generation: int
    prefix: str
    envelope: CompletionEnvelope
    buffer_revision: int | None = None


@dataclass(frozen=True)
class CompletionResolveRequest:
    """Request to enrich lazy metadata for a selected completion item."""

    item: CompletionItem
    source_text: str
    cursor_position: int
    current_file_path: str
    project_root: str | None
    context_fingerprint: str
    requested_fields: tuple[str, ...] = ("documentation", "signature", "return_type", "detail")
    buffer_revision: int | None = None
    request_generation: int = 0


@dataclass(frozen=True)
class CompletionResolveResult:
    """Lazy resolution result paired with editor request identity."""

    request_generation: int
    item: CompletionItem
    buffer_revision: int | None = None
    context_fingerprint: str = ""


@dataclass(frozen=True)
class RankedCompletionItem:
    """Completion entry paired with ranking score."""

    item: CompletionItem
    score: int
