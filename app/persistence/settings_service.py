from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from app.features.shop_sharing.service import DocumentRoute


class SettingsService:
    """Owns global settings reads and writes.

    In shop mode a save writes only the leaves that changed since the merge
    base: the document returned by the last ``save_global`` or by the last
    ``load_global`` outside a sharing listener. A reload inside a sharing
    listener refreshes the cache but keeps the merge base, so a dialog payload
    built before turn on is diffed against the settings it was built from.
    """

    def __init__(self, *, state_root: PathInput | None = None) -> None:
        self._state_root = state_root
        self._cached_global_payload: dict[str, Any] | None = None
        self._cached_generation = 0
        self._merge_base: dict[str, Any] | None = None
        self._cached_project_payloads: dict[str, dict[str, Any]] = {}

    @property
    def path(self) -> Path:
        return global_settings_path(self._state_root)

    def project_path(self, project_root: PathInput) -> Path:
        return project_settings_path(project_root)

    def load_global(self, *, force_refresh: bool = False) -> dict[str, Any]:
        route = _route(self._state_root)
        if self._cached_global_payload is None or force_refresh or route.generation != self._cached_generation:
            self._cached_global_payload = (
                route.shop.load_settings() if route.shop is not None else load_settings(state_root=self._state_root)
            )
            self._cached_generation = route.generation
        if self._merge_base is None or not route.reloading:
            self._merge_base = copy.deepcopy(self._cached_global_payload)
        return copy.deepcopy(self._cached_global_payload)

    def save_global(self, payload: Mapping[str, Any]) -> Path:
        route = _route(self._state_root)
        if route.shop is None:
            saved_path = save_settings(payload, state_root=self._state_root)
            saved = copy.deepcopy(dict(payload))
        else:
            if self._merge_base is None:
                self.load_global()
            assert self._merge_base is not None
            saved = route.shop.save_settings(base=self._merge_base, new=payload)
            saved_path = route.shop.settings_path
        self._cached_global_payload = saved
        self._merge_base = copy.deepcopy(saved)
        self._cached_generation = _route(self._state_root).generation
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
        self._merge_base = None
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


def _route(state_root: PathInput | None) -> "DocumentRoute":
    from app.features.shop_sharing.service import route_documents

    return route_documents(state_root)


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
