"""Editor completion service facade over the tiered broker."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from typing import Callable

from app.intelligence.completion_broker import CompletionBroker
from app.intelligence.completion_context import CompletionContext
from app.intelligence.completion_merge_policy import merge_completion_display
from app.intelligence.completion_models import CompletionEnvelope, CompletionItem
from app.intelligence.runtime_introspection import (
    RuntimeIntrospectionCoordinator,
    RuntimeIntrospectionQuery,
    attach_replacement_metadata,
    resolve_runtime_introspection_query_with_inference,
)
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
    """Compatibility facade used by shell/session callers."""

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
        max_results: int = 100,
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

    def runtime_completion_items(
        self,
        context: CompletionContext,
        *,
        coordinator: RuntimeIntrospectionCoordinator | None,
    ) -> tuple[RuntimeIntrospectionQuery | None, list[CompletionItem]]:
        """Resolve cached runtime introspection items for ``context``."""
        runtime_query = resolve_runtime_introspection_query_with_inference(
            context=context,
            project_root=context.project_root,
            current_file_path=context.file_path,
            source_text=context.source_text,
        )
        runtime_items: list[CompletionItem] = []
        if coordinator is not None and runtime_query is not None:
            cached = coordinator.cached_items(runtime_query)
            if cached:
                runtime_items = attach_replacement_metadata(cached, context=context)
        return runtime_query, runtime_items

    def attach_runtime_replacement_metadata(
        self,
        items: list[CompletionItem],
        *,
        context: CompletionContext,
    ) -> list[CompletionItem]:
        """Stamp broker replacement metadata onto runtime introspection items."""
        return attach_replacement_metadata(items, context=context)
