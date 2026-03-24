from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from app.bootstrap.paths import PathInput, global_settings_path, project_settings_path
from app.persistence.settings_store import (
    compute_effective_settings_payload,
    filter_project_settings_payload,
    load_project_settings,
    load_settings,
    save_project_settings,
    save_settings,
)


class SettingsService:
    def __init__(self, *, state_root: PathInput | None = None) -> None:
        self._state_root = state_root
        self._cached_global_payload: dict[str, Any] | None = None
        self._cached_project_payloads: dict[str, dict[str, Any]] = {}

    @property
    def path(self) -> Path:
        return global_settings_path(self._state_root)

    def project_path(self, project_root: PathInput) -> Path:
        return project_settings_path(project_root)

    def load_global(self, *, force_refresh: bool = False) -> dict[str, Any]:
        if self._cached_global_payload is None or force_refresh:
            self._cached_global_payload = load_settings(state_root=self._state_root)
        return dict(self._cached_global_payload)

    def save_global(self, payload: Mapping[str, Any]) -> Path:
        saved_path = save_settings(payload, state_root=self._state_root)
        self._cached_global_payload = dict(payload)
        return saved_path

    def update_global(self, updater: Callable[[dict[str, Any]], Mapping[str, Any]]) -> dict[str, Any]:
        current_payload = self.load_global()
        updated_payload = dict(updater(current_payload))
        self.save_global(updated_payload)
        return updated_payload

    def load_project(self, project_root: PathInput, *, force_refresh: bool = False) -> dict[str, Any]:
        cache_key = str(Path(project_root).expanduser().resolve())
        if force_refresh or cache_key not in self._cached_project_payloads:
            self._cached_project_payloads[cache_key] = load_project_settings(project_root)
        return dict(self._cached_project_payloads[cache_key])

    def save_project(self, project_root: PathInput, payload: Mapping[str, Any]) -> Path:
        saved_path = save_project_settings(project_root, payload)
        cache_key = str(Path(project_root).expanduser().resolve())
        self._cached_project_payloads[cache_key] = filter_project_settings_payload(payload)
        return saved_path

    def update_project(
        self,
        project_root: PathInput,
        updater: Callable[[dict[str, Any]], Mapping[str, Any]],
    ) -> dict[str, Any]:
        current_payload = self.load_project(project_root)
        updated_payload = dict(updater(current_payload))
        self.save_project(project_root, updated_payload)
        return updated_payload

    def load_effective(
        self,
        *,
        project_root: PathInput | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        global_payload = self.load_global(force_refresh=force_refresh)
        if project_root is None:
            return compute_effective_settings_payload(global_payload, None)
        project_payload = self.load_project(project_root, force_refresh=force_refresh)
        return compute_effective_settings_payload(global_payload, project_payload)

    def load(self, *, force_refresh: bool = False) -> dict[str, Any]:
        """Load **global** settings only (not project-effective). Prefer `load_effective` when layering matters."""
        return self.load_global(force_refresh=force_refresh)

    def save(self, payload: Mapping[str, Any]) -> Path:
        return self.save_global(payload)

    def update(self, updater: Callable[[dict[str, Any]], Mapping[str, Any]]) -> dict[str, Any]:
        return self.update_global(updater)

    def invalidate_cache(self) -> None:
        self._cached_global_payload = None
        self._cached_project_payloads.clear()
