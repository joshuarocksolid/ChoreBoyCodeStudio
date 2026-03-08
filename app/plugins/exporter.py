from __future__ import annotations

from pathlib import Path
import zipfile

from app.core import constants
from app.core.errors import AppValidationError
from app.plugins.registry_store import load_plugin_registry


def export_installed_plugin(
    plugin_id: str,
    version: str,
    *,
    output_directory: str | Path,
    state_root: str | None = None,
) -> Path:
    registry = load_plugin_registry(state_root)
    matching_entry = None
    for entry in registry.entries:
        if entry.plugin_id == plugin_id and entry.version == version:
            matching_entry = entry
            break
    if matching_entry is None:
        raise AppValidationError(f"Plugin not found in registry: {plugin_id}@{version}")

    install_path = Path(matching_entry.install_path).expanduser().resolve()
    if not install_path.exists() or not install_path.is_dir():
        raise AppValidationError(f"Plugin install path missing: {install_path}")

    destination_dir = Path(output_directory).expanduser().resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    safe_plugin_id = _safe_archive_component(plugin_id, field_name="plugin_id")
    safe_version = _safe_archive_component(version, field_name="version")
    archive_name = f"{safe_plugin_id}-{safe_version}{constants.PLUGIN_PACKAGE_EXTENSION}"
    archive_path = destination_dir / archive_name
    if archive_path.exists():
        archive_path.unlink()

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(install_path.rglob("*")):
            if file_path.is_dir():
                continue
            archive.write(file_path, file_path.relative_to(install_path))
    return archive_path


def _safe_archive_component(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise AppValidationError(f"{field_name} must be a non-empty string.")
    if normalized in {".", ".."}:
        raise AppValidationError(f"{field_name} cannot be '.' or '..'.")
    if "/" in normalized or "\\" in normalized:
        raise AppValidationError(f"{field_name} cannot contain path separators.")
    return normalized
