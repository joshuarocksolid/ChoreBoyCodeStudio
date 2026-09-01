from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from app.bootstrap.paths import plugin_install_dir
from app.core import constants
from app.plugins.api_broker import PluginApiBroker
from app.plugins.manifest import parse_plugin_manifest
from app.plugins.models import DiscoveredWorkflowProvider, PluginRegistryEntry
from app.plugins.registry_store import upsert_registry_entry
from app.plugins.rpc_protocol import PluginPermissionDeniedError
from app.plugins.runtime_manager import PluginRuntimeManager
from app.plugins.trust_store import set_runtime_plugin_trust
from app.plugins.workflow_broker import WorkflowBroker
from app.plugins.workflow_catalog import WorkflowProviderCatalog, provider_key

pytestmark = pytest.mark.unit


class _RuntimeManagerProbe:
    def __init__(self) -> None:
        self.command_invoked = False

    def invoke_command(self, _command_id: str, _payload: dict[str, object]) -> object:
        self.command_invoked = True
        return {}


def test_runtime_command_rejects_permission_missing_from_manifest() -> None:
    runtime_manager = _RuntimeManagerProbe()
    broker = PluginApiBroker(cast(PluginRuntimeManager, runtime_manager))

    with pytest.raises(PluginPermissionDeniedError) as caught:
        broker.invoke_runtime_command(
            "acme.permission_probe.write",
            {},
            required_permissions=(constants.PLUGIN_PERMISSION_PROJECT_WRITE,),
            manifest_permissions=(constants.PLUGIN_PERMISSION_PROJECT_READ,),
        )

    assert caught.value.permission == constants.PLUGIN_PERMISSION_PROJECT_WRITE
    assert runtime_manager.command_invoked is False


def test_undeclared_permission_is_denied_without_disrupting_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CBCS_DISABLE_BACKGROUND_RUNTIME", raising=False)
    state_root = str((tmp_path / "state").resolve())
    install_path = plugin_install_dir("acme.permission_probe", "1.0.0", state_root)
    install_path.mkdir(parents=True, exist_ok=True)
    handler_marker = tmp_path / "handler-invoked"
    manifest_payload = {
        "id": "acme.permission_probe",
        "name": "Permission Probe",
        "version": "1.0.0",
        "api_version": constants.PLUGIN_API_VERSION,
        "runtime": {"entrypoint": "runtime.py"},
        "activation_events": ["on_provider:formatter"],
        "capabilities": [constants.PLUGIN_CAPABILITY_WORKFLOW_FORMATTER],
        "permissions": [constants.PLUGIN_PERMISSION_PROJECT_READ],
        "contributes": {
            "workflow_providers": [
                {
                    "id": "formatter",
                    "kind": constants.WORKFLOW_PROVIDER_KIND_FORMATTER,
                    "lane": constants.WORKFLOW_PROVIDER_LANE_QUERY,
                    "title": "Permission Probe Formatter",
                    "query_handler": "handle_query",
                    "permissions": [constants.PLUGIN_PERMISSION_PROJECT_WRITE],
                }
            ]
        },
    }
    (install_path / constants.PLUGIN_MANIFEST_FILENAME).write_text(
        json.dumps(manifest_payload),
        encoding="utf-8",
    )
    (install_path / "runtime.py").write_text(
        "from pathlib import Path\n\n"
        "def handle_query(provider_key, request):\n"
        f"    Path({str(handler_marker)!r}).write_text('invoked', encoding='utf-8')\n"
        "    return {'status': 'invoked'}\n",
        encoding="utf-8",
    )
    upsert_registry_entry(
        PluginRegistryEntry(
            plugin_id="acme.permission_probe",
            version="1.0.0",
            install_path=str(install_path.resolve()),
            enabled=True,
            installed_at="2026-09-01T00:00:00",
        ),
        state_root=state_root,
    )
    set_runtime_plugin_trust(
        "acme.permission_probe",
        "1.0.0",
        trusted=True,
        state_root=state_root,
    )
    manifest = parse_plugin_manifest(manifest_payload)
    provider = manifest.workflow_providers[0]
    key = provider_key(manifest.plugin_id, provider.provider_id)
    catalog = WorkflowProviderCatalog(
        [
            DiscoveredWorkflowProvider(
                plugin_id=manifest.plugin_id,
                plugin_version=manifest.version,
                source_kind=constants.PLUGIN_SOURCE_INSTALLED,
                install_path=str(install_path),
                provider=provider,
                manifest=manifest,
                provider_key=key,
            )
        ]
    )
    runtime_manager = PluginRuntimeManager(state_root=state_root)
    broker = WorkflowBroker(PluginApiBroker(runtime_manager))
    broker.set_plugin_catalog(catalog)

    runtime_manager.start()
    try:
        with pytest.raises(PluginPermissionDeniedError) as caught:
            broker.invoke_query(
                kind=constants.WORKFLOW_PROVIDER_KIND_FORMATTER,
                request={"source_text": "value=1\n"},
                preferred_provider_key=key,
            )

        assert caught.value.error_type == "permission_denied"
        assert caught.value.permission == constants.PLUGIN_PERMISSION_PROJECT_WRITE
        assert runtime_manager.is_running()
        assert not handler_marker.exists()
    finally:
        runtime_manager.stop()
