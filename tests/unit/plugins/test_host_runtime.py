"""Unit tests for plugin host runtime module loading guards."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.plugins.host_runtime import _load_runtime_module

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

