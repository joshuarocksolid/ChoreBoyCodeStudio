"""Per-user editor memory in the global settings store.

Recent colours live at ``form_builder.editors.recent_colours`` on the same JSON
file as the rest of the shell settings, most recent first, at most 12. One
store is shared per state root, so two open forms see the same list. A missing
or unreadable block is an empty list.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Mapping, Optional, Tuple

from app.bootstrap.paths import resolve_global_state_root
from app.persistence.settings_service import SettingsService

SETTINGS_KEY = "form_builder"
EDITORS_KEY = "editors"
RECENT_KEY = "recent_colours"
RECENT_LIMIT = 12

_STORES: Dict[str, "RecentColourStore"] = {}
_ROOT_OVERRIDE: Optional[str] = None


def use_state_root(root: Optional[str]) -> None:
    """Pin the store the editors read. ``None`` follows the product state root."""
    global _ROOT_OVERRIDE
    _ROOT_OVERRIDE = root


def active_store() -> "RecentColourStore":
    if _ROOT_OVERRIDE:
        return shared_store(_ROOT_OVERRIDE)
    try:
        root = str(resolve_global_state_root())
    except OSError:
        root = ""
    if not root:
        return shared_store("")
    return shared_store(root)


def shared_store(state_root: str) -> "RecentColourStore":
    """One store per settings root."""
    key = os.path.abspath(state_root) if state_root else ""
    found = _STORES.get(key)
    if found is None:
        found = RecentColourStore(state_root or None)
        _STORES[key] = found
    return found


def memory_from_payload(payload: Mapping[str, Any]) -> Tuple[str, ...]:
    section = payload.get(SETTINGS_KEY)
    if not isinstance(section, Mapping):
        return ()
    editors = section.get(EDITORS_KEY)
    if not isinstance(editors, Mapping):
        return ()
    raw = editors.get(RECENT_KEY)
    if not isinstance(raw, list):
        return ()
    found = []
    for item in raw:
        if isinstance(item, str) and item.startswith("#") and item not in found:
            found.append(item)
        if len(found) == RECENT_LIMIT:
            break
    return tuple(found)


def payload_with_recent(payload: Mapping[str, Any], recent: Tuple[str, ...]) -> Dict[str, Any]:
    updated = dict(payload)
    section_raw = updated.get(SETTINGS_KEY)
    section = dict(section_raw) if isinstance(section_raw, Mapping) else {}
    editors_raw = section.get(EDITORS_KEY)
    editors = dict(editors_raw) if isinstance(editors_raw, Mapping) else {}
    editors[RECENT_KEY] = list(recent[:RECENT_LIMIT])
    section[EDITORS_KEY] = editors
    updated[SETTINGS_KEY] = section
    return updated


class RecentColourStore:
    """Load and save one user's recent colours."""

    def __init__(self, state_root: Optional[str] = None) -> None:
        self._service = SettingsService(state_root=state_root)
        self._recent: Optional[Tuple[str, ...]] = None

    def recent(self) -> Tuple[str, ...]:
        if self._recent is None:
            try:
                self._recent = memory_from_payload(self._service.load_global())
            except OSError:
                self._recent = ()
        return self._recent

    def note(self, text: str) -> None:
        colour = text.strip().upper()
        if not colour.startswith("#"):
            return
        current = self.recent()
        moved = (colour,) + tuple(item for item in current if item.upper() != colour)
        self._save(moved[:RECENT_LIMIT])

    def _save(self, recent: Tuple[str, ...]) -> None:
        self._recent = recent
        try:
            self._service.update_global(lambda payload: payload_with_recent(payload, recent))
        except OSError:
            return
