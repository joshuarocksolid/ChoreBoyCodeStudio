"""Unit tests for plugin manifest parsing and loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.errors import PluginManifestValidationError
from app.plugins.manifest import load_plugin_manifest, parse_plugin_manifest

pytestmark = pytest.mark.unit


def test_parse_plugin_manifest_accepts_runtime_and_engine_constraints() -> None:
    manifest = parse_plugin_manifest(
        {
            "id": "acme.demo",
            "name": "Demo Plugin",
            "version": "1.2.3",
            "api_version": 1,
            "runtime": {"entrypoint": "runtime.py"},
            "activation_events": ["run_start"],
            "capabilities": ["command"],
            "contributes": {"commands": [{"id": "acme.demo.hello", "title": "Hello"}]},
            "engine_constraints": {
                "min_app_version": "0.1.0",
                "max_app_version": "0.9.9",
                "min_api_version": 1,
                "max_api_version": 2,
            },
        }
    )

    assert manifest.plugin_id == "acme.demo"
    assert manifest.runtime_entrypoint == "runtime.py"
    assert manifest.engine.min_app_version == "0.1.0"
    assert manifest.engine.max_api_version == 2


def test_parse_plugin_manifest_rejects_missing_required_id() -> None:
    with pytest.raises(PluginManifestValidationError, match="Missing required field: id"):
        parse_plugin_manifest(
            {
                "name": "Demo Plugin",
                "version": "1.0.0",
                "api_version": 1,
            }
        )


def test_parse_plugin_manifest_rejects_invalid_runtime_entrypoint() -> None:
    with pytest.raises(PluginManifestValidationError, match="runtime.entrypoint must be a non-empty string"):
        parse_plugin_manifest(
            {
                "id": "acme.demo",
                "name": "Demo Plugin",
                "version": "1.0.0",
                "api_version": 1,
                "runtime": {"entrypoint": ""},
            }
        )


def test_parse_plugin_manifest_rejects_runtime_entrypoint_traversal() -> None:
    with pytest.raises(PluginManifestValidationError, match="cannot contain"):
        parse_plugin_manifest(
            {
                "id": "acme.demo",
                "name": "Demo Plugin",
                "version": "1.0.0",
                "api_version": 1,
                "runtime": {"entrypoint": "../../outside.py"},
            }
        )


def test_parse_plugin_manifest_rejects_absolute_runtime_entrypoint() -> None:
    with pytest.raises(PluginManifestValidationError, match="must be a relative path"):
        parse_plugin_manifest(
            {
                "id": "acme.demo",
                "name": "Demo Plugin",
                "version": "1.0.0",
                "api_version": 1,
                "runtime": {"entrypoint": "/tmp/outside.py"},
            }
        )


def test_parse_plugin_manifest_rejects_path_traversal_plugin_id() -> None:
    with pytest.raises(PluginManifestValidationError, match="id must use only"):
        parse_plugin_manifest(
            {
                "id": "../../escape",
                "name": "Demo Plugin",
                "version": "1.0.0",
                "api_version": 1,
            }
        )


def test_parse_plugin_manifest_rejects_path_traversal_version() -> None:
    with pytest.raises(PluginManifestValidationError, match="version must use only"):
        parse_plugin_manifest(
            {
                "id": "acme.demo",
                "name": "Demo Plugin",
                "version": "../1.0.0",
                "api_version": 1,
            }
        )


def test_load_plugin_manifest_reads_manifest_from_disk(tmp_path: Path) -> None:
    manifest_path = tmp_path / "plugin.json"
    manifest_path.write_text(
        json.dumps(
            {
                "id": "acme.demo",
                "name": "Demo Plugin",
                "version": "1.0.0",
                "api_version": 1,
            }
        ),
        encoding="utf-8",
    )

    manifest = load_plugin_manifest(manifest_path)

    assert manifest.plugin_id == "acme.demo"
    assert manifest.version == "1.0.0"


def test_load_plugin_manifest_rejects_invalid_json(tmp_path: Path) -> None:
    manifest_path = tmp_path / "plugin.json"
    manifest_path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(PluginManifestValidationError, match="Invalid JSON in plugin manifest"):
        load_plugin_manifest(manifest_path)


def test_parse_plugin_manifest_accepts_workflow_provider_contributions() -> None:
    manifest = parse_plugin_manifest(
        {
            "id": "acme.workflow",
            "name": "Workflow Plugin",
            "version": "1.0.0",
            "api_version": 1,
            "runtime": {"entrypoint": "runtime.py"},
            "capabilities": ["workflow.formatter"],
            "permissions": ["project.read"],
            "contributes": {
                "workflow_providers": [
                    {
                        "id": "formatter",
                        "kind": "formatter",
                        "lane": "query",
                        "title": "Formatter",
                        "languages": ["python"],
                        "file_extensions": [".py"],
                        "query_handler": "handle_formatter_query",
                    }
                ]
            },
        }
    )

    assert manifest.permissions == ["project.read"]
    assert len(manifest.workflow_providers) == 1
    assert manifest.workflow_providers[0].provider_id == "formatter"
    assert manifest.workflow_providers[0].query_handler == "handle_formatter_query"


def test_parse_plugin_manifest_rejects_workflow_provider_without_runtime_entrypoint() -> None:
    with pytest.raises(PluginManifestValidationError, match="runtime.entrypoint is required"):
        parse_plugin_manifest(
            {
                "id": "acme.workflow",
                "name": "Workflow Plugin",
                "version": "1.0.0",
                "api_version": 1,
                "contributes": {
                    "workflow_providers": [
                        {
                            "id": "formatter",
                            "kind": "formatter",
                            "lane": "query",
                            "title": "Formatter",
                            "query_handler": "handle_formatter_query",
                        }
                    ]
                },
            }
        )
