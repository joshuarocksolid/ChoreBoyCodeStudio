"""Unit tests for plugin discovery and compatibility evaluation."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.bootstrap.paths import ensure_directory, plugin_install_dir
from app.core import constants
from app.plugins.discovery import discover_installed_plugins, evaluate_manifest_compatibility
from app.plugins.models import PluginEngineConstraints, PluginManifest

pytestmark = pytest.mark.unit


def _write_manifest(path: Path, *, plugin_id: str, version: str, api_version: int) -> None:
    path.write_text(
        (
            "{\n"
            f'  "id": "{plugin_id}",\n'
            f'  "name": "{plugin_id}",\n'
            f'  "version": "{version}",\n'
            f'  "api_version": {api_version}\n'
            "}\n"
        ),
        encoding="utf-8",
    )


def test_evaluate_manifest_compatibility_reports_api_and_version_bounds() -> None:
    manifest = PluginManifest(
        plugin_id="acme.demo",
        name="Demo",
        version="1.0.0",
        api_version=2,
        engine=PluginEngineConstraints(
            min_app_version="0.2.0",
            max_app_version="0.3.0",
            min_api_version=2,
            max_api_version=2,
        ),
    )

    compatibility = evaluate_manifest_compatibility(
        manifest,
        current_app_version="0.1.0",
        current_api_version=1,
    )

    assert compatibility.is_compatible is False
    assert any("api_version" in reason for reason in compatibility.reasons)
    assert any("below plugin minimum" in reason for reason in compatibility.reasons)


def test_discover_installed_plugins_returns_valid_manifest_entries(tmp_path: Path) -> None:
    state_root = str(tmp_path.resolve())
    install_path = plugin_install_dir("acme.demo", "1.0.0", state_root)
    ensure_directory(install_path)
    _write_manifest(
        install_path / constants.PLUGIN_MANIFEST_FILENAME,
        plugin_id="acme.demo",
        version="1.0.0",
        api_version=constants.PLUGIN_API_VERSION,
    )

    discovered = discover_installed_plugins(state_root=state_root)

    assert len(discovered) == 1
    assert discovered[0].plugin_id == "acme.demo"
    assert discovered[0].errors == []
    assert discovered[0].compatibility is not None
    assert discovered[0].compatibility.is_compatible is True


def test_discover_installed_plugins_reports_missing_manifest(tmp_path: Path) -> None:
    state_root = str(tmp_path.resolve())
    install_path = plugin_install_dir("acme.demo", "1.0.0", state_root)
    ensure_directory(install_path)

    discovered = discover_installed_plugins(state_root=state_root)

    assert len(discovered) == 1
    assert discovered[0].errors
    assert "Missing plugin.json." in discovered[0].errors[0]


def test_discover_installed_plugins_reports_phase1_audit_findings(tmp_path: Path) -> None:
    state_root = str(tmp_path.resolve())
    install_path = plugin_install_dir("acme.demo", "1.0.0", state_root)
    ensure_directory(install_path)
    _write_manifest(
        install_path / constants.PLUGIN_MANIFEST_FILENAME,
        plugin_id="acme.demo",
        version="1.0.0",
        api_version=constants.PLUGIN_API_VERSION,
    )
    (install_path / "runtime.py").write_text(
        "import subprocess\n\n"
        "def handle_command(command_id, payload):\n"
        "    subprocess.run(['echo', 'boom'])\n"
        "    return payload\n",
        encoding="utf-8",
    )

    discovered = discover_installed_plugins(state_root=state_root)

    assert len(discovered) == 1
    assert discovered[0].compatibility is not None
    assert discovered[0].compatibility.is_compatible is False
    assert any("subprocess execution" in reason for reason in discovered[0].errors)
