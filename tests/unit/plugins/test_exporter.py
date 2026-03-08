"""Unit tests for plugin export helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import AppValidationError
from app.plugins.exporter import export_installed_plugin
from app.plugins.models import PluginRegistryEntry
from app.plugins.registry_store import upsert_registry_entry

pytestmark = pytest.mark.unit


def test_export_installed_plugin_creates_archive(tmp_path: Path) -> None:
    state_root = str((tmp_path / "state").resolve())
    install_path = tmp_path / "install" / "acme.demo" / "1.0.0"
    install_path.mkdir(parents=True, exist_ok=True)
    (install_path / "plugin.json").write_text("{}", encoding="utf-8")
    (install_path / "runtime.py").write_text("print('ok')\n", encoding="utf-8")
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
    output_dir = tmp_path / "exports"
    output_dir.mkdir(parents=True, exist_ok=True)

    archive_path = export_installed_plugin(
        "acme.demo",
        "1.0.0",
        output_directory=output_dir,
        state_root=state_root,
    )

    assert archive_path.exists() is True
    assert archive_path.name == "acme.demo-1.0.0.cbcs-plugin.zip"


def test_export_installed_plugin_rejects_path_like_registry_id(tmp_path: Path) -> None:
    state_root = str((tmp_path / "state").resolve())
    install_path = tmp_path / "install" / "evil"
    install_path.mkdir(parents=True, exist_ok=True)
    (install_path / "plugin.json").write_text("{}", encoding="utf-8")
    upsert_registry_entry(
        PluginRegistryEntry(
            plugin_id="../evil",
            version="1.0.0",
            install_path=str(install_path.resolve()),
            enabled=True,
            installed_at="2026-03-08T00:00:00",
        ),
        state_root=state_root,
    )

    with pytest.raises(AppValidationError, match="plugin_id cannot contain path separators"):
        export_installed_plugin(
            "../evil",
            "1.0.0",
            output_directory=tmp_path / "exports",
            state_root=state_root,
        )

