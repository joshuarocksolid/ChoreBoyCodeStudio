"""JSON-backed persistence helpers for global app state."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.bootstrap.paths import PathInput, ensure_directory, global_settings_path

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


def _copy_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be a mapping object.")
    return dict(payload)
