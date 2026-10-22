"""Per-user workbench widths in the global settings store.

The key is ``form_builder.workbench`` on the same JSON file as the rest of
the shell settings. A missing or unreadable block is the default plan.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from app.features.form_builder.integration.layout import WorkbenchMemory
from app.persistence.settings_service import SettingsService

SETTINGS_KEY = "form_builder"
WORKBENCH_KEY = "workbench"

_BOOLS = (
    "outline_collapsed",
    "insert_collapsed",
    "pin_left",
    "pin_inspector",
)
_INTS = ("left", "inspector", "outline_share")


def memory_from_payload(payload: Mapping[str, Any]) -> WorkbenchMemory:
    section = payload.get(SETTINGS_KEY)
    if not isinstance(section, Mapping):
        return WorkbenchMemory()
    raw = section.get(WORKBENCH_KEY)
    if not isinstance(raw, Mapping):
        return WorkbenchMemory()
    values: dict[str, Any] = {}
    for name in _INTS:
        item = raw.get(name)
        if isinstance(item, int) and not isinstance(item, bool):
            values[name] = item
    for name in _BOOLS:
        item = raw.get(name)
        if isinstance(item, bool):
            values[name] = item
    return WorkbenchMemory(**values).clamped()


def payload_with_memory(payload: Mapping[str, Any], memory: WorkbenchMemory) -> dict[str, Any]:
    updated = dict(payload)
    section_raw = updated.get(SETTINGS_KEY)
    section = dict(section_raw) if isinstance(section_raw, Mapping) else {}
    stored = memory.clamped()
    section[WORKBENCH_KEY] = {
        "left": stored.left,
        "inspector": stored.inspector,
        "outline_share": stored.outline_share,
        "outline_collapsed": stored.outline_collapsed,
        "insert_collapsed": stored.insert_collapsed,
        "pin_left": stored.pin_left,
        "pin_inspector": stored.pin_inspector,
    }
    updated[SETTINGS_KEY] = section
    return updated


class WorkbenchMemoryStore:
    """Load and save one user's workbench memory."""

    def __init__(self, state_root: Optional[str] = None) -> None:
        self._service = SettingsService(state_root=state_root)
        self._memory: Optional[WorkbenchMemory] = None

    def load(self) -> WorkbenchMemory:
        if self._memory is None:
            try:
                self._memory = memory_from_payload(self._service.load_global())
            except OSError:
                self._memory = WorkbenchMemory()
        return self._memory

    def save(self, memory: WorkbenchMemory) -> None:
        stored = memory.clamped()
        self._memory = stored
        try:
            self._service.update_global(lambda payload: payload_with_memory(payload, stored))
        except OSError:
            return


__all__ = [
    "SETTINGS_KEY",
    "WORKBENCH_KEY",
    "WorkbenchMemoryStore",
    "memory_from_payload",
    "payload_with_memory",
]
