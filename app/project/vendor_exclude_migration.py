"""One-time migration to persist vendor/ exclusion for large existing projects."""

from __future__ import annotations

from dataclasses import replace
import logging
import os
from pathlib import Path

from app.bootstrap.paths import project_manifest_path
from app.core.models import LoadedProject
from app.project.project_manifest import save_project_manifest

VENDOR_DIRNAME = "vendor"
LARGE_VENDOR_FILE_THRESHOLD = 100


def maybe_persist_vendor_exclude(
    loaded_project: LoadedProject,
    *,
    logger: logging.Logger | None = None,
) -> LoadedProject:
    """Persist ``vendor`` in manifest excludes when a large vendor tree is present.

    Idempotent: no-op when the manifest already lists exclude patterns or vendor
    is absent/small.
    """
    if "vendor" in loaded_project.metadata.exclude_patterns:
        return loaded_project

    project_root = Path(loaded_project.project_root).expanduser().resolve()
    vendor_dir = project_root / VENDOR_DIRNAME
    if not vendor_dir.is_dir():
        return loaded_project

    file_count = _count_files_under(vendor_dir)
    if file_count <= LARGE_VENDOR_FILE_THRESHOLD:
        return loaded_project

    patterns = list(loaded_project.metadata.exclude_patterns)
    if VENDOR_DIRNAME not in patterns:
        patterns.append(VENDOR_DIRNAME)
    updated_metadata = replace(loaded_project.metadata, exclude_patterns=patterns)
    manifest_path = project_manifest_path(project_root)
    save_project_manifest(manifest_path, updated_metadata)
    if logger is not None:
        logger.info(
            "Excluded vendor/ from project tree for performance (%s files under vendor/).",
            file_count,
        )
    return LoadedProject(
        project_root=loaded_project.project_root,
        manifest_path=loaded_project.manifest_path,
        metadata=updated_metadata,
        entries=loaded_project.entries,
        manifest_materialized=True,
    )


def _count_files_under(root: Path) -> int:
    count = 0
    for _current_dir, _dir_names, file_names in os.walk(root):
        count += len(file_names)
        if count > LARGE_VENDOR_FILE_THRESHOLD:
            return count
    return count
