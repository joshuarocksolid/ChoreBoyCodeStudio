from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from app.bootstrap.paths import PathInput, global_settings_path, project_settings_path
from app.core import constants
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

    def load_recent_argv_history(self) -> list[str]:
        """Return the most-recent-first list of argv strings used in Run With Arguments."""
        payload = self.load_global()
        return _coerce_recent_argv_history(payload)

    def push_recent_argv_history(self, argv_text: str) -> list[str]:
        """Prepend ``argv_text`` to the recent argv history (deduplicated, capped)."""

        normalized = (argv_text or "").strip()
        if not normalized:
            return self.load_recent_argv_history()

        def _updater(current_payload: dict[str, Any]) -> Mapping[str, Any]:
            updated_payload = dict(current_payload)
            run_section_raw = updated_payload.get(constants.UI_RUN_SETTINGS_KEY)
            run_section: dict[str, Any] = (
                dict(run_section_raw) if isinstance(run_section_raw, Mapping) else {}
            )
            existing_history = _coerce_recent_argv_history(updated_payload)
            deduped_history = [normalized] + [entry for entry in existing_history if entry != normalized]
            run_section[constants.UI_RUN_RECENT_ARGV_KEY] = deduped_history[
                : constants.UI_RUN_RECENT_ARGV_HISTORY_LIMIT
            ]
            updated_payload[constants.UI_RUN_SETTINGS_KEY] = run_section
            return updated_payload

        updated = self.update_global(_updater)
        return _coerce_recent_argv_history(updated)


def _coerce_recent_argv_history(payload: Mapping[str, Any]) -> list[str]:
    run_section = payload.get(constants.UI_RUN_SETTINGS_KEY)
    if not isinstance(run_section, Mapping):
        return []
    raw_history = run_section.get(constants.UI_RUN_RECENT_ARGV_KEY)
    if not isinstance(raw_history, list):
        return []
    normalized: list[str] = []
    for entry in raw_history:
        if isinstance(entry, str) and entry.strip():
            normalized.append(entry)
    return normalized[: constants.UI_RUN_RECENT_ARGV_HISTORY_LIMIT]
