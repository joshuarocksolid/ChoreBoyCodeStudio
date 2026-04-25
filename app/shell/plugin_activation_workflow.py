"""Plugin activation orchestration for the shell."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, Sequence

from app.bootstrap.paths import PathInput
from app.plugins.discovery import discover_installed_plugins
from app.plugins.models import DiscoveredPlugin, PluginRegistry, PluginRegistryEntry
from app.plugins.project_config import (
    ProjectPluginConfig,
    is_plugin_enabled_in_project,
    is_plugin_version_pinned,
    load_project_plugin_config_or_none,
    preferred_provider_key,
)
from app.plugins.registry_store import load_plugin_registry
from app.plugins.workflow_catalog import WorkflowProviderCatalog, provider_key


PluginKey = tuple[str, str]


class _PluginDiscoveryLoader(Protocol):
    def __call__(
        self,
        *,
        state_root: PathInput | None = None,
        include_bundled: bool = False,
    ) -> list[DiscoveredPlugin]:
        ...


class _ContributionManager(Protocol):
    def clear(self) -> None:
        ...

    def apply(
        self,
        discovered_plugins: list[DiscoveredPlugin],
        *,
        enabled_map: dict[PluginKey, bool],
    ) -> None:
        ...


class _PluginRuntimeManager(Protocol):
    def stop(self) -> None:
        ...


class _PluginApiBroker(Protocol):
    def reload_runtime_plugins(self) -> None:
        ...


class _WorkflowBroker(Protocol):
    def set_plugin_catalog(
        self,
        catalog: WorkflowProviderCatalog,
        *,
        project_config: ProjectPluginConfig | None = None,
    ) -> None:
        ...


@dataclass(frozen=True)
class ProviderPreferenceOption:
    label: str
    selector_key: str
    provider_key: str


@dataclass(frozen=True)
class PluginDisplayState:
    effective_enabled: bool
    project_status: str
    preferred_selectors: tuple[str, ...] = ()


@dataclass(frozen=True)
class PluginActivationSnapshot:
    registry: PluginRegistry
    registry_map: dict[PluginKey, PluginRegistryEntry]
    registry_enabled_map: dict[PluginKey, bool]
    project_config: ProjectPluginConfig | None
    discovered_plugins: list[DiscoveredPlugin]
    effective_enabled_map: dict[PluginKey, bool]
    workflow_provider_catalog: WorkflowProviderCatalog

    def display_state_for(self, discovered: DiscoveredPlugin) -> PluginDisplayState:
        return plugin_display_state(discovered, self)


class PluginActivationWorkflow:
    """Owns plugin contribution reload and effective activation state."""

    def __init__(
        self,
        *,
        state_root: PathInput | None,
        project_root_provider: Callable[[], str | None],
        safe_mode_enabled: Callable[[], bool],
        contribution_manager: _ContributionManager,
        runtime_manager: _PluginRuntimeManager,
        plugin_api_broker: _PluginApiBroker,
        workflow_broker: _WorkflowBroker,
        on_catalog_changed: Callable[[WorkflowProviderCatalog], None] | None = None,
        registry_loader: Callable[[PathInput | None], PluginRegistry] = load_plugin_registry,
        discovery_loader: _PluginDiscoveryLoader = discover_installed_plugins,
        project_config_loader: Callable[[str], ProjectPluginConfig | None] = load_project_plugin_config_or_none,
    ) -> None:
        self._state_root = state_root
        self._project_root_provider = project_root_provider
        self._safe_mode_enabled = safe_mode_enabled
        self._contribution_manager = contribution_manager
        self._runtime_manager = runtime_manager
        self._plugin_api_broker = plugin_api_broker
        self._workflow_broker = workflow_broker
        self._on_catalog_changed = on_catalog_changed
        self._registry_loader = registry_loader
        self._discovery_loader = discovery_loader
        self._project_config_loader = project_config_loader

    def reload(self) -> None:
        if self._safe_mode_enabled():
            empty_catalog = WorkflowProviderCatalog([])
            self._contribution_manager.clear()
            self._runtime_manager.stop()
            self._workflow_broker.set_plugin_catalog(empty_catalog)
            self._publish_catalog(empty_catalog)
            return

        snapshot = self.snapshot()
        self._contribution_manager.apply(
            snapshot.discovered_plugins,
            enabled_map=snapshot.effective_enabled_map,
        )
        self._workflow_broker.set_plugin_catalog(
            snapshot.workflow_provider_catalog,
            project_config=snapshot.project_config,
        )
        self._publish_catalog(snapshot.workflow_provider_catalog)
        self._plugin_api_broker.reload_runtime_plugins()

    def snapshot(self, *, project_root: str | None = None) -> PluginActivationSnapshot:
        resolved_project_root = self._project_root_provider() if project_root is None else project_root
        registry = self._registry_loader(self._state_root)
        registry_map = {
            (entry.plugin_id, entry.version): entry
            for entry in registry.entries
        }
        registry_enabled_map = {
            (entry.plugin_id, entry.version): entry.enabled
            for entry in registry.entries
        }
        project_config = (
            self._project_config_loader(resolved_project_root)
            if resolved_project_root
            else None
        )
        discovered_plugins = self._discovery_loader(
            state_root=self._state_root,
            include_bundled=True,
        )
        effective_enabled_map = build_effective_enabled_map(
            discovered_plugins,
            registry_enabled_map=registry_enabled_map,
            project_config=project_config,
        )
        if self._safe_mode_enabled():
            effective_enabled_map = {
                key: False
                for key in effective_enabled_map
            }
            workflow_provider_catalog = WorkflowProviderCatalog([])
        else:
            workflow_provider_catalog = WorkflowProviderCatalog.from_plugins(
                discovered_plugins,
                enabled_map=effective_enabled_map,
                project_config=project_config,
            )
        return PluginActivationSnapshot(
            registry=registry,
            registry_map=registry_map,
            registry_enabled_map=registry_enabled_map,
            project_config=project_config,
            discovered_plugins=discovered_plugins,
            effective_enabled_map=effective_enabled_map,
            workflow_provider_catalog=workflow_provider_catalog,
        )

    def _publish_catalog(self, catalog: WorkflowProviderCatalog) -> None:
        if self._on_catalog_changed is not None:
            self._on_catalog_changed(catalog)


def build_effective_enabled_map(
    discovered_plugins: Sequence[DiscoveredPlugin],
    *,
    registry_enabled_map: Mapping[PluginKey, bool],
    project_config: ProjectPluginConfig | None,
) -> dict[PluginKey, bool]:
    enabled_map = dict(registry_enabled_map)
    for discovered in discovered_plugins:
        key = (discovered.plugin_id, discovered.version)
        default_enabled = enabled_map.get(key, True)
        if not is_plugin_version_pinned(
            discovered.plugin_id,
            discovered.version,
            config=project_config,
        ):
            enabled_map[key] = False
            continue
        enabled_map[key] = is_plugin_enabled_in_project(
            discovered.plugin_id,
            config=project_config,
            default_enabled=default_enabled,
        )
    return enabled_map


def plugin_display_state(
    discovered: DiscoveredPlugin,
    snapshot: PluginActivationSnapshot,
) -> PluginDisplayState:
    key = (discovered.plugin_id, discovered.version)
    effective_enabled = snapshot.effective_enabled_map.get(key, True)
    project_status = "-"
    preferred_selectors: tuple[str, ...] = ()
    project_config = snapshot.project_config
    if project_config is not None:
        pinned_version = project_config.pinned_versions.get(discovered.plugin_id)
        pin_matches = pinned_version is None or pinned_version == discovered.version
        if pinned_version is not None:
            project_status = f"pinned {pinned_version}"
        if pin_matches:
            if discovered.plugin_id in project_config.enabled_plugins:
                project_status = "enabled"
            if discovered.plugin_id in project_config.disabled_plugins:
                project_status = "disabled"
        if discovered.manifest is not None:
            preferred_selectors = matching_preferred_selector_keys(
                project_config.preferred_providers,
                discovered.plugin_id,
                [
                    provider.to_dict()
                    for provider in discovered.manifest.workflow_providers
                ],
            )
    return PluginDisplayState(
        effective_enabled=effective_enabled,
        project_status=project_status,
        preferred_selectors=preferred_selectors,
    )


def matching_preferred_selector_keys(
    preferred_providers: Mapping[str, str],
    plugin_id: str,
    provider_entries: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    matched: list[str] = []
    for option in provider_preference_options(plugin_id, provider_entries):
        if (
            preferred_providers.get(option.selector_key) == option.provider_key
            and option.selector_key not in matched
        ):
            matched.append(option.selector_key)
    return tuple(matched)


def provider_preference_options(
    plugin_id: str,
    provider_entries: Sequence[Mapping[str, object]],
) -> tuple[ProviderPreferenceOption, ...]:
    options: list[ProviderPreferenceOption] = []
    seen: set[tuple[str, str]] = set()
    for provider_entry in provider_entries:
        provider_id = provider_entry.get("id")
        kind = provider_entry.get("kind")
        title = provider_entry.get("title")
        languages = provider_entry.get("languages", [])
        if not isinstance(provider_id, str) or not provider_id.strip():
            continue
        if not isinstance(kind, str) or not kind.strip():
            continue
        stripped_provider_id = provider_id.strip()
        stripped_kind = kind.strip()
        label_prefix = title.strip() if isinstance(title, str) and title.strip() else stripped_provider_id
        provider_key_value = provider_key(plugin_id, stripped_provider_id)
        generic_selector = preferred_provider_key(stripped_kind)
        generic_key = (generic_selector, provider_key_value)
        if generic_key not in seen:
            options.append(
                ProviderPreferenceOption(
                    label=f"{label_prefix} ({stripped_kind}, all languages)",
                    selector_key=generic_selector,
                    provider_key=provider_key_value,
                )
            )
            seen.add(generic_key)
        if isinstance(languages, list):
            for language in languages:
                if not isinstance(language, str) or not language.strip():
                    continue
                scoped_selector = preferred_provider_key(stripped_kind, language=language)
                scoped_key = (scoped_selector, provider_key_value)
                if scoped_key in seen:
                    continue
                normalized_language = language.strip().lower()
                options.append(
                    ProviderPreferenceOption(
                        label=f"{label_prefix} ({stripped_kind}, {normalized_language})",
                        selector_key=scoped_selector,
                        provider_key=provider_key_value,
                    )
                )
                seen.add(scoped_key)
    return tuple(options)
