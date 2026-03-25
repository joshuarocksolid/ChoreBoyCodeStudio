"""Integration tests for plugin/provider diagnostics in support bundles."""

from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest

from app.plugins.project_config import set_project_plugin_version_pin, set_project_preferred_provider
from app.support.support_bundle import build_support_bundle

pytestmark = pytest.mark.integration


def _write_valid_project(project_root: Path) -> None:
    (project_root / "cbcs").mkdir(parents=True, exist_ok=True)
    (project_root / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (project_root / "cbcs" / "project.json").write_text(
        json.dumps({"schema_version": 1, "name": "plugin_bundle_project"}, indent=2),
        encoding="utf-8",
    )


def test_support_bundle_includes_plugin_project_config_and_provider_inventory(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    state_root = tmp_path / "state"
    _write_valid_project(project_root)
    set_project_plugin_version_pin(str(project_root), "cbcs.python_tools", "1.0.0")
    set_project_preferred_provider(
        str(project_root),
        "formatter:python",
        "cbcs.python_tools:formatter",
    )

    bundle_path = build_support_bundle(
        project_root,
        state_root=state_root,
        destination_dir=tmp_path / "bundles",
        workflow_provider_metrics=[
            {
                "provider_key": "cbcs.python_tools:formatter",
                "kind": "formatter",
                "lane": "query",
                "title": "CBCS Python Formatter",
                "source_kind": "bundled",
                "invocation_count": 2,
                "success_count": 2,
                "failure_count": 0,
                "timeout_count": 0,
                "last_elapsed_ms": 12.5,
                "max_elapsed_ms": 17.0,
                "last_error": None,
            }
        ],
    )

    with zipfile.ZipFile(bundle_path, "r") as archive:
        names = set(archive.namelist())
        assert "project/cbcs/plugins.json" in names
        assert "diagnostics/plugins.json" in names
        plugins_payload = json.loads(archive.read("diagnostics/plugins.json").decode("utf-8"))
        assert plugins_payload["project_plugin_config"]["pinned_versions"]["cbcs.python_tools"] == "1.0.0"
        provider_keys = {item["provider_key"] for item in plugins_payload["active_workflow_providers"]}
        assert "cbcs.python_tools:formatter" in provider_keys
        assert plugins_payload["workflow_provider_metrics"][0]["provider_key"] == "cbcs.python_tools:formatter"
