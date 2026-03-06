from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from app.bootstrap.paths import PathInput, global_settings_path
from app.persistence.settings_store import load_settings, save_settings


class SettingsService:
    def __init__(self, *, state_root: PathInput | None = None) -> None:
        self._state_root = state_root
        self._cached_payload: dict[str, Any] | None = None

    @property
    def path(self) -> Path:
        return global_settings_path(self._state_root)

    def load(self, *, force_refresh: bool = False) -> dict[str, Any]:
        if self._cached_payload is None or force_refresh:
            self._cached_payload = load_settings(state_root=self._state_root)
        return dict(self._cached_payload)

    def save(self, payload: Mapping[str, Any]) -> Path:
        saved_path = save_settings(payload, state_root=self._state_root)
        self._cached_payload = dict(payload)
        return saved_path

    def update(self, updater: Callable[[dict[str, Any]], Mapping[str, Any]]) -> dict[str, Any]:
        current_payload = self.load()
        updated_payload = dict(updater(current_payload))
        self.save(updated_payload)
        return updated_payload

    def invalidate_cache(self) -> None:
        self._cached_payload = None
