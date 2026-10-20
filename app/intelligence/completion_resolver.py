"""Lazy completion item metadata resolution."""

from __future__ import annotations

from dataclasses import replace
from typing import Optional, Protocol

from app.intelligence.completion_models import CompletionItem, CompletionResolveRequest
from app.intelligence.runtime_members import (
    RUNTIME_INTROSPECTION_PROVIDER,
    RuntimeMemberDetail,
    RuntimeMemberRef,
)
from app.intelligence.semantic_facade import SemanticFacade


class RuntimeMemberResolver(Protocol):
    """Resolves one runtime member. RuntimeIntrospectionCoordinator satisfies it."""

    def resolve_member(self, ref: RuntimeMemberRef) -> Optional[RuntimeMemberDetail]:
        ...


class CompletionResolver:
    """Resolve documentation/signature fields only for selected items."""

    def __init__(self, *, semantic_facade: SemanticFacade) -> None:
        self._semantic_facade = semantic_facade
        self._runtime_members: Optional[RuntimeMemberResolver] = None
        self._resolved_cache: dict[str, CompletionItem] = {}

    def bind_runtime_members(self, runtime_members: Optional[RuntimeMemberResolver]) -> None:
        """Attach the runtime member resolver that produced the runtime items."""

        self._runtime_members = runtime_members

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
        elif item.resolve_provider == RUNTIME_INTROSPECTION_PROVIDER:
            detail = self._resolve_runtime_member(item)
            if detail is None:
                return item
            resolved = replace(
                item,
                signature=detail.signature,
                documentation=detail.documentation,
                resolvable_fields=(),
            )
        else:
            resolved = item
        self._resolved_cache[cache_key] = resolved
        return resolved

    def _resolve_runtime_member(self, item: CompletionItem) -> Optional[RuntimeMemberDetail]:
        ref = RuntimeMemberRef.from_item(item)
        if ref is None or self._runtime_members is None:
            return None
        return self._runtime_members.resolve_member(ref)


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
