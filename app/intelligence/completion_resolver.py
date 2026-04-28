"""Lazy completion item metadata resolution."""

from __future__ import annotations

from app.intelligence.completion_models import CompletionItem, CompletionResolveRequest
from app.intelligence.semantic_facade import SemanticFacade


class CompletionResolver:
    """Resolve documentation/signature fields only for selected items."""

    def __init__(self, *, semantic_facade: SemanticFacade) -> None:
        self._semantic_facade = semantic_facade
        self._resolved_cache: dict[str, CompletionItem] = {}

    def resolve(self, request: CompletionResolveRequest) -> CompletionItem:
        """Return ``request.item`` enriched with requested lazy metadata."""

        item = request.item
        if not item.resolvable_fields:
            return item
        cache_key = _cache_key(request)
        cached = self._resolved_cache.get(cache_key)
        if cached is not None:
            return cached
        if item.resolve_provider == "jedi" or item.source == "semantic":
            resolved = self._semantic_facade.resolve_completion_item(
                project_root=request.project_root,
                current_file_path=request.current_file_path,
                source_text=request.source_text,
                cursor_position=request.cursor_position,
                item=item,
            )
        else:
            resolved = item
        self._resolved_cache[cache_key] = resolved
        return resolved


def _cache_key(request: CompletionResolveRequest) -> str:
    item = request.item
    return "|".join(
        [
            request.context_fingerprint,
            item.item_id,
            item.label,
            item.source,
            ",".join(request.requested_fields),
        ]
    )
