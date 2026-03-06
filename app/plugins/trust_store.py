from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.bootstrap.paths import PathInput, global_plugins_trust_path
from app.persistence.settings_store import load_json_object, save_json_object

_DEFAULT_TRUST_PAYLOAD = {
    "schema_version": 1,
    "trusted_runtime_plugins": {},
}


def load_plugin_trust(state_root: PathInput | None = None) -> dict[str, Any]:
    return load_json_object(global_plugins_trust_path(state_root), default=_DEFAULT_TRUST_PAYLOAD)


def save_plugin_trust(payload: Mapping[str, Any], state_root: PathInput | None = None) -> None:
    save_json_object(global_plugins_trust_path(state_root), payload)


def is_runtime_plugin_trusted(
    plugin_id: str,
    version: str,
    *,
    state_root: PathInput | None = None,
) -> bool:
    payload = load_plugin_trust(state_root)
    trusted_payload = payload.get("trusted_runtime_plugins", {})
    if not isinstance(trusted_payload, dict):
        return False
    version_map = trusted_payload.get(plugin_id, {})
    if not isinstance(version_map, dict):
        return False
    trusted = version_map.get(version)
    return bool(trusted) if isinstance(trusted, bool) else False


def set_runtime_plugin_trust(
    plugin_id: str,
    version: str,
    *,
    trusted: bool,
    state_root: PathInput | None = None,
) -> None:
    payload = load_plugin_trust(state_root)
    trusted_payload = payload.get("trusted_runtime_plugins", {})
    if not isinstance(trusted_payload, dict):
        trusted_payload = {}
    trusted_payload = dict(trusted_payload)
    version_map = trusted_payload.get(plugin_id, {})
    if not isinstance(version_map, dict):
        version_map = {}
    version_map = dict(version_map)
    version_map[version] = bool(trusted)
    trusted_payload[plugin_id] = version_map
    merged_payload = dict(payload)
    merged_payload["trusted_runtime_plugins"] = trusted_payload
    save_plugin_trust(merged_payload, state_root)
