"""Unit tests for plugin install-time workflow audits."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import constants
from app.plugins.auditor import audit_plugin_package_messages
from app.plugins.models import PluginManifest

pytestmark = pytest.mark.unit


def _manifest(*, runtime_entrypoint: str = "runtime.py") -> PluginManifest:
    return PluginManifest(
        plugin_id="acme.demo",
        name="Demo",
        version="1.0.0",
        api_version=constants.PLUGIN_API_VERSION,
        runtime_entrypoint=runtime_entrypoint,
    )


def test_audit_plugin_package_rejects_native_extensions_and_hidden_paths(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    (plugin_root / "runtime.py").write_text(
        "def handle_command(command_id, payload):\n    return {'command_id': command_id, 'payload': payload}\n",
        encoding="utf-8",
    )
    (plugin_root / ".hidden").mkdir()
    (plugin_root / ".hidden" / "secret.txt").write_text("x\n", encoding="utf-8")
    (plugin_root / "native.so").write_text("", encoding="utf-8")

    messages = audit_plugin_package_messages(plugin_root, _manifest())

    assert any("hidden files or directories" in message for message in messages)
    assert any("pure Python" in message for message in messages)


def test_audit_plugin_package_rejects_python310_syntax_and_subprocess_usage(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    (plugin_root / "runtime.py").write_text(
        "import subprocess\n\n"
        "def handle_command(command_id, payload):\n"
        "    match payload:\n"
        "        case _:\n"
        "            subprocess.run(['echo', 'nope'])\n"
        "    return {'command_id': command_id, 'payload': payload}\n",
        encoding="utf-8",
    )

    messages = audit_plugin_package_messages(plugin_root, _manifest())

    assert any("Python 3.9" in message for message in messages)
    assert any("subprocess execution" in message for message in messages)


def test_audit_plugin_package_rejects_non_python_runtime_entrypoint(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    (plugin_root / "runtime.sh").write_text("#!/bin/sh\n", encoding="utf-8")

    messages = audit_plugin_package_messages(plugin_root, _manifest(runtime_entrypoint="runtime.sh"))

    assert any("runtime.entrypoint" in message for message in messages)
