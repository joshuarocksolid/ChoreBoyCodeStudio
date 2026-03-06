"""JSON-backed persistence helpers for global app state."""

from __future__ import annotations

from copy import deepcopy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.bootstrap.paths import PathInput, ensure_directory, global_settings_path, project_settings_path
from app.core import constants

SETTINGS_SCHEMA_VERSION = 1
DEFAULT_SETTINGS: dict[str, Any] = {
    "schema_version": SETTINGS_SCHEMA_VERSION,
}


def load_json_object(path: PathInput, *, default: Mapping[str, Any]) -> dict[str, Any]:
    """Load a JSON object from disk, returning default on read/parse failures."""
    default_payload = _copy_mapping(default)
    resolved_path = Path(path).expanduser().resolve()

    try:
        raw_content = resolved_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return default_payload
    except OSError:
        return default_payload

    try:
        parsed_payload = json.loads(raw_content)
    except json.JSONDecodeError:
        return default_payload

    if not isinstance(parsed_payload, dict):
        return default_payload
    return dict(parsed_payload)


def save_json_object(path: PathInput, payload: Mapping[str, Any]) -> Path:
    """Persist a JSON object to disk with deterministic formatting."""
    normalized_payload = _copy_mapping(payload)
    resolved_path = Path(path).expanduser().resolve()
    ensure_directory(resolved_path.parent)

    serialized = json.dumps(normalized_payload, indent=2, sort_keys=True) + "\n"
    temp_path = resolved_path.with_suffix(f"{resolved_path.suffix}.tmp")
    temp_path.write_text(serialized, encoding="utf-8")
    temp_path.replace(resolved_path)
    return resolved_path


def load_settings(state_root: PathInput | None = None) -> dict[str, Any]:
    """Load global settings from the canonical settings path."""
    return load_json_object(global_settings_path(state_root), default=DEFAULT_SETTINGS)


def save_settings(payload: Mapping[str, Any], state_root: PathInput | None = None) -> Path:
    """Save global settings to the canonical settings path."""
    return save_json_object(global_settings_path(state_root), payload)


def load_project_settings(project_root: PathInput) -> dict[str, Any]:
    """Load per-project settings from `<project>/cbcs/settings.json`."""
    return load_json_object(project_settings_path(project_root), default=DEFAULT_SETTINGS)


def save_project_settings(project_root: PathInput, payload: Mapping[str, Any]) -> Path:
    """Persist per-project settings after scope filtering."""
    return save_json_object(
        project_settings_path(project_root),
        filter_project_settings_payload(payload),
    )


def filter_project_settings_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a sanitized payload containing only project-overridable sections."""
    normalized: dict[str, Any] = {
        "schema_version": _coerce_schema_version(payload.get("schema_version")),
    }
    for key in constants.PROJECT_SETTINGS_OVERRIDABLE_ROOT_KEYS:
        value = payload.get(key)
        if isinstance(value, Mapping):
            normalized[key] = _deepcopy_mapping(value)
    return normalized


def compute_effective_settings_payload(
    global_settings_payload: Mapping[str, Any],
    project_settings_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute effective settings payload via defaults -> global -> project layers."""
    merged = _deep_merge_mappings(DEFAULT_SETTINGS, global_settings_payload)
    if project_settings_payload is None:
        return merged
    filtered_project_payload = filter_project_settings_payload(project_settings_payload)
    return _deep_merge_mappings(merged, filtered_project_payload)


def project_settings_has_overrides(payload: Mapping[str, Any]) -> bool:
    """Return True when payload contains at least one project settings override."""
    filtered_payload = filter_project_settings_payload(payload)
    return any(key in filtered_payload for key in constants.PROJECT_SETTINGS_OVERRIDABLE_ROOT_KEYS)


def _copy_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be a mapping object.")
    return dict(payload)


def _deepcopy_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): deepcopy(value) for key, value in payload.items() if isinstance(key, str)}


def _deep_merge_mappings(
    base_payload: Mapping[str, Any],
    override_payload: Mapping[str, Any],
) -> dict[str, Any]:
    merged: dict[str, Any] = _deepcopy_mapping(base_payload)
    for key, override_value in override_payload.items():
        if not isinstance(key, str):
            continue
        base_value = merged.get(key)
        if isinstance(base_value, Mapping) and isinstance(override_value, Mapping):
            merged[key] = _deep_merge_mappings(base_value, override_value)
            continue
        merged[key] = deepcopy(override_value)
    return merged


def _coerce_schema_version(raw_value: Any) -> int:
    if isinstance(raw_value, int) and not isinstance(raw_value, bool) and raw_value > 0:
        return raw_value
    return SETTINGS_SCHEMA_VERSION
