from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import shutil

from app.bootstrap.paths import PathInput, ensure_directory, plugin_install_dir
from app.core import constants
from app.plugins.manifest import load_plugin_manifest
from app.plugins.models import PluginRegistryEntry
from app.plugins.package_format import locate_manifest_root, stage_plugin_source
from app.plugins.registry_store import (
    load_plugin_registry,
    remove_registry_entry,
    set_registry_entry_enabled,
    upsert_registry_entry,
)


@dataclass(frozen=True)
class PluginInstallResult:
    plugin_id: str
    version: str
    install_path: str
    manifest_path: str


def install_plugin(
    source_path: str | Path,
    *,
    state_root: PathInput | None = None,
) -> PluginInstallResult:
    staged_root = stage_plugin_source(source_path)
    try:
        manifest_root = locate_manifest_root(staged_root)
        manifest_path = manifest_root / constants.PLUGIN_MANIFEST_FILENAME
        manifest = load_plugin_manifest(manifest_path)
        install_path = plugin_install_dir(manifest.plugin_id, manifest.version, state_root)
        ensure_directory(install_path.parent)
        if install_path.exists():
            shutil.rmtree(install_path)
        shutil.copytree(manifest_root, install_path)

        registry_entry = PluginRegistryEntry(
            plugin_id=manifest.plugin_id,
            version=manifest.version,
            install_path=str(install_path.resolve()),
            enabled=True,
            installed_at=datetime.now().isoformat(timespec="seconds"),
            last_error=None,
        )
        upsert_registry_entry(registry_entry, state_root=state_root)
        return PluginInstallResult(
            plugin_id=manifest.plugin_id,
            version=manifest.version,
            install_path=str(install_path.resolve()),
            manifest_path=str((install_path / constants.PLUGIN_MANIFEST_FILENAME).resolve()),
        )
    finally:
        shutil.rmtree(staged_root, ignore_errors=True)


def uninstall_plugin(
    plugin_id: str,
    *,
    version: str | None = None,
    state_root: PathInput | None = None,
) -> None:
    registry = load_plugin_registry(state_root)
    entries = [
        entry
        for entry in registry.entries
        if entry.plugin_id == plugin_id and (version is None or entry.version == version)
    ]
    for entry in entries:
        install_path = Path(entry.install_path).expanduser().resolve()
        if install_path.exists():
            shutil.rmtree(install_path, ignore_errors=True)
    remove_registry_entry(plugin_id, version=version, state_root=state_root)


def set_plugin_enabled(
    plugin_id: str,
    version: str,
    *,
    enabled: bool,
    state_root: PathInput | None = None,
) -> None:
    set_registry_entry_enabled(
        plugin_id,
        version,
        enabled=enabled,
        state_root=state_root,
    )
