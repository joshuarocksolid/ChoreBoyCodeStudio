"""Project open/load orchestration for filesystem-first project workflows."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

try:  # Python 3.11+
    import tomllib as _toml_module
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.9 runtimes
    try:
        import tomli as _toml_module  # type: ignore[import-not-found]
    except ModuleNotFoundError:  # pragma: no cover - no TOML parser available
        _toml_module = None

from app.bootstrap.paths import PathInput, project_cbcs_dir, project_manifest_path
from app.core import constants
from app.core.errors import AppValidationError, ProjectEnumerationError, ProjectStructureValidationError
from app.core.models import LoadedProject, ProjectFileEntry
from app.project.file_excludes import should_exclude_name
from app.project.project_manifest import build_default_project_manifest_payload, load_project_manifest

_TOML_MODULE = _toml_module


class ProjectRootState(str, Enum):
    """Classification for project root metadata readiness."""

    CANONICAL = "canonical_project"
    IMPORTABLE = "importable_python_folder"
    INVALID = "invalid_folder"


@dataclass(frozen=True)
class ProjectRootAssessment:
    """Classification result for a candidate project root."""

    state: ProjectRootState
    project_root: Path
    message: str
    inferred_entry: str | None = None


def open_project(
    project_root: PathInput,
    exclude_patterns: list[str] | None = None,
) -> LoadedProject:
    """Load a project root into a structured object for shell consumers."""
    resolved_root = _require_existing_project_root(project_root)
    assessment = assess_project_root(resolved_root)
    if assessment.state == ProjectRootState.INVALID:
        raise ProjectStructureValidationError(
            assessment.message,
            project_root=resolved_root,
            manifest_path=project_manifest_path(resolved_root),
        )
    _initialize_missing_project_metadata(resolved_root)
    resolved_root = validate_project_structure(resolved_root)
    manifest_path = project_manifest_path(resolved_root)

    metadata = load_project_manifest(manifest_path)

    from app.project.file_excludes import compute_effective_excludes
    effective_excludes = compute_effective_excludes(
        exclude_patterns or [],
        metadata.exclude_patterns,
    )
    entries = enumerate_project_entries(resolved_root, exclude_patterns=effective_excludes)

    return LoadedProject(
        project_root=str(resolved_root),
        manifest_path=str(manifest_path),
        metadata=metadata,
        entries=entries,
    )


def assess_project_root(project_root: PathInput) -> ProjectRootAssessment:
    """Classify project root as canonical, importable, or invalid."""
    try:
        resolved_root = _require_existing_project_root(project_root)
    except ProjectStructureValidationError as exc:
        fallback_root = exc.project_root if exc.project_root is not None else Path(project_root).expanduser()
        return ProjectRootAssessment(
            state=ProjectRootState.INVALID,
            project_root=fallback_root,
            message=str(exc),
        )

    cbcs_dir = project_cbcs_dir(resolved_root)
    manifest_path = project_manifest_path(resolved_root)
    if cbcs_dir.exists() and not cbcs_dir.is_dir():
        return ProjectRootAssessment(
            state=ProjectRootState.INVALID,
            project_root=resolved_root,
            message="Project metadata path cbcs exists but is not a directory.",
        )
    if manifest_path.exists() and not manifest_path.is_file():
        return ProjectRootAssessment(
            state=ProjectRootState.INVALID,
            project_root=resolved_root,
            message="Project manifest path cbcs/project.json exists but is not a file.",
        )
    if cbcs_dir.is_dir() and manifest_path.is_file():
        return ProjectRootAssessment(
            state=ProjectRootState.CANONICAL,
            project_root=resolved_root,
            message="Project has canonical cbcs/project.json metadata.",
        )
    if _is_shared_temp_root(resolved_root):
        return ProjectRootAssessment(
            state=ProjectRootState.INVALID,
            project_root=resolved_root,
            message=(
                "Shared temporary root folders cannot be opened as projects. "
                "Choose a specific project directory instead."
            ),
        )

    try:
        inferred_entry = _infer_default_entry_file(resolved_root)
    except OSError as exc:
        return ProjectRootAssessment(
            state=ProjectRootState.INVALID,
            project_root=resolved_root,
            message=f"Unable to inspect project files for Python entrypoints: {exc}",
        )
    if inferred_entry is None:
        return ProjectRootAssessment(
            state=ProjectRootState.INVALID,
            project_root=resolved_root,
            message=(
                "Project metadata is missing and no Python files were found. "
                "Add a `.py` file (for example `main.py`) and try again."
            ),
        )

    return ProjectRootAssessment(
        state=ProjectRootState.IMPORTABLE,
        project_root=resolved_root,
        message="Project is importable and metadata can be initialized automatically.",
        inferred_entry=inferred_entry,
    )


def open_project_and_track_recent(
    project_root: PathInput,
    *,
    state_root: PathInput | None = None,
    max_recent_entries: int | None = None,
    exclude_patterns: list[str] | None = None,
) -> LoadedProject:
    """Open a project and update persisted recents only after success."""
    loaded_project = open_project(project_root, exclude_patterns=exclude_patterns)

    # Local import keeps the recents module decoupled from service module import order.
    from app.project.recent_projects import remember_recent_project

    remember_recent_project(
        loaded_project.project_root,
        state_root=state_root,
        max_entries=max_recent_entries,
    )
    return loaded_project


def create_blank_project(destination_path: PathInput, *, project_name: str) -> Path:
    """Create a new blank project with canonical metadata and root `main.py`."""
    normalized_name = project_name.strip()
    if not normalized_name:
        raise AppValidationError("project_name must be a non-empty string.")

    destination = Path(destination_path).expanduser().resolve()
    if destination.exists():
        if not destination.is_dir():
            raise AppValidationError(f"Destination is not a directory: {destination}")
        if any(destination.iterdir()):
            raise AppValidationError(f"Destination is not empty: {destination}")
    else:
        try:
            destination.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise AppValidationError(f"Unable to create destination folder: {exc}") from exc

    manifest_path = project_manifest_path(destination)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_default_project_manifest_payload(
        project_name=normalized_name,
        default_entry="main.py",
        working_directory=".",
        template="blank_project",
    )
    try:
        manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        raise AppValidationError(f"Unable to write project manifest: {exc}") from exc

    entry_path = destination / "main.py"
    if entry_path.exists() and not entry_path.is_file():
        raise AppValidationError(f"Entry path exists but is not a file: {entry_path}")
    if not entry_path.exists():
        try:
            entry_path.write_text("# Project entrypoint.\n", encoding="utf-8")
        except OSError as exc:
            raise AppValidationError(f"Unable to write main.py: {exc}") from exc

    return destination


def validate_project_structure(project_root: PathInput) -> Path:
    """Validate required on-disk project shape and return resolved root path."""
    resolved_root = _require_existing_project_root(project_root)

    cbcs_dir = project_cbcs_dir(resolved_root)
    if cbcs_dir.exists() and not cbcs_dir.is_dir():
        raise ProjectStructureValidationError(
            "Project metadata path cbcs exists but is not a directory.",
            project_root=resolved_root,
        )
    if not cbcs_dir.exists() or not cbcs_dir.is_dir():
        raise ProjectStructureValidationError(
            "Missing required metadata directory: cbcs.",
            project_root=resolved_root,
        )

    manifest_path = project_manifest_path(resolved_root)
    if manifest_path.exists() and not manifest_path.is_file():
        raise ProjectStructureValidationError(
            "Project manifest path cbcs/project.json exists but is not a file.",
            project_root=resolved_root,
            manifest_path=manifest_path,
        )
    if not manifest_path.exists() or not manifest_path.is_file():
        raise ProjectStructureValidationError(
            "Missing required project manifest file: cbcs/project.json.",
            project_root=resolved_root,
            manifest_path=manifest_path,
        )

    return resolved_root


def enumerate_project_entries(
    project_root: PathInput,
    exclude_patterns: list[str] | None = None,
) -> list[ProjectFileEntry]:
    """Recursively enumerate project entries in deterministic sorted order.

    Policy for T07:
    - include both files and directories
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
        root_text = str(resolved_root)
        for current_dir, dir_names, file_names in os.walk(
            resolved_root,
            topdown=True,
            onerror=_on_walk_error,
            followlinks=False,
        ):
            current_relative_dir = os.path.relpath(current_dir, root_text)
            if current_relative_dir == ".":
                current_relative_dir = ""
            _active_excludes = exclude_patterns or []
            dir_names[:] = sorted(
                name for name in dir_names
                if not should_exclude_name(name, _active_excludes)
            )
            file_names = sorted(
                name for name in file_names
                if not should_exclude_name(name, _active_excludes)
            )

            for directory_name in dir_names:
                entries.append(
                    _build_project_entry_from_walk(
                        current_dir=current_dir,
                        current_relative_dir=current_relative_dir,
                        entry_name=directory_name,
                        is_directory=True,
                    )
                )

            for file_name in file_names:
                entries.append(
                    _build_project_entry_from_walk(
                        current_dir=current_dir,
                        current_relative_dir=current_relative_dir,
                        entry_name=file_name,
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


def _require_existing_project_root(project_root: PathInput) -> Path:
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
    return resolved_root


def _initialize_missing_project_metadata(project_root: Path) -> None:
    cbcs_dir = project_cbcs_dir(project_root)
    manifest_path = project_manifest_path(project_root)

    if cbcs_dir.exists() and not cbcs_dir.is_dir():
        raise ProjectStructureValidationError(
            "Project metadata path cbcs exists but is not a directory.",
            project_root=project_root,
        )
    if manifest_path.exists() and not manifest_path.is_file():
        raise ProjectStructureValidationError(
            "Project manifest path cbcs/project.json exists but is not a file.",
            project_root=project_root,
            manifest_path=manifest_path,
        )
    if cbcs_dir.is_dir() and manifest_path.is_file():
        return
    if _is_shared_temp_root(project_root):
        raise ProjectStructureValidationError(
            "Shared temporary root folders cannot be opened as projects. "
            "Choose a specific project directory instead.",
            project_root=project_root,
            manifest_path=manifest_path,
        )

    try:
        inferred_entry = _infer_default_entry_file(project_root)
    except OSError as exc:
        raise ProjectStructureValidationError(
            f"Unable to inspect project files for Python entrypoints: {exc}",
            project_root=project_root,
        ) from exc

    if inferred_entry is None:
        raise ProjectStructureValidationError(
            "Project metadata is missing and no Python files were found. "
            "Add a `.py` file (for example `main.py`) and try again.",
            project_root=project_root,
            manifest_path=manifest_path,
        )

    payload = build_default_project_manifest_payload(
        project_name=_derive_project_name(project_root),
        default_entry=inferred_entry,
        working_directory=".",
        template="imported_external",
    )

    try:
        cbcs_dir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ProjectStructureValidationError(
            f"Unable to initialize project metadata at cbcs/project.json: {exc}",
            project_root=project_root,
            manifest_path=manifest_path,
        ) from exc


def _infer_default_entry_file(project_root: Path) -> str | None:
    pyproject_entry = _infer_entry_from_pyproject(project_root)
    if pyproject_entry is not None:
        return pyproject_entry

    prioritized_names = ("main.py", "run.py", "__main__.py")
    for name in prioritized_names:
        candidate = project_root / name
        if candidate.exists() and candidate.is_file():
            return name

    top_level_python_files = sorted(
        file_path.name
        for file_path in project_root.iterdir()
        if file_path.is_file() and file_path.suffix == ".py"
    )
    if top_level_python_files:
        return top_level_python_files[0]

    package_main_entry = _infer_recursive_package_main(project_root)
    if package_main_entry is not None:
        return package_main_entry

    for current_dir, dir_names, file_names in os.walk(project_root, topdown=True, followlinks=False):
        current_path = Path(current_dir)
        dir_names[:] = sorted(name for name in dir_names if name != constants.PROJECT_META_DIRNAME)
        python_files = sorted(name for name in file_names if name.endswith(".py"))
        if python_files:
            return (current_path / python_files[0]).relative_to(project_root).as_posix()
    return None


def _derive_project_name(project_root: Path) -> str:
    project_name = project_root.name.strip()
    if project_name:
        return project_name
    return "Imported Project"


def _infer_entry_from_pyproject(project_root: Path) -> str | None:
    pyproject_path = project_root / "pyproject.toml"
    if not pyproject_path.exists() or not pyproject_path.is_file():
        return None

    if _TOML_MODULE is None:
        return None

    toml_decode_error = getattr(_TOML_MODULE, "TOMLDecodeError", ValueError)
    try:
        payload = _TOML_MODULE.loads(pyproject_path.read_text(encoding="utf-8"))
    except (OSError, toml_decode_error):
        return None

    script_targets: list[str] = []
    project_scripts = payload.get("project", {}).get("scripts")
    if isinstance(project_scripts, dict):
        for script_name in sorted(project_scripts.keys()):
            target = project_scripts.get(script_name)
            if isinstance(target, str) and target.strip():
                script_targets.append(target.strip())

    poetry_scripts = payload.get("tool", {}).get("poetry", {}).get("scripts")
    if isinstance(poetry_scripts, dict):
        for script_name in sorted(poetry_scripts.keys()):
            target = poetry_scripts.get(script_name)
            if isinstance(target, str) and target.strip():
                script_targets.append(target.strip())

    for target in script_targets:
        module_reference = target.split(":", maxsplit=1)[0].strip()
        if not module_reference:
            continue
        resolved_entry = _resolve_module_reference_to_entry(project_root, module_reference)
        if resolved_entry is not None:
            return resolved_entry
    return None


def _resolve_module_reference_to_entry(project_root: Path, module_reference: str) -> str | None:
    module_parts = [part for part in module_reference.split(".") if part]
    if not module_parts:
        return None
    module_path = Path(*module_parts)
    candidate_roots = [project_root, project_root / "src"]
    for root in candidate_roots:
        file_candidate = root / module_path
        py_candidate = file_candidate.with_suffix(".py")
        if py_candidate.exists() and py_candidate.is_file():
            return py_candidate.relative_to(project_root).as_posix()
        package_main = file_candidate / "__main__.py"
        if package_main.exists() and package_main.is_file():
            return package_main.relative_to(project_root).as_posix()
        package_init = file_candidate / "__init__.py"
        if package_init.exists() and package_init.is_file():
            return package_init.relative_to(project_root).as_posix()
    return None


def _infer_recursive_package_main(project_root: Path) -> str | None:
    for candidate in sorted(project_root.rglob("__main__.py")):
        if constants.PROJECT_META_DIRNAME in candidate.parts:
            continue
        if candidate.parent == project_root:
            continue
        return candidate.relative_to(project_root).as_posix()
    return None


def _build_project_entry(path: Path, project_root: Path, *, is_directory: bool) -> ProjectFileEntry:
    relative_path = path.relative_to(project_root).as_posix()
    return ProjectFileEntry(
        relative_path=relative_path,
        absolute_path=str(path.resolve()),
        is_directory=is_directory,
    )


def _build_project_entry_from_walk(
    *,
    current_dir: str,
    current_relative_dir: str,
    entry_name: str,
    is_directory: bool,
) -> ProjectFileEntry:
    relative_path = entry_name if not current_relative_dir else f"{current_relative_dir}/{entry_name}"
    absolute_path = os.path.join(current_dir, entry_name)
    return ProjectFileEntry(
        relative_path=relative_path,
        absolute_path=absolute_path,
        is_directory=is_directory,
    )


def _resolve_project_root(project_root: PathInput) -> Path:
    candidate = Path(project_root).expanduser()
    if not candidate.is_absolute():
        raise ValueError("project_root must be an absolute path.")
    return candidate.resolve()


def _is_shared_temp_root(project_root: Path) -> bool:
    temp_root = Path(tempfile.gettempdir()).expanduser().resolve()
    return project_root == temp_root
