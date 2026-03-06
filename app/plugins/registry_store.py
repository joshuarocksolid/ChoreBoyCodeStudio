from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.bootstrap.paths import PathInput, global_plugins_registry_path
from app.core import constants
from app.plugins.models import PluginRegistry, PluginRegistryEntry
from app.persistence.settings_store import load_json_object, save_json_object


def load_plugin_registry(state_root: PathInput | None = None) -> PluginRegistry:
    payload = load_json_object(
        global_plugins_registry_path(state_root),
        default={"schema_version": constants.PLUGIN_REGISTRY_SCHEMA_VERSION, "entries": []},
    )
    return parse_plugin_registry(payload)


def save_plugin_registry(registry: PluginRegistry, state_root: PathInput | None = None) -> None:
    save_json_object(global_plugins_registry_path(state_root), registry.to_dict())


def upsert_registry_entry(
    entry: PluginRegistryEntry,
    *,
    state_root: PathInput | None = None,
) -> PluginRegistry:
    registry = load_plugin_registry(state_root)
    updated_entries: list[PluginRegistryEntry] = []
    replaced = False
    for current in registry.entries:
        if current.plugin_id == entry.plugin_id and current.version == entry.version:
            updated_entries.append(entry)
            replaced = True
        else:
            updated_entries.append(current)
    if not replaced:
        updated_entries.append(entry)
    updated_registry = PluginRegistry(
        schema_version=registry.schema_version,
        entries=sorted(updated_entries, key=lambda item: (item.plugin_id, item.version)),
    )
    save_plugin_registry(updated_registry, state_root)
    return updated_registry


def remove_registry_entry(
    plugin_id: str,
    *,
    version: str | None = None,
    state_root: PathInput | None = None,
) -> PluginRegistry:
    registry = load_plugin_registry(state_root)
    updated_entries = [
        entry
        for entry in registry.entries
        if not (
            entry.plugin_id == plugin_id
            and (version is None or entry.version == version)
        )
    ]
    updated_registry = PluginRegistry(
        schema_version=registry.schema_version,
        entries=updated_entries,
    )
    save_plugin_registry(updated_registry, state_root)
    return updated_registry


def set_registry_entry_enabled(
    plugin_id: str,
    version: str,
    *,
    enabled: bool,
    state_root: PathInput | None = None,
) -> PluginRegistry:
    registry = load_plugin_registry(state_root)
    updated_entries: list[PluginRegistryEntry] = []
    for entry in registry.entries:
        if entry.plugin_id == plugin_id and entry.version == version:
            updated_entries.append(
                PluginRegistryEntry(
                    plugin_id=entry.plugin_id,
                    version=entry.version,
                    install_path=entry.install_path,
                    enabled=enabled,
                    installed_at=entry.installed_at,
                    last_error=entry.last_error,
                )
            )
        else:
            updated_entries.append(entry)
    updated_registry = PluginRegistry(
        schema_version=registry.schema_version,
        entries=updated_entries,
    )
    save_plugin_registry(updated_registry, state_root)
    return updated_registry


def parse_plugin_registry(payload: Mapping[str, Any]) -> PluginRegistry:
    schema_version = payload.get("schema_version", constants.PLUGIN_REGISTRY_SCHEMA_VERSION)
    if not isinstance(schema_version, int) or schema_version <= 0:
        schema_version = constants.PLUGIN_REGISTRY_SCHEMA_VERSION

    entries_payload = payload.get("entries", [])
    if not isinstance(entries_payload, list):
        entries_payload = []

    entries: list[PluginRegistryEntry] = []
    for item in entries_payload:
        if not isinstance(item, dict):
            continue
        plugin_id = item.get("id")
        version = item.get("version")
        install_path = item.get("install_path")
        enabled = item.get("enabled", True)
        installed_at = item.get("installed_at", "")
        last_error = item.get("last_error")
        if not isinstance(plugin_id, str) or not plugin_id.strip():
            continue
        if not isinstance(version, str) or not version.strip():
            continue
        if not isinstance(install_path, str) or not install_path.strip():
            continue
        if not isinstance(enabled, bool):
            enabled = True
        if not isinstance(installed_at, str):
            installed_at = ""
        if last_error is not None and not isinstance(last_error, str):
            last_error = None
        entries.append(
            PluginRegistryEntry(
                plugin_id=plugin_id.strip(),
                version=version.strip(),
                install_path=install_path.strip(),
                enabled=enabled,
                installed_at=installed_at,
                last_error=last_error,
            )
        )

    return PluginRegistry(
        schema_version=schema_version,
        entries=sorted(entries, key=lambda item: (item.plugin_id, item.version)),
    )
