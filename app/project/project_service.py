"""Project open/load orchestration for filesystem-first project workflows."""

from __future__ import annotations

import os
from pathlib import Path

from app.bootstrap.paths import PathInput, project_cbcs_dir, project_manifest_path
from app.core.errors import ProjectEnumerationError, ProjectStructureValidationError
from app.core.models import LoadedProject, ProjectFileEntry
from app.project.project_manifest import load_project_manifest


def open_project(project_root: PathInput) -> LoadedProject:
    """Load a project root into a structured object for shell consumers."""
    resolved_root = validate_project_structure(project_root)
    manifest_path = project_manifest_path(resolved_root)

    metadata = load_project_manifest(manifest_path)
    entries = enumerate_project_entries(resolved_root)

    return LoadedProject(
        project_root=str(resolved_root),
        manifest_path=str(manifest_path),
        metadata=metadata,
        entries=entries,
    )


def validate_project_structure(project_root: PathInput) -> Path:
    """Validate required on-disk project shape and return resolved root path."""
    try:
        resolved_root = _resolve_project_root(project_root)
    except ValueError as exc:
        raise ProjectStructureValidationError(str(exc), project_root=Path(project_root)) from exc

    if not resolved_root.exists():
        raise ProjectStructureValidationError(
            "Project folder not found.",
            project_root=resolved_root,
        )
    if not resolved_root.is_dir():
        raise ProjectStructureValidationError(
            "Project root must be a directory.",
            project_root=resolved_root,
        )

    cbcs_dir = project_cbcs_dir(resolved_root)
    if not cbcs_dir.exists() or not cbcs_dir.is_dir():
        raise ProjectStructureValidationError(
            "Missing required metadata directory: .cbcs.",
            project_root=resolved_root,
        )

    manifest_path = project_manifest_path(resolved_root)
    if not manifest_path.exists() or not manifest_path.is_file():
        raise ProjectStructureValidationError(
            "Missing required project manifest file: .cbcs/project.json.",
            project_root=resolved_root,
            manifest_path=manifest_path,
        )

    return resolved_root


def enumerate_project_entries(project_root: PathInput) -> list[ProjectFileEntry]:
    """Recursively enumerate project entries in deterministic sorted order.

    Policy for T07:
    - include both files and directories
    - exclude `.cbcs` metadata subtree from UI-facing project entries
    - keep stable lexical ordering by relative path
    """
    try:
        resolved_root = _resolve_project_root(project_root)
    except ValueError as exc:
        raise ProjectEnumerationError(str(exc), project_root=Path(project_root)) from exc

    if not resolved_root.exists():
        raise ProjectEnumerationError(
            "Project folder not found.",
            project_root=resolved_root,
        )
    if not resolved_root.is_dir():
        raise ProjectEnumerationError(
            "Project root must be a directory.",
            project_root=resolved_root,
        )

    entries: list[ProjectFileEntry] = []

    def _on_walk_error(error: OSError) -> None:
        raise ProjectEnumerationError(
            f"Failed to enumerate project files: {error}",
            project_root=resolved_root,
        ) from error

    try:
        for current_dir, dir_names, file_names in os.walk(
            resolved_root,
            topdown=True,
            onerror=_on_walk_error,
            followlinks=False,
        ):
            current_path = Path(current_dir)
            dir_names[:] = sorted(name for name in dir_names if name != ".cbcs")
            file_names.sort()

            for directory_name in dir_names:
                directory_path = current_path / directory_name
                entries.append(
                    _build_project_entry(
                        path=directory_path,
                        project_root=resolved_root,
                        is_directory=True,
                    )
                )

            for file_name in file_names:
                file_path = current_path / file_name
                entries.append(
                    _build_project_entry(
                        path=file_path,
                        project_root=resolved_root,
                        is_directory=False,
                    )
                )
    except ProjectEnumerationError:
        raise
    except OSError as exc:
        raise ProjectEnumerationError(
            f"Failed to enumerate project files: {exc}",
            project_root=resolved_root,
        ) from exc

    return sorted(entries, key=lambda entry: entry.relative_path)


def _build_project_entry(path: Path, project_root: Path, *, is_directory: bool) -> ProjectFileEntry:
    relative_path = path.relative_to(project_root).as_posix()
    return ProjectFileEntry(
        relative_path=relative_path,
        absolute_path=str(path.resolve()),
        is_directory=is_directory,
    )


def _resolve_project_root(project_root: PathInput) -> Path:
    candidate = Path(project_root).expanduser()
    if not candidate.is_absolute():
        raise ValueError("project_root must be an absolute path.")
    return candidate.resolve()
