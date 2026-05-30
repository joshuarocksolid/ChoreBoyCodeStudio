"""One-time migration to persist vendor/ exclusion for large existing projects."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from app.bootstrap.paths import project_manifest_path
from app.core.models import LoadedProject, ProjectMetadata
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
    if loaded_project.metadata.exclude_patterns:
        return loaded_project

    project_root = Path(loaded_project.project_root).expanduser().resolve()
    vendor_dir = project_root / VENDOR_DIRNAME
    if not vendor_dir.is_dir():
        return loaded_project

    file_count = _count_files_under(vendor_dir)
    if file_count <= LARGE_VENDOR_FILE_THRESHOLD:
        return loaded_project

    updated_metadata = ProjectMetadata(
        schema_version=loaded_project.metadata.schema_version,
        project_id=loaded_project.metadata.project_id,
        name=loaded_project.metadata.name,
        default_entry=loaded_project.metadata.default_entry,
        default_argv=list(loaded_project.metadata.default_argv),
        working_directory=loaded_project.metadata.working_directory,
        template=loaded_project.metadata.template,
        run_configs=list(loaded_project.metadata.run_configs),
        env_overrides=dict(loaded_project.metadata.env_overrides),
        project_notes=loaded_project.metadata.project_notes,
        exclude_patterns=[VENDOR_DIRNAME],
    )
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
