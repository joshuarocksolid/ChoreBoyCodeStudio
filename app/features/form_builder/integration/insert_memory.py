"""Per-user Insert state in the global settings store (UX-CAT-004, -005, -006).

The key is ``form_builder.insert`` on the same JSON file as the rest of the shell
settings: ``recent`` (catalog keys, most recent first), ``view`` (``icons``,
``list`` or absent for the width default) and ``expanded`` (category -> bool).
A missing or unreadable block is the default. ``memory.py`` is not touched.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional, Tuple, Union

from app.persistence.settings_service import SettingsService

SETTINGS_KEY = "form_builder"
INSERT_KEY = "insert"
RECENT_LIMIT = 6
VIEWS = ("icons", "list")


@dataclass(frozen=True)
class InsertMemory:
    recent: Tuple[str, ...] = ()
    view: str = ""
    expanded: Mapping[str, bool] = field(default_factory=dict)


def memory_from_payload(payload: Mapping[str, Any]) -> InsertMemory:
    section = payload.get(SETTINGS_KEY)
    if not isinstance(section, Mapping):
        return InsertMemory()
    raw = section.get(INSERT_KEY)
    if not isinstance(raw, Mapping):
        return InsertMemory()
    recent_raw = raw.get("recent")
    recent: Tuple[str, ...] = ()
    if isinstance(recent_raw, list):
        recent = tuple(item for item in recent_raw if isinstance(item, str) and item)[:RECENT_LIMIT]
    view_raw = raw.get("view")
    view = view_raw if isinstance(view_raw, str) and view_raw in VIEWS else ""
    expanded: Dict[str, bool] = {}
    expanded_raw = raw.get("expanded")
    if isinstance(expanded_raw, Mapping):
        for name, value in expanded_raw.items():
            if isinstance(name, str) and isinstance(value, bool):
                expanded[name] = value
    return InsertMemory(recent, view, expanded)


def payload_with_insert(payload: Mapping[str, Any], memory: InsertMemory) -> Dict[str, Any]:
    updated = dict(payload)
    section_raw = updated.get(SETTINGS_KEY)
    section = dict(section_raw) if isinstance(section_raw, Mapping) else {}
    block: Dict[str, Any] = {"recent": list(memory.recent[:RECENT_LIMIT]), "expanded": dict(memory.expanded)}
    if memory.view:
        block["view"] = memory.view
    section[INSERT_KEY] = block
    updated[SETTINGS_KEY] = section
    return updated


_STORES: Dict[str, "InsertMemoryStore"] = {}


def shared_store(state_root: str) -> "InsertMemoryStore":
    """One store per settings root. Two open forms must see the same recent list."""
    key = os.path.abspath(state_root)
    found = _STORES.get(key)
    if found is None:
        found = InsertMemoryStore(state_root)
        _STORES[key] = found
    return found


class InsertMemoryStore:
    """Load and save one user's Insert state. Implements ``qtside.insert.ports.InsertMemoryPort``."""

    def __init__(self, state_root: Optional[str] = None) -> None:
        self._service = SettingsService(state_root=state_root)
        self._memory: Optional[InsertMemory] = None

    def load(self) -> InsertMemory:
        if self._memory is None:
            try:
                self._memory = memory_from_payload(self._service.load_global())
            except OSError:
                self._memory = InsertMemory()
        return self._memory

    def _save(self, memory: InsertMemory) -> None:
        self._memory = memory
        try:
            self._service.update_global(lambda payload: payload_with_insert(payload, memory))
        except OSError:
            return

    def recent(self) -> Tuple[str, ...]:
        return self.load().recent

    def note_used(self, key: str) -> None:
        current = self.load()
        if not key:
            return
        moved = (key,) + tuple(item for item in current.recent if item != key)
        self._save(InsertMemory(moved[:RECENT_LIMIT], current.view, current.expanded))

    def clear_recent(self) -> None:
        current = self.load()
        self._save(InsertMemory((), current.view, current.expanded))

    def view(self) -> str:
        return self.load().view

    def set_view(self, view: str) -> None:
        current = self.load()
        self._save(InsertMemory(current.recent, view if view in VIEWS else "", current.expanded))

    def expanded_states(self) -> Dict[str, bool]:
        return dict(self.load().expanded)

    def set_expanded(self, category: str, expanded: bool) -> None:
        current = self.load()
        states = dict(current.expanded)
        states[category] = bool(expanded)
        self._save(InsertMemory(current.recent, current.view, states))


class InMemoryInsertMemory:
    """Session-only memory, used when no settings root is known yet (tests, a window without a project)."""

    def __init__(self) -> None:
        self._memory = InsertMemory()

    def recent(self) -> Tuple[str, ...]:
        return self._memory.recent

    def note_used(self, key: str) -> None:
        current = self._memory
        if key:
            moved = (key,) + tuple(item for item in current.recent if item != key)
            self._memory = InsertMemory(moved[:RECENT_LIMIT], current.view, current.expanded)

    def clear_recent(self) -> None:
        current = self._memory
        self._memory = InsertMemory((), current.view, current.expanded)

    def view(self) -> str:
        return self._memory.view

    def set_view(self, view: str) -> None:
        current = self._memory
        self._memory = InsertMemory(current.recent, view if view in VIEWS else "", current.expanded)

    def expanded_states(self) -> Dict[str, bool]:
        return dict(self._memory.expanded)

    def set_expanded(self, category: str, expanded: bool) -> None:
        current = self._memory
        states = dict(current.expanded)
        states[category] = bool(expanded)
        self._memory = InsertMemory(current.recent, current.view, states)


class LazyInsertMemory:
    """Opens the settings-backed store once a settings root is known; until then it is in memory.

    The workbench is built before its window knows the project's state root, so the
    store is resolved at first use, not at construction.
    """

    def __init__(self, root_of: Callable[[], Optional[str]]) -> None:
        self._root_of = root_of
        self._inner: Union[InsertMemoryStore, InMemoryInsertMemory, None] = None

    def _port(self) -> Union[InsertMemoryStore, InMemoryInsertMemory]:
        if isinstance(self._inner, InsertMemoryStore):
            return self._inner
        root = self._root_of()
        if root:
            carried = self._inner.expanded_states() if self._inner is not None else {}
            store = shared_store(root)
            for category, expanded in carried.items():
                store.set_expanded(category, expanded)
            self._inner = store
            return store
        if self._inner is None:
            self._inner = InMemoryInsertMemory()
        return self._inner

    def recent(self) -> Tuple[str, ...]:
        return self._port().recent()

    def note_used(self, key: str) -> None:
        self._port().note_used(key)

    def clear_recent(self) -> None:
        self._port().clear_recent()

    def view(self) -> str:
        return self._port().view()

    def set_view(self, view: str) -> None:
        self._port().set_view(view)

    def expanded_states(self) -> Dict[str, bool]:
        return self._port().expanded_states()

    def set_expanded(self, category: str, expanded: bool) -> None:
        self._port().set_expanded(category, expanded)


__all__ = [
    "INSERT_KEY",
    "InMemoryInsertMemory",
    "InsertMemory",
    "InsertMemoryStore",
    "LazyInsertMemory",
    "shared_store",
    "SETTINGS_KEY",
    "memory_from_payload",
    "payload_with_insert",
]
