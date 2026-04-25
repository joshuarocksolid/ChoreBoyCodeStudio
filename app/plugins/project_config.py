from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.bootstrap.logging_setup import get_subsystem_logger
from app.bootstrap.paths import project_plugins_path
from app.core import constants
from app.persistence.settings_store import load_json_object, save_json_object

_LOGGER = get_subsystem_logger("plugins")


@dataclass(frozen=True)
class ProjectPluginConfig:
    schema_version: int = constants.PLUGIN_PROJECT_CONFIG_SCHEMA_VERSION
    enabled_plugins: tuple[str, ...] = field(default_factory=tuple)
    disabled_plugins: tuple[str, ...] = field(default_factory=tuple)
    pinned_versions: dict[str, str] = field(default_factory=dict)
    preferred_providers: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "enabled_plugins": list(self.enabled_plugins),
            "disabled_plugins": list(self.disabled_plugins),
            "pinned_versions": dict(self.pinned_versions),
            "preferred_providers": dict(self.preferred_providers),
        }


def preferred_provider_key(kind: str, *, language: str | None = None) -> str:
    normalized_kind = kind.strip()
    if not normalized_kind:
        raise ValueError("kind must be a non-empty string")
    if language is None or not language.strip():
        return normalized_kind
    return f"{normalized_kind}:{language.strip().lower()}"


def load_project_plugin_config(project_root: str) -> ProjectPluginConfig:
    payload = load_json_object(
        project_plugins_path(project_root),
        default={
            "schema_version": constants.PLUGIN_PROJECT_CONFIG_SCHEMA_VERSION,
            "enabled_plugins": [],
            "disabled_plugins": [],
            "pinned_versions": {},
            "preferred_providers": {},
        },
    )
    return parse_project_plugin_config(payload)


def load_project_plugin_config_or_none(project_root: str) -> ProjectPluginConfig | None:
    try:
        return load_project_plugin_config(project_root)
    except Exception as exc:
        _LOGGER.warning(
            "Failed to load project plugin config for %s: %s",
            project_root,
            exc,
            exc_info=True,
        )
        return None


def save_project_plugin_config(config: ProjectPluginConfig, project_root: str) -> None:
    save_json_object(project_plugins_path(project_root), config.to_dict())


def parse_project_plugin_config(payload: Mapping[str, Any]) -> ProjectPluginConfig:
    schema_version = payload.get("schema_version", constants.PLUGIN_PROJECT_CONFIG_SCHEMA_VERSION)
    if not isinstance(schema_version, int) or schema_version <= 0:
        schema_version = constants.PLUGIN_PROJECT_CONFIG_SCHEMA_VERSION
    enabled_plugins = tuple(_normalize_string_list(payload.get("enabled_plugins", [])))
    disabled_plugins = tuple(_normalize_string_list(payload.get("disabled_plugins", [])))
    pinned_versions = _normalize_string_map(payload.get("pinned_versions", {}))
    preferred_providers = _normalize_string_map(payload.get("preferred_providers", {}))
    return ProjectPluginConfig(
        schema_version=schema_version,
        enabled_plugins=enabled_plugins,
        disabled_plugins=disabled_plugins,
        pinned_versions=pinned_versions,
        preferred_providers=preferred_providers,
    )


def set_project_plugin_enabled(project_root: str, plugin_id: str, *, enabled: bool) -> ProjectPluginConfig:
    config = load_project_plugin_config(project_root)
    enabled_plugins = [item for item in config.enabled_plugins if item != plugin_id]
    disabled_plugins = [item for item in config.disabled_plugins if item != plugin_id]
    target_list = enabled_plugins if enabled else disabled_plugins
    target_list.append(plugin_id)
    updated = ProjectPluginConfig(
        schema_version=config.schema_version,
        enabled_plugins=tuple(sorted(set(enabled_plugins))),
        disabled_plugins=tuple(sorted(set(disabled_plugins))),
        pinned_versions=dict(config.pinned_versions),
        preferred_providers=dict(config.preferred_providers),
    )
    save_project_plugin_config(updated, project_root)
    return updated


def set_project_plugin_version_pin(
    project_root: str,
    plugin_id: str,
    version: str | None,
) -> ProjectPluginConfig:
    config = load_project_plugin_config(project_root)
    pinned_versions = dict(config.pinned_versions)
    if version is None or not version.strip():
        pinned_versions.pop(plugin_id, None)
    else:
        pinned_versions[plugin_id] = version.strip()
    updated = ProjectPluginConfig(
        schema_version=config.schema_version,
        enabled_plugins=tuple(config.enabled_plugins),
        disabled_plugins=tuple(config.disabled_plugins),
        pinned_versions=pinned_versions,
        preferred_providers=dict(config.preferred_providers),
    )
    save_project_plugin_config(updated, project_root)
    return updated


def set_project_preferred_provider(
    project_root: str,
    selector_key: str,
    provider_id: str | None,
) -> ProjectPluginConfig:
    config = load_project_plugin_config(project_root)
    preferred_providers = dict(config.preferred_providers)
    normalized_key = selector_key.strip()
    if provider_id is None or not provider_id.strip():
        preferred_providers.pop(normalized_key, None)
    else:
        preferred_providers[normalized_key] = provider_id.strip()
    updated = ProjectPluginConfig(
        schema_version=config.schema_version,
        enabled_plugins=tuple(config.enabled_plugins),
        disabled_plugins=tuple(config.disabled_plugins),
        pinned_versions=dict(config.pinned_versions),
        preferred_providers=preferred_providers,
    )
    save_project_plugin_config(updated, project_root)
    return updated


def is_plugin_enabled_in_project(
    plugin_id: str,
    *,
    config: ProjectPluginConfig | None,
    default_enabled: bool,
) -> bool:
    if config is None:
        return default_enabled
    if plugin_id in config.disabled_plugins:
        return False
    if plugin_id in config.enabled_plugins:
        return True
    return default_enabled


def is_plugin_version_pinned(
    plugin_id: str,
    version: str,
    *,
    config: ProjectPluginConfig | None,
) -> bool:
    if config is None:
        return True
    pinned_version = config.pinned_versions.get(plugin_id)
    if pinned_version is None:
        return True
    return pinned_version == version


def preferred_provider_for(
    kind: str,
    *,
    config: ProjectPluginConfig | None,
    language: str | None = None,
) -> str | None:
    if config is None:
        return None
    scoped_key = preferred_provider_key(kind, language=language)
    if scoped_key in config.preferred_providers:
        return config.preferred_providers[scoped_key]
    return config.preferred_providers.get(kind)


def _normalize_string_list(raw_value: object) -> list[str]:
    if not isinstance(raw_value, list):
        return []
    normalized: list[str] = []
    for item in raw_value:
        if not isinstance(item, str):
            continue
        stripped = item.strip()
        if stripped and stripped not in normalized:
            normalized.append(stripped)
    return sorted(normalized)


def _normalize_string_map(raw_value: object) -> dict[str, str]:
    if not isinstance(raw_value, dict):
        return {}
    normalized: dict[str, str] = {}
    for key, value in raw_value.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        stripped_key = key.strip()
        stripped_value = value.strip()
        if stripped_key and stripped_value:
            normalized[stripped_key] = stripped_value
    return normalized
