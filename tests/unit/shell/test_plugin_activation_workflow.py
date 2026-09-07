"""Unit tests for plugin activation workflow orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.core import constants
from app.plugins.models import (
    DiscoveredPlugin,
    PluginManifest,
    PluginRegistry,
    PluginRegistryEntry,
    PluginWorkflowProvider,
)
from app.plugins.project_config import ProjectPluginConfig
from app.plugins.workflow_catalog import WorkflowProviderCatalog, provider_key
from app.shell.plugin_activation_workflow import (
    PluginActivationWorkflow,
    build_effective_enabled_map,
)

pytestmark = pytest.mark.unit


@dataclass
class RecordingContributionManager:
    cleared_count: int = 0
    applied: list[tuple[list[DiscoveredPlugin], dict[tuple[str, str], bool]]] = field(default_factory=list)

    def clear(self) -> None:
        self.cleared_count += 1

    def apply(
        self,
        discovered_plugins: list[DiscoveredPlugin],
        *,
        enabled_map: dict[tuple[str, str], bool],
    ) -> None:
        self.applied.append((list(discovered_plugins), dict(enabled_map)))


@dataclass
class RecordingRuntimeManager:
    stopped_count: int = 0

    def stop(self) -> None:
        self.stopped_count += 1


@dataclass
class RecordingApiBroker:
    reload_count: int = 0

    def reload_runtime_plugins(self) -> None:
        self.reload_count += 1


@dataclass
class RecordingWorkflowBroker:
    calls: list[tuple[WorkflowProviderCatalog, ProjectPluginConfig | None]] = field(default_factory=list)

    def set_plugin_catalog(
        self,
        catalog: WorkflowProviderCatalog,
        *,
        project_config: ProjectPluginConfig | None = None,
    ) -> None:
        self.calls.append((catalog, project_config))


def _workflow_provider(provider_id: str = "formatter") -> PluginWorkflowProvider:
    return PluginWorkflowProvider(
        provider_id=provider_id,
        kind=constants.WORKFLOW_PROVIDER_KIND_FORMATTER,
        lane=constants.WORKFLOW_PROVIDER_LANE_QUERY,
        title="Formatter",
        languages=("python",),
        file_extensions=(".py",),
        query_handler="format_python",
    )


def _plugin(plugin_id: str, version: str, *, enabled_provider: bool = True) -> DiscoveredPlugin:
    providers = [_workflow_provider()] if enabled_provider else []
    manifest = PluginManifest(
        plugin_id=plugin_id,
        name=plugin_id,
        version=version,
        api_version=constants.PLUGIN_API_VERSION,
        runtime_entrypoint="runtime.py",
        capabilities=[constants.PLUGIN_CAPABILITY_WORKFLOW_FORMATTER],
        permissions=[constants.PLUGIN_PERMISSION_PROJECT_READ],
        workflow_providers=providers,
    )
    return DiscoveredPlugin(
        plugin_id=plugin_id,
        version=version,
        install_path=f"/plugins/{plugin_id}/{version}",
        manifest_path=f"/plugins/{plugin_id}/{version}/plugin.json",
        manifest=manifest,
    )


def _registry(entries: list[PluginRegistryEntry]) -> PluginRegistry:
    return PluginRegistry(
        schema_version=constants.PLUGIN_REGISTRY_SCHEMA_VERSION,
        entries=entries,
    )


def test_effective_enabled_map_prefers_pin_mismatch_over_project_enable() -> None:
    discovered = [
        _plugin("acme.formatter", "1.0.0"),
        _plugin("acme.formatter", "2.0.0"),
        _plugin("acme.disabled", "1.0.0"),
    ]
    config = ProjectPluginConfig(
        enabled_plugins=("acme.formatter",),
        disabled_plugins=("acme.disabled",),
        pinned_versions={"acme.formatter": "1.0.0"},
    )

    enabled_map = build_effective_enabled_map(
        discovered,
        registry_enabled_map={
            ("acme.formatter", "1.0.0"): False,
            ("acme.formatter", "2.0.0"): True,
            ("acme.disabled", "1.0.0"): True,
        },
        project_config=config,
    )

    assert enabled_map[("acme.formatter", "1.0.0")] is True
    assert enabled_map[("acme.formatter", "2.0.0")] is False
    assert enabled_map[("acme.disabled", "1.0.0")] is False


def test_reload_applies_contributions_catalog_and_runtime_reload() -> None:
    discovered_plugins = [_plugin("acme.formatter", "1.0.0")]
    registry_entries = [
        PluginRegistryEntry(
            plugin_id="acme.formatter",
            version="1.0.0",
            install_path="/plugins/acme.formatter/1.0.0",
            enabled=True,
        )
    ]
    contribution_manager = RecordingContributionManager()
    api_broker = RecordingApiBroker()
    workflow_broker = RecordingWorkflowBroker()
    published_catalogs: list[WorkflowProviderCatalog] = []
    workflow = PluginActivationWorkflow(
        state_root=None,
        project_root_provider=lambda: "/project",
        safe_mode_enabled=lambda: False,
        contribution_manager=contribution_manager,
        runtime_manager=RecordingRuntimeManager(),
        plugin_api_broker=api_broker,
        workflow_broker=workflow_broker,
        on_catalog_changed=published_catalogs.append,
        registry_loader=lambda _state_root: _registry(registry_entries),
        discovery_loader=lambda **_kwargs: list(discovered_plugins),
        project_config_loader=lambda _project_root: ProjectPluginConfig(),
    )

    workflow.reload()

    assert len(contribution_manager.applied) == 1
    applied_plugins, applied_enabled_map = contribution_manager.applied[0]
    assert [plugin.plugin_id for plugin in applied_plugins] == ["acme.formatter"]
    assert applied_enabled_map[("acme.formatter", "1.0.0")] is True
    assert api_broker.reload_count == 1
    assert len(workflow_broker.calls) == 1
    assert workflow_broker.calls[0][0].providers[0].provider_key == provider_key("acme.formatter", "formatter")
    assert published_catalogs == [workflow_broker.calls[0][0]]


def test_reload_refreshes_discovery_after_install() -> None:
    discovered_plugins = [_plugin("acme.one", "1.0.0")]
    registry_entries = [
        PluginRegistryEntry("acme.one", "1.0.0", "/plugins/acme.one/1.0.0", enabled=True)
    ]
    contribution_manager = RecordingContributionManager()
    workflow = PluginActivationWorkflow(
        state_root=None,
        project_root_provider=lambda: None,
        safe_mode_enabled=lambda: False,
        contribution_manager=contribution_manager,
        runtime_manager=RecordingRuntimeManager(),
        plugin_api_broker=RecordingApiBroker(),
        workflow_broker=RecordingWorkflowBroker(),
        registry_loader=lambda _state_root: _registry(registry_entries),
        discovery_loader=lambda **_kwargs: list(discovered_plugins),
        project_config_loader=lambda _project_root: None,
    )

    workflow.reload()
    discovered_plugins.append(_plugin("acme.two", "1.0.0"))
    registry_entries.append(
        PluginRegistryEntry("acme.two", "1.0.0", "/plugins/acme.two/1.0.0", enabled=True)
    )
    workflow.reload()

    assert [
        [plugin.plugin_id for plugin in applied_plugins]
        for applied_plugins, _enabled_map in contribution_manager.applied
    ] == [["acme.one"], ["acme.one", "acme.two"]]


def test_safe_mode_clears_contributions_stops_runtime_and_installs_empty_catalog() -> None:
    contribution_manager = RecordingContributionManager()
    runtime_manager = RecordingRuntimeManager()
    api_broker = RecordingApiBroker()
    workflow_broker = RecordingWorkflowBroker()
    workflow = PluginActivationWorkflow(
        state_root=None,
        project_root_provider=lambda: None,
        safe_mode_enabled=lambda: True,
        contribution_manager=contribution_manager,
        runtime_manager=runtime_manager,
        plugin_api_broker=api_broker,
        workflow_broker=workflow_broker,
        registry_loader=lambda _state_root: pytest.fail("safe-mode reload should not load registry"),
        discovery_loader=lambda **_kwargs: pytest.fail("safe-mode reload should not discover plugins"),
        project_config_loader=lambda _project_root: None,
    )

    workflow.reload()

    assert contribution_manager.cleared_count == 1
    assert runtime_manager.stopped_count == 1
    assert api_broker.reload_count == 0
    assert len(workflow_broker.calls) == 1
    assert workflow_broker.calls[0][0].providers == []
    assert workflow_broker.calls[0][1] is None


def test_snapshot_uses_same_effective_state_for_display_and_catalog() -> None:
    older = _plugin("acme.formatter", "1.0.0")
    newer = _plugin("acme.formatter", "2.0.0")
    config = ProjectPluginConfig(
        enabled_plugins=("acme.formatter",),
        pinned_versions={"acme.formatter": "1.0.0"},
        preferred_providers={
            "formatter:python": provider_key("acme.formatter", "formatter"),
        },
    )
    workflow = PluginActivationWorkflow(
        state_root=None,
        project_root_provider=lambda: "/project",
        safe_mode_enabled=lambda: False,
        contribution_manager=RecordingContributionManager(),
        runtime_manager=RecordingRuntimeManager(),
        plugin_api_broker=RecordingApiBroker(),
        workflow_broker=RecordingWorkflowBroker(),
        registry_loader=lambda _state_root: _registry(
            [
                PluginRegistryEntry("acme.formatter", "1.0.0", older.install_path, enabled=True),
                PluginRegistryEntry("acme.formatter", "2.0.0", newer.install_path, enabled=True),
            ]
        ),
        discovery_loader=lambda **_kwargs: [older, newer],
        project_config_loader=lambda _project_root: config,
    )

    snapshot = workflow.snapshot()
    older_display = snapshot.display_state_for(older)
    newer_display = snapshot.display_state_for(newer)

    assert older_display.effective_enabled is True
    assert older_display.project_status == "enabled"
    assert older_display.preferred_selectors == ("formatter:python",)
    assert newer_display.effective_enabled is False
    assert newer_display.project_status == "pinned 1.0.0"
    assert [
        provider.plugin_version
        for provider in snapshot.workflow_provider_catalog.providers
        if provider.plugin_id == "acme.formatter"
    ] == ["1.0.0"]
