"""Unit tests for plugin host runtime module loading guards."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core import constants
from app.plugins.host_runtime import _load_runtime_module
from app.plugins.host_runtime import load_runtime_command_handlers
from app.plugins.models import PluginRegistryEntry
from app.plugins.registry_store import upsert_registry_entry
from app.plugins.trust_store import set_runtime_plugin_trust

pytestmark = pytest.mark.unit


def test_load_runtime_module_requires_entrypoint_inside_plugin_root(tmp_path: Path) -> None:
    install_path = tmp_path / "plugin"
    install_path.mkdir()
    outside_path = tmp_path / "outside.py"
    outside_path.write_text("def handle_command(*_args, **_kwargs):\n    return {'outside': True}\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="escapes plugin install path"):
        _load_runtime_module(
            plugin_id="acme.demo",
            install_path=install_path,
            runtime_entrypoint="../outside.py",
        )


def test_load_runtime_module_requires_existing_entrypoint_file(tmp_path: Path) -> None:
    install_path = tmp_path / "plugin"
    install_path.mkdir()

    with pytest.raises(RuntimeError, match="Runtime entrypoint not found"):
        _load_runtime_module(
            plugin_id="acme.demo",
            install_path=install_path,
            runtime_entrypoint="runtime.py",
        )


def test_load_runtime_handlers_skips_untrusted_runtime_plugins(tmp_path: Path) -> None:
    state_root = str((tmp_path / "state").resolve())
    install_path = tmp_path / "plugins" / "acme.demo" / "1.0.0"
    install_path.mkdir(parents=True, exist_ok=True)
    (install_path / constants.PLUGIN_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "id": "acme.demo",
                "name": "Demo",
                "version": "1.0.0",
                "api_version": constants.PLUGIN_API_VERSION,
                "runtime": {"entrypoint": "runtime.py"},
                "contributes": {
                    "commands": [
                        {
                            "id": "acme.demo.echo",
                            "title": "Echo",
                            "runtime": True,
                            "runtime_handler": "handle_command",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    (install_path / "runtime.py").write_text(
        "def handle_command(command_id, payload):\n    return {'ok': True, 'command_id': command_id, 'payload': payload}\n",
        encoding="utf-8",
    )
    upsert_registry_entry(
        PluginRegistryEntry(
            plugin_id="acme.demo",
            version="1.0.0",
            install_path=str(install_path.resolve()),
            enabled=True,
            installed_at="2026-03-08T00:00:00",
        ),
        state_root=state_root,
    )

    handlers = load_runtime_command_handlers(state_root=state_root)

    assert handlers == {}


def test_load_runtime_handlers_allows_trusted_runtime_plugins(tmp_path: Path) -> None:
    state_root = str((tmp_path / "state").resolve())
    install_path = tmp_path / "plugins" / "acme.demo" / "1.0.0"
    install_path.mkdir(parents=True, exist_ok=True)
    (install_path / constants.PLUGIN_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "id": "acme.demo",
                "name": "Demo",
                "version": "1.0.0",
                "api_version": constants.PLUGIN_API_VERSION,
                "runtime": {"entrypoint": "runtime.py"},
                "contributes": {
                    "commands": [
                        {
                            "id": "acme.demo.echo",
                            "title": "Echo",
                            "runtime": True,
                            "runtime_handler": "handle_command",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    (install_path / "runtime.py").write_text(
        "def handle_command(command_id, payload):\n    return {'ok': True, 'command_id': command_id, 'payload': payload}\n",
        encoding="utf-8",
    )
    upsert_registry_entry(
        PluginRegistryEntry(
            plugin_id="acme.demo",
            version="1.0.0",
            install_path=str(install_path.resolve()),
            enabled=True,
            installed_at="2026-03-08T00:00:00",
        ),
        state_root=state_root,
    )
    set_runtime_plugin_trust("acme.demo", "1.0.0", trusted=True, state_root=state_root)

    handlers = load_runtime_command_handlers(state_root=state_root)

    assert "acme.demo.echo" in handlers
    assert handlers["acme.demo.echo"]({"value": 7}) == {
        "ok": True,
        "command_id": "acme.demo.echo",
        "payload": {"value": 7},
    }

