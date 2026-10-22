"""Editor completion service facade over the tiered broker."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from typing import Callable

from app.core.constants import UI_INTELLIGENCE_COMPLETION_MAX_RESULTS_DEFAULT
from app.intelligence.completion_broker import CompletionBroker
from app.intelligence.completion_context import CompletionContext
from app.intelligence.completion_merge_policy import merge_completion_display
from app.intelligence.completion_models import CompletionEnvelope, CompletionItem
from app.intelligence.runtime_introspection import attach_replacement_metadata
from app.intelligence.semantic_facade import SemanticFacade
from app.project.file_inventory import ProjectInventorySnapshot


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
    """Compatibility facade used by shell/session callers.

    Degradation UX: when the semantic engine fails, ``CompletionEnvelope.degradation_reason``
    is set (for example ``semantic_engine_error``) and the shell status bar surfaces it once
    per reason. Approximate fast-tier items are tagged via ``source``, ``detail`` (including
    an ``approximate`` suffix), and ``confidence`` so they remain distinguishable from
    semantic results without separate popup grouping.
    """

    def __init__(self, *, cache_db_path: str, semantic_facade: SemanticFacade | None = None) -> None:
        self._cache_db_path = str(Path(cache_db_path).expanduser().resolve())
        self._semantic_facade = semantic_facade or SemanticFacade(cache_db_path=self._cache_db_path)
        self._broker = CompletionBroker(
            cache_db_path=self._cache_db_path,
            semantic_facade=self._semantic_facade,
        )

    def set_inventory_snapshot_provider(
        self,
        provider: Callable[[], ProjectInventorySnapshot | None],
    ) -> None:
        self._broker._inventory_snapshot_provider = provider

    def complete(self, request: CompletionRequest) -> CompletionEnvelope:
        """Return ranked completion candidates for one editor query."""
        return self._broker.complete(request)

    def complete_fast(self, request: CompletionRequest) -> CompletionEnvelope:
        """Return nonblocking cached/indexed completion candidates."""
        return self._broker.complete_fast(request)

    def complete_semantic(self, request: CompletionRequest) -> CompletionEnvelope:
        """Return semantic refinement candidates."""
        return self._broker.complete_semantic(request)

    def merge_for_editor_display(
        self,
        *,
        fast: CompletionEnvelope | None = None,
        semantic: CompletionEnvelope | None = None,
        runtime_items: list[CompletionItem] | None = None,
        max_results: int = UI_INTELLIGENCE_COMPLETION_MAX_RESULTS_DEFAULT,
    ) -> CompletionEnvelope:
        """Merge tiered completion results for editor popup display."""
        return merge_completion_display(
            fast=fast,
            semantic=semantic,
            runtime_items=runtime_items,
            max_results=max_results,
        )

    def record_acceptance(self, item: CompletionItem) -> None:
        """Record a user-accepted completion for future ranking boosts."""
        self._broker.record_acceptance(item)

    def build_completion_context(self, request: CompletionRequest) -> CompletionContext:
        """Return broker-owned completion context for one editor request."""
        return self._broker._context_from_request(request)

    def attach_runtime_replacement_metadata(
        self,
        items: list[CompletionItem],
        *,
        context: CompletionContext,
    ) -> list[CompletionItem]:
        """Stamp broker replacement metadata onto runtime introspection items."""
        return attach_replacement_metadata(items, context=context)
