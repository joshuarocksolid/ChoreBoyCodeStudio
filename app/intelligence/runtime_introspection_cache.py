"""Session-scoped LRU cache for trusted runtime introspection results."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace

from app.intelligence.completion_models import CompletionItem

_DEFAULT_MAX_ENTRIES = 128


@dataclass(frozen=True)
class RuntimeIntrospectionCacheKey:
    """Cache key for a trusted runtime member listing."""

    target_path: str
    include_private: bool


class RuntimeIntrospectionCache:
    """In-memory LRU cache keyed by whitelisted target path."""

    def __init__(self, *, max_entries: int = _DEFAULT_MAX_ENTRIES) -> None:
        self._max_entries = max(1, int(max_entries))
        self._entries: OrderedDict[RuntimeIntrospectionCacheKey, tuple[CompletionItem, ...]] = OrderedDict()

    def get(self, *, target_path: str, include_private: bool = True) -> list[CompletionItem] | None:
        key = RuntimeIntrospectionCacheKey(target_path=target_path, include_private=include_private)
        cached = self._entries.get(key)
        if cached is None:
            return None
        self._entries.move_to_end(key)
        return list(cached)

    def put(
        self,
        *,
        target_path: str,
        include_private: bool,
        items: list[CompletionItem],
    ) -> None:
        key = RuntimeIntrospectionCacheKey(target_path=target_path, include_private=include_private)
        stored = tuple(items)
        self._entries[key] = stored
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()


def clone_completion_items(items: list[CompletionItem]) -> list[CompletionItem]:
    """Return shallow copies so callers can attach per-request metadata safely."""

    return [replace(item) for item in items]
