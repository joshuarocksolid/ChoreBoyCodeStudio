from __future__ import annotations

from collections import OrderedDict
from typing import Optional

from app.intelligence.runtime_members import RuntimeMemberListing

_DEFAULT_MAX_ENTRIES = 128


class RuntimeIntrospectionCache:
    """In-memory LRU cache keyed by whitelisted target path."""

    def __init__(self, *, max_entries: int = _DEFAULT_MAX_ENTRIES) -> None:
        self._max_entries = max(1, int(max_entries))
        self._entries: OrderedDict[str, RuntimeMemberListing] = OrderedDict()

    def get(self, target_path: str) -> Optional[RuntimeMemberListing]:
        listing = self._entries.get(target_path)
        if listing is None:
            return None
        self._entries.move_to_end(target_path)
        return listing

    def put(self, listing: RuntimeMemberListing) -> None:
        self._entries[listing.target_path] = listing
        self._entries.move_to_end(listing.target_path)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()
