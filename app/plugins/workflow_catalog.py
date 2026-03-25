from __future__ import annotations

from pathlib import Path

from app.core import constants
from app.plugins.models import DiscoveredPlugin, DiscoveredWorkflowProvider, PluginWorkflowProvider
from app.plugins.project_config import (
    ProjectPluginConfig,
    is_plugin_enabled_in_project,
    is_plugin_version_pinned,
)


class WorkflowProviderCatalog:
    def __init__(self, providers: list[DiscoveredWorkflowProvider]) -> None:
        self._providers = sorted(
            providers,
            key=lambda item: (-item.provider.priority, item.provider_key),
        )
        self._providers_by_key = {
            provider.provider_key: provider for provider in self._providers
        }

    @property
    def providers(self) -> list[DiscoveredWorkflowProvider]:
        return list(self._providers)

    @classmethod
    def from_plugins(
        cls,
        discovered_plugins: list[DiscoveredPlugin],
        *,
        enabled_map: dict[tuple[str, str], bool],
        project_config: ProjectPluginConfig | None = None,
    ) -> "WorkflowProviderCatalog":
        providers: list[DiscoveredWorkflowProvider] = []
        for discovered in discovered_plugins:
            if discovered.manifest is None:
                continue
            if discovered.compatibility is not None and not discovered.compatibility.is_compatible:
                continue
            default_enabled = enabled_map.get((discovered.plugin_id, discovered.version), True)
            if not is_plugin_enabled_in_project(
                discovered.plugin_id,
                config=project_config,
                default_enabled=default_enabled,
            ):
                continue
            if not is_plugin_version_pinned(
                discovered.plugin_id,
                discovered.version,
                config=project_config,
            ):
                continue
            manifest_capabilities = set(discovered.manifest.capabilities)
            manifest_permissions = set(discovered.manifest.permissions)
            for provider in discovered.manifest.workflow_providers:
                required_capability = _default_capability_for_provider_kind(provider.kind)
                provider_capabilities = set(provider.capabilities) or {required_capability}
                if not provider_capabilities.issubset(manifest_capabilities):
                    continue
                provider_permissions = set(provider.permissions)
                if provider_permissions and not provider_permissions.issubset(manifest_permissions):
                    continue
                providers.append(
                    DiscoveredWorkflowProvider(
                        plugin_id=discovered.plugin_id,
                        plugin_version=discovered.version,
                        source_kind=discovered.source_kind,
                        install_path=discovered.install_path,
                        provider=provider,
                        manifest=discovered.manifest,
                        provider_key=provider_key(discovered.plugin_id, provider.provider_id),
                    )
                )
        return cls(providers)

    def get(self, provider_key_value: str) -> DiscoveredWorkflowProvider | None:
        return self._providers_by_key.get(provider_key_value)

    def list_matching(
        self,
        *,
        kind: str | None = None,
        lane: str | None = None,
        language: str | None = None,
        file_path: str | None = None,
    ) -> list[DiscoveredWorkflowProvider]:
        return [
            provider
            for provider in self._providers
            if _matches_provider_context(
                provider.provider,
                kind=kind,
                lane=lane,
                language=language,
                file_path=file_path,
            )
        ]

    def select(
        self,
        *,
        kind: str,
        lane: str | None = None,
        preferred_provider_key: str | None = None,
        language: str | None = None,
        file_path: str | None = None,
    ) -> DiscoveredWorkflowProvider | None:
        if preferred_provider_key:
            preferred = self.get(preferred_provider_key)
            if preferred is not None and _matches_provider_context(
                preferred.provider,
                kind=kind,
                lane=lane,
                language=language,
                file_path=file_path,
            ):
                return preferred
        matches = self.list_matching(
            kind=kind,
            lane=lane,
            language=language,
            file_path=file_path,
        )
        if not matches:
            return None
        return matches[0]


def provider_key(plugin_id: str, provider_id: str) -> str:
    return f"{plugin_id}:{provider_id}"


def _default_capability_for_provider_kind(kind: str) -> str:
    return {
        constants.WORKFLOW_PROVIDER_KIND_FORMATTER: constants.PLUGIN_CAPABILITY_WORKFLOW_FORMATTER,
        constants.WORKFLOW_PROVIDER_KIND_IMPORT_ORGANIZER: constants.PLUGIN_CAPABILITY_WORKFLOW_IMPORT_ORGANIZER,
        constants.WORKFLOW_PROVIDER_KIND_DIAGNOSTICS: constants.PLUGIN_CAPABILITY_WORKFLOW_DIAGNOSTICS,
        constants.WORKFLOW_PROVIDER_KIND_TEST: constants.PLUGIN_CAPABILITY_WORKFLOW_TEST,
        constants.WORKFLOW_PROVIDER_KIND_TEMPLATE: constants.PLUGIN_CAPABILITY_WORKFLOW_TEMPLATE,
        constants.WORKFLOW_PROVIDER_KIND_PACKAGING: constants.PLUGIN_CAPABILITY_WORKFLOW_PACKAGING,
        constants.WORKFLOW_PROVIDER_KIND_RUNTIME_EXPLAINER: constants.PLUGIN_CAPABILITY_WORKFLOW_RUNTIME_EXPLAINER,
        constants.WORKFLOW_PROVIDER_KIND_FREECAD_HELPER: constants.PLUGIN_CAPABILITY_WORKFLOW_FREECAD_HELPER,
        constants.WORKFLOW_PROVIDER_KIND_DEPENDENCY_AUDIT: constants.PLUGIN_CAPABILITY_WORKFLOW_DEPENDENCY_AUDIT,
    }[kind]


def _matches_provider_context(
    provider: PluginWorkflowProvider,
    *,
    kind: str | None,
    lane: str | None,
    language: str | None,
    file_path: str | None,
) -> bool:
    if kind is not None and provider.kind != kind:
        return False
    if lane is not None and provider.lane != lane:
        return False
    if language is not None and provider.languages:
        normalized_language = language.strip().lower()
        if normalized_language not in {value.lower() for value in provider.languages}:
            return False
    if file_path is not None and provider.file_extensions:
        suffix = Path(file_path).suffix.lower()
        if suffix not in {value.lower() for value in provider.file_extensions}:
            return False
    return True
