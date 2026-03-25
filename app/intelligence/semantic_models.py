"""Shared models for trusted semantic operations."""
from __future__ import annotations

from dataclasses import dataclass


CONFIDENCE_EXACT = "exact"
CONFIDENCE_APPROXIMATE = "approximate"
CONFIDENCE_UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class SemanticOperationMetadata:
    """Metadata describing one semantic query result."""

    engine: str
    source: str
    confidence: str
    latency_ms: float = 0.0
    is_stale: bool = False
    fallback_reason: str = ""
    unsupported_reason: str = ""


def exact_metadata(engine: str, *, latency_ms: float = 0.0, source: str = "semantic") -> SemanticOperationMetadata:
    """Build metadata for an exact semantic result."""
    return SemanticOperationMetadata(
        engine=engine,
        source=source,
        confidence=CONFIDENCE_EXACT,
        latency_ms=latency_ms,
    )


def approximate_metadata(
    engine: str,
    *,
    latency_ms: float = 0.0,
    source: str = "approximate",
    fallback_reason: str = "",
) -> SemanticOperationMetadata:
    """Build metadata for an approximate fallback result."""
    return SemanticOperationMetadata(
        engine=engine,
        source=source,
        confidence=CONFIDENCE_APPROXIMATE,
        latency_ms=latency_ms,
        fallback_reason=fallback_reason,
    )


def unsupported_metadata(
    engine: str,
    *,
    latency_ms: float = 0.0,
    source: str = "semantic",
    unsupported_reason: str = "",
) -> SemanticOperationMetadata:
    """Build metadata for an unsupported or unresolved semantic query."""
    return SemanticOperationMetadata(
        engine=engine,
        source=source,
        confidence=CONFIDENCE_UNSUPPORTED,
        latency_ms=latency_ms,
        unsupported_reason=unsupported_reason,
    )


@dataclass(frozen=True)
class SemanticLocation:
    """Resolved semantic symbol location."""

    name: str
    file_path: str
    line_number: int
    column_number: int | None = None
    symbol_kind: str = "symbol"
    container_name: str = ""
    signature_text: str = ""
    doc_excerpt: str = ""


@dataclass(frozen=True)
class SemanticDefinitionResult:
    """Semantic definition lookup result."""

    symbol_name: str
    locations: list[SemanticLocation]
    metadata: SemanticOperationMetadata

    @property
    def found(self) -> bool:
        return bool(self.locations)

    @property
    def source(self) -> str:
        return self.metadata.source


@dataclass(frozen=True)
class SemanticReferenceHit:
    """One semantic reference location."""

    symbol_name: str
    file_path: str
    line_number: int
    column_number: int
    line_text: str
    is_definition: bool = False


@dataclass(frozen=True)
class SemanticReferenceResult:
    """Semantic reference-search result."""

    symbol_name: str
    hits: list[SemanticReferenceHit]
    metadata: SemanticOperationMetadata

    @property
    def found(self) -> bool:
        return bool(self.hits)

    @property
    def source(self) -> str:
        return self.metadata.source


@dataclass(frozen=True)
class SemanticHoverResult:
    """Semantic hover information."""

    symbol_name: str
    symbol_kind: str
    file_path: str | None
    line_number: int | None
    doc_summary: str
    metadata: SemanticOperationMetadata

    @property
    def source(self) -> str:
        return self.metadata.source


@dataclass(frozen=True)
class SemanticSignatureResult:
    """Semantic signature-help result."""

    callable_name: str
    signature_text: str
    argument_index: int
    doc_summary: str
    metadata: SemanticOperationMetadata

    @property
    def source(self) -> str:
        return self.metadata.source


@dataclass(frozen=True)
class SemanticRenamePatch:
    """Patch-style preview for one rename-affected file."""

    file_path: str
    relative_path: str
    diff_text: str
    updated_content: str
    changed_line_numbers: list[int]


@dataclass(frozen=True)
class SemanticRenamePlan:
    """Semantic rename plan with preview patches."""

    old_symbol: str
    new_symbol: str
    hits: list[SemanticReferenceHit]
    preview_patches: list[SemanticRenamePatch]
    metadata: SemanticOperationMetadata

    @property
    def touched_files(self) -> list[str]:
        return [patch.file_path for patch in self.preview_patches]

    @property
    def source(self) -> str:
        return self.metadata.source


@dataclass(frozen=True)
class SemanticRenameApplyResult:
    """Result of applying a semantic rename plan."""

    changed_files: list[str]
    changed_occurrences: int
