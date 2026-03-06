"""Unit tests for plugin install/uninstall lifecycle helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core import constants
from app.plugins.installer import install_plugin, set_plugin_enabled, uninstall_plugin
from app.plugins.registry_store import load_plugin_registry

pytestmark = pytest.mark.unit


def _write_plugin_source(source_root: Path, *, plugin_id: str, version: str) -> None:
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / constants.PLUGIN_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "id": plugin_id,
                "name": "Demo Plugin",
                "version": version,
                "api_version": constants.PLUGIN_API_VERSION,
                "contributes": {"commands": [{"id": "demo.hello", "title": "Hello"}]},
            }
        ),
        encoding="utf-8",
    )
    (source_root / "runtime.py").write_text("def handle_command(command_id, payload):\n    return payload\n", encoding="utf-8")


def test_install_plugin_persists_registry_entry_and_files(tmp_path: Path) -> None:
    source_root = tmp_path / "plugin_source"
    _write_plugin_source(source_root, plugin_id="acme.demo", version="1.0.0")
    state_root = str((tmp_path / "state").resolve())

    result = install_plugin(source_root, state_root=state_root)
    registry = load_plugin_registry(state_root)

    assert result.plugin_id == "acme.demo"
    assert Path(result.install_path).is_dir()
    assert Path(result.manifest_path).is_file()
    assert len(registry.entries) == 1
    assert registry.entries[0].plugin_id == "acme.demo"
    assert registry.entries[0].enabled is True


def test_set_plugin_enabled_updates_registry_state(tmp_path: Path) -> None:
    source_root = tmp_path / "plugin_source"
    _write_plugin_source(source_root, plugin_id="acme.demo", version="1.0.0")
    state_root = str((tmp_path / "state").resolve())
    install_plugin(source_root, state_root=state_root)

    set_plugin_enabled("acme.demo", "1.0.0", enabled=False, state_root=state_root)
    registry = load_plugin_registry(state_root)

    assert registry.entries[0].enabled is False


def test_uninstall_plugin_removes_installation_and_registry_entry(tmp_path: Path) -> None:
    source_root = tmp_path / "plugin_source"
    _write_plugin_source(source_root, plugin_id="acme.demo", version="1.0.0")
    state_root = str((tmp_path / "state").resolve())
    result = install_plugin(source_root, state_root=state_root)
    assert Path(result.install_path).exists()

    uninstall_plugin("acme.demo", state_root=state_root)

    assert Path(result.install_path).exists() is False
    assert load_plugin_registry(state_root).entries == []
