from __future__ import annotations

import shutil
from pathlib import Path
import tempfile
import uuid
import zipfile

from app.core import constants
from app.core.errors import AppValidationError
from app.packaging.zip_safety import UnsafeArchiveError, safe_extract_zip


def stage_plugin_source(source_path: str | Path) -> Path:
    resolved_source = Path(source_path).expanduser().resolve()
    if not resolved_source.exists():
        raise AppValidationError(f"Plugin source not found: {resolved_source}")

    staging_dir = Path(tempfile.gettempdir()).resolve() / constants.TEMP_NAMESPACE_DIRNAME / "plugins_stage"
    staging_dir.mkdir(parents=True, exist_ok=True)
    target_root = staging_dir / uuid.uuid4().hex
    target_root.mkdir(parents=True, exist_ok=True)

    if resolved_source.is_dir():
        target_dir = target_root / resolved_source.name
        shutil.copytree(resolved_source, target_dir, dirs_exist_ok=True)
        return target_dir

    if resolved_source.suffix.lower() != ".zip":
        raise AppValidationError("Plugin source must be a directory or .zip archive.")

    try:
        with zipfile.ZipFile(resolved_source, "r") as archive:
            safe_extract_zip(archive, target_root)
    except UnsafeArchiveError as exc:
        raise AppValidationError(str(exc)) from exc
    return target_root


def locate_manifest_root(staged_root: str | Path) -> Path:
    root = Path(staged_root).expanduser().resolve()
    if root.is_file():
        raise AppValidationError(f"Plugin staging root must be a directory: {root}")

    candidate_paths: list[Path] = []
    direct_manifest = root / constants.PLUGIN_MANIFEST_FILENAME
    if direct_manifest.exists() and direct_manifest.is_file():
        candidate_paths.append(root)

    for manifest_path in sorted(root.rglob(constants.PLUGIN_MANIFEST_FILENAME)):
        if manifest_path.is_file():
            candidate_paths.append(manifest_path.parent)

    unique_roots: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidate_paths:
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_roots.append(resolved)

    if not unique_roots:
        raise AppValidationError(
            f"Plugin source does not contain {constants.PLUGIN_MANIFEST_FILENAME}."
        )
    if len(unique_roots) > 1:
        raise AppValidationError("Plugin source contains multiple plugin manifests.")
    return unique_roots[0]
