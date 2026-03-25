"""Unit tests for workflow provider catalog selection."""

from __future__ import annotations

import pytest

from app.core import constants
from app.plugins.models import DiscoveredPlugin, PluginManifest, PluginWorkflowProvider
from app.plugins.project_config import ProjectPluginConfig
from app.plugins.workflow_catalog import WorkflowProviderCatalog, provider_key

pytestmark = pytest.mark.unit


def _plugin(
    *,
    plugin_id: str,
    version: str,
    provider_id: str,
    title: str,
    priority: int,
) -> DiscoveredPlugin:
    provider = PluginWorkflowProvider(
        provider_id=provider_id,
        kind=constants.WORKFLOW_PROVIDER_KIND_FORMATTER,
        lane=constants.WORKFLOW_PROVIDER_LANE_QUERY,
        title=title,
        priority=priority,
        languages=("python",),
        file_extensions=(".py",),
        query_handler="handle_formatter_query",
    )
    manifest = PluginManifest(
        plugin_id=plugin_id,
        name=plugin_id,
        version=version,
        api_version=constants.PLUGIN_API_VERSION,
        runtime_entrypoint="runtime.py",
        capabilities=[constants.PLUGIN_CAPABILITY_WORKFLOW_FORMATTER],
        permissions=[constants.PLUGIN_PERMISSION_PROJECT_READ],
        workflow_providers=[provider],
        contributes={"workflow_providers": [provider.to_dict()]},
    )
    return DiscoveredPlugin(
        plugin_id=plugin_id,
        version=version,
        install_path=f"/tmp/{plugin_id}/{version}",
        manifest_path=f"/tmp/{plugin_id}/{version}/plugin.json",
        manifest=manifest,
    )


def test_workflow_provider_catalog_prefers_higher_priority_by_default() -> None:
    primary = _plugin(
        plugin_id="cbcs.primary",
        version="1.0.0",
        provider_id="formatter",
        title="Primary Formatter",
        priority=200,
    )
    secondary = _plugin(
        plugin_id="cbcs.secondary",
        version="1.0.0",
        provider_id="formatter",
        title="Secondary Formatter",
        priority=100,
    )

    catalog = WorkflowProviderCatalog.from_plugins(
        [secondary, primary],
        enabled_map={
            ("cbcs.primary", "1.0.0"): True,
            ("cbcs.secondary", "1.0.0"): True,
        },
    )

    selected = catalog.select(
        kind=constants.WORKFLOW_PROVIDER_KIND_FORMATTER,
        lane=constants.WORKFLOW_PROVIDER_LANE_QUERY,
        language="python",
        file_path="demo.py",
    )

    assert selected is not None
    assert selected.plugin_id == "cbcs.primary"
    assert selected.provider_key == provider_key("cbcs.primary", "formatter")


def test_workflow_provider_catalog_respects_project_pins_and_preferred_provider() -> None:
    older = _plugin(
        plugin_id="cbcs.python_tools",
        version="1.0.0",
        provider_id="formatter",
        title="Formatter v1",
        priority=200,
    )
    newer = _plugin(
        plugin_id="cbcs.python_tools",
        version="2.0.0",
        provider_id="formatter",
        title="Formatter v2",
        priority=250,
    )
    alternative = _plugin(
        plugin_id="cbcs.alt_formatter",
        version="1.0.0",
        provider_id="formatter",
        title="Alternative Formatter",
        priority=100,
    )
    config = ProjectPluginConfig(
        pinned_versions={"cbcs.python_tools": "1.0.0"},
        preferred_providers={"formatter:python": provider_key("cbcs.alt_formatter", "formatter")},
    )

    catalog = WorkflowProviderCatalog.from_plugins(
        [older, newer, alternative],
        enabled_map={
            ("cbcs.python_tools", "1.0.0"): True,
            ("cbcs.python_tools", "2.0.0"): True,
            ("cbcs.alt_formatter", "1.0.0"): True,
        },
        project_config=config,
    )

    matching = catalog.list_matching(
        kind=constants.WORKFLOW_PROVIDER_KIND_FORMATTER,
        lane=constants.WORKFLOW_PROVIDER_LANE_QUERY,
        language="python",
        file_path="demo.py",
    )
    assert [item.plugin_version for item in matching if item.plugin_id == "cbcs.python_tools"] == ["1.0.0"]

    selected = catalog.select(
        kind=constants.WORKFLOW_PROVIDER_KIND_FORMATTER,
        lane=constants.WORKFLOW_PROVIDER_LANE_QUERY,
        preferred_provider_key=provider_key("cbcs.alt_formatter", "formatter"),
        language="python",
        file_path="demo.py",
    )

    assert selected is not None
    assert selected.plugin_id == "cbcs.alt_formatter"
