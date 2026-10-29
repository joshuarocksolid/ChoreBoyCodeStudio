"""The drawer's height, remembered per user in the global settings (UX-STYLE-002)."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from app.persistence.settings_service import SettingsService

SETTINGS_KEY = "form_builder"
HEIGHT_KEY = "style_drawer_height"
DEFAULT_HEIGHT = 240
MIN_HEIGHT = 160


def height_from_payload(payload: Mapping[str, Any]) -> int:
    section = payload.get(SETTINGS_KEY)
    raw = section.get(HEIGHT_KEY) if isinstance(section, Mapping) else None
    if isinstance(raw, int) and not isinstance(raw, bool) and raw >= MIN_HEIGHT:
        return raw
    return DEFAULT_HEIGHT


def payload_with_height(payload: Mapping[str, Any], height: int) -> dict:
    updated = dict(payload)
    section_raw = updated.get(SETTINGS_KEY)
    section = dict(section_raw) if isinstance(section_raw, Mapping) else {}
    section[HEIGHT_KEY] = int(height)
    updated[SETTINGS_KEY] = section
    return updated


class DrawerHeight:
    def __init__(self, state_root: Optional[str] = None) -> None:
        self._service = SettingsService(state_root=state_root)

    def load(self) -> int:
        try:
            return height_from_payload(self._service.load_global())
        except OSError:
            return DEFAULT_HEIGHT

    def save(self, height: int) -> None:
        try:
            self._service.update_global(lambda payload: payload_with_height(payload, height))
        except OSError:
            return
