"""Editor completion service facade over the tiered broker."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.intelligence.completion_broker import CompletionBroker
from app.intelligence.completion_models import CompletionEnvelope, CompletionItem
from app.intelligence.semantic_facade import SemanticFacade


@dataclass(frozen=True)
class CompletionRequest:
    """Completion query payload from the editor."""

    source_text: str
    cursor_position: int
    current_file_path: str
    project_root: str | None
    trigger_is_manual: bool
    min_prefix_chars: int
    max_results: int = 100
    trigger_kind: str = "invoked"
    trigger_character: str = ""
    buffer_revision: int | None = None


class CompletionService:
    """Compatibility facade used by shell/session callers."""

    def __init__(self, *, cache_db_path: str, semantic_facade: SemanticFacade | None = None) -> None:
        self._cache_db_path = str(Path(cache_db_path).expanduser().resolve())
        self._semantic_facade = semantic_facade or SemanticFacade(cache_db_path=self._cache_db_path)
        self._broker = CompletionBroker(
            cache_db_path=self._cache_db_path,
            semantic_facade=self._semantic_facade,
        )

    def complete(self, request: CompletionRequest) -> CompletionEnvelope:
        """Return ranked completion candidates for one editor query."""
        return self._broker.complete(request)

    def complete_fast(self, request: CompletionRequest) -> CompletionEnvelope:
        """Return nonblocking cached/indexed completion candidates."""
        return self._broker.complete_fast(request)

    def complete_semantic(self, request: CompletionRequest) -> CompletionEnvelope:
        """Return semantic refinement candidates."""
        return self._broker.complete_semantic(request)

    def record_acceptance(self, item: CompletionItem) -> None:
        """Record a user-accepted completion for future ranking boosts."""
        self._broker.record_acceptance(item)
