"""Single source of truth for project file traversal and exclusion.

All project-tree iteration in `app/` (search, symbol indexing, import rewrite,
diagnostics, project enumeration, packaging audit, intelligence helpers, the
shell entry-replacement dialog) routes through this module so that exclude
policy and ``cbcs/`` skipping cannot drift between callers.

**Vendor triple role (policy vocabulary):**

- User dependency: ``vendor/`` may appear in default exclude patterns for
  editor workflows.
- Project walk default: ``iter_python_files()`` does not skip ``vendor/`` unless
  callers pass excludes or ``extra_top_level_skips``.
- Packaging: payload copy may ship ``vendor/``; dependency audit skips
  top-level ``vendor/`` via ``extra_top_level_skips=('vendor',)``.

See :class:`InventoryScope` and :class:`MetaDirPolicy` for per-surface policy
names used by parity tests and upcoming scope-aware iterators.

Two pattern modes are supported:

- ``"name"``: each path segment is checked against patterns without ``/``.
  Matches the historical behaviour of :func:`enumerate_project_entries`.
- ``"relative_path"``: the full POSIX relative path is also checked against
  patterns containing ``/``. Matches the historical behaviour of
  :func:`find_in_files`.

Callers that just want the eight-site ``rglob('*.py') + cbcs skip`` behaviour
should use :func:`iter_python_files` with no patterns.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, Iterator, Sequence, Union

from dataclasses import dataclass

from app.core import constants
from app.core.errors import ProjectEnumerationError
from app.core.models import ProjectFileEntry
from app.project.file_excludes import should_exclude_name, should_exclude_relative_path
from app.project.import_layout import module_name_for_file, resolve_project_import_layout

PathInput = Union[str, Path]

PATTERN_MODE_NAME = "name"
PATTERN_MODE_RELATIVE_PATH = "relative_path"


class InventoryScope(str, Enum):
    """Named inventory surfaces that share one traversal kernel."""

    tree_entries = "tree_entries"
    python_analysis = "python_analysis"
    text_search = "text_search"
    packaging_payload = "packaging_payload"
    packaging_audit = "packaging_audit"


@dataclass(frozen=True)
class MetaDirPolicy:
    """How ``cbcs/`` (project metadata) is treated per inventory scope.

    - *tree_entries*: include metadata directory in project tree enumeration.
    - *python_analysis*: prune entire metadata directory from Python walks.
    - *text_search*: prune metadata from text search (matches python default).
    - *packaging_payload*: ship selected metadata files; prune runs/logs/cache.
    - *packaging_audit*: skip metadata for static Python dependency audit.
    """

    include_in_tree: bool = True
    prune_from_python_walk: bool = True
    prune_from_text_search: bool = True
    ship_metadata_in_payload: bool = True
    prune_payload_subdirs: tuple[str, ...] = ("runs", "logs", "cache")
    skip_in_dependency_audit: bool = True


DEFAULT_META_DIR_POLICY = MetaDirPolicy()


def _resolve_root(project_root: PathInput) -> Path:
    return Path(project_root).expanduser().resolve()


def _matches_excludes(
    *,
    name: str,
    relative_posix: str,
    is_directory: bool,
    patterns: Sequence[str],
    pattern_mode: str,
) -> bool:
    if not patterns:
        return False
    if pattern_mode == PATTERN_MODE_RELATIVE_PATH:
        return should_exclude_relative_path(
            relative_posix,
            patterns,
            is_directory=is_directory,
        )
    return should_exclude_name(name, patterns)


def _resolve_pattern_mode(
    exclude_patterns: Sequence[str],
    pattern_mode: str | None,
) -> str:
    if pattern_mode is not None:
        return pattern_mode
    if any("/" in pattern for pattern in exclude_patterns):
        return PATTERN_MODE_RELATIVE_PATH
    return PATTERN_MODE_NAME


def walk_project(
    project_root: PathInput,
    *,
    exclude_patterns: Sequence[str] = (),
    pattern_mode: str = PATTERN_MODE_NAME,
    extra_top_level_skips: Iterable[str] = (),
    follow_symlinks: bool = False,
    include_meta_dir: bool = False,
    on_error: Callable[[OSError], None] | None = None,
) -> Iterator[tuple[Path, str, list[str], list[str]]]:
    """Yield ``(current_dir, current_relative_dir, dir_names, file_names)`` for the project.

    ``cbcs/`` (``constants.PROJECT_META_DIRNAME``) is pruned at every level
    unless ``include_meta_dir`` is True (project enumeration callers that need
    to surface the metadata directory in the file tree). Names in
    ``extra_top_level_skips`` are pruned only when they appear as a top-level
    child of the project root (e.g. ``("vendor",)`` for the packaging
    dependency audit).

    Both ``dir_names`` and ``file_names`` are sorted lexicographically and
    already filtered against ``exclude_patterns`` using ``pattern_mode``.
    Callers may further mutate the yielded ``dir_names`` list to prune the
    walk, matching the standard :func:`os.walk` contract.
    """
    root = _resolve_root(project_root)
    top_level_skips = {name for name in extra_top_level_skips if name}
    root_text = str(root)
    for current_dir, dir_names, file_names in os.walk(
        root,
        topdown=True,
        onerror=on_error,
        followlinks=follow_symlinks,
    ):
        current_relative_dir = os.path.relpath(current_dir, root_text)
        if current_relative_dir == ".":
            current_relative_dir = ""

        is_root_level = current_relative_dir == ""
        pruned_dir_names: list[str] = []
        for name in sorted(dir_names):
            if name == constants.PROJECT_META_DIRNAME and not include_meta_dir:
                continue
            if is_root_level and name in top_level_skips:
                continue
            relative_dir = name if is_root_level else f"{current_relative_dir}/{name}"
            if _matches_excludes(
                name=name,
                relative_posix=relative_dir,
                is_directory=True,
                patterns=exclude_patterns,
                pattern_mode=pattern_mode,
            ):
                continue
            pruned_dir_names.append(name)
        dir_names[:] = pruned_dir_names

        pruned_file_names: list[str] = []
        for name in sorted(file_names):
            relative_file = name if is_root_level else f"{current_relative_dir}/{name}"
            if _matches_excludes(
                name=name,
                relative_posix=relative_file,
                is_directory=False,
                patterns=exclude_patterns,
                pattern_mode=pattern_mode,
            ):
                continue
            pruned_file_names.append(name)

        yield Path(current_dir), current_relative_dir, dir_names, pruned_file_names


def iter_python_files(
    project_root: PathInput,
    *,
    exclude_patterns: Sequence[str] = (),
    pattern_mode: str | None = None,
    extra_top_level_skips: Iterable[str] = (),
    follow_symlinks: bool = False,
) -> Iterator[Path]:
    """Yield ``.py`` files under *project_root* in deterministic sorted order.

    Replaces the eight ``sorted(root.rglob('*.py')) + cbcs skip`` call sites.
    The default arguments preserve their behaviour exactly: only ``cbcs/`` is
    pruned. Pass ``extra_top_level_skips=('vendor',)`` for the packaging
    dependency audit, and ``exclude_patterns`` for callers that want effective
    project excludes (e.g. search-driven flows).

    When *pattern_mode* is omitted, slash-containing patterns automatically use
    :data:`PATTERN_MODE_RELATIVE_PATH` so tree and search agree on globs like
    ``src/generated/*``.
    """
    resolved_mode = _resolve_pattern_mode(exclude_patterns, pattern_mode)
    for current_path, _relative_dir, _dir_names, file_names in walk_project(
        project_root,
        exclude_patterns=exclude_patterns,
        pattern_mode=resolved_mode,
        extra_top_level_skips=extra_top_level_skips,
        follow_symlinks=follow_symlinks,
    ):
        for name in file_names:
            if name.endswith(".py"):
                yield current_path / name


def iter_text_file_paths(
    project_root: PathInput,
    *,
    exclude_patterns: Sequence[str] = (),
    follow_symlinks: bool = False,
) -> Iterator[tuple[Path, str]]:
    """Yield ``(absolute_path, relative_posix)`` for every project file.

    Used by the project-wide text search. Pattern matching uses
    :data:`PATTERN_MODE_RELATIVE_PATH` so that user-configured patterns like
    ``build/**`` and ``src/*.gen.py`` work as expected.
    """
    for current_path, relative_dir, _dir_names, file_names in walk_project(
        project_root,
        exclude_patterns=exclude_patterns,
        pattern_mode=PATTERN_MODE_RELATIVE_PATH,
        follow_symlinks=follow_symlinks,
    ):
        for name in file_names:
            relative_path = name if not relative_dir else f"{relative_dir}/{name}"
            yield current_path / name, relative_path


def iter_project_entries(
    project_root: PathInput,
    *,
    exclude_patterns: Sequence[str] = (),
    pattern_mode: str | None = None,
    follow_symlinks: bool = False,
) -> Iterator[ProjectFileEntry]:
    """Yield :class:`ProjectFileEntry` for every directory and file in the project.

    Includes the ``cbcs/`` metadata directory (project enumeration is the one
    consumer that needs the full on-disk tree, including project metadata).
    Walk-time exclusion uses name mode for segment-only patterns and relative
    path mode when any pattern contains ``/``.
    """
    resolved_mode = _resolve_pattern_mode(exclude_patterns, pattern_mode)

    def _on_walk_error(error: OSError) -> None:
        raise ProjectEnumerationError(
            f"Failed to enumerate project files: {error}",
            project_root=_resolve_root(project_root),
        ) from error

    for current_path, relative_dir, dir_names, file_names in walk_project(
        project_root,
        exclude_patterns=exclude_patterns,
        pattern_mode=resolved_mode,
        follow_symlinks=follow_symlinks,
        include_meta_dir=True,
        on_error=_on_walk_error,
    ):
        for directory_name in dir_names:
            yield _build_entry(current_path, relative_dir, directory_name, is_directory=True)
        for file_name in file_names:
            yield _build_entry(current_path, relative_dir, file_name, is_directory=False)


def _build_entry(
    current_path: Path,
    relative_dir: str,
    entry_name: str,
    *,
    is_directory: bool,
) -> ProjectFileEntry:
    relative_path = entry_name if not relative_dir else f"{relative_dir}/{entry_name}"
    absolute_path = str(current_path / entry_name)
    return ProjectFileEntry(
        relative_path=relative_path,
        absolute_path=absolute_path,
        is_directory=is_directory,
    )


@dataclass(frozen=True)
class ProjectInventorySnapshot:
    """One deterministic walk of importable Python modules under a project root."""

    project_root: str
    python_file_paths: tuple[str, ...]
    module_names: tuple[str, ...]


def build_project_inventory_snapshot(
    project_root: PathInput,
    *,
    exclude_patterns: Sequence[str] = (),
) -> ProjectInventorySnapshot:
    """Build a snapshot from a single project walk."""
    root = _resolve_root(project_root)
    resolved_mode = _resolve_pattern_mode(exclude_patterns, None)
    python_paths = tuple(
        str(path.resolve())
        for path in iter_python_files(
            root,
            exclude_patterns=exclude_patterns,
            pattern_mode=resolved_mode,
        )
    )
    module_names = tuple(
        sorted(
            {
                name
                for name in (_module_name_from_python_path(root, Path(path)) for path in python_paths)
                if name
            }
        )
    )
    return ProjectInventorySnapshot(
        project_root=str(root),
        python_file_paths=python_paths,
        module_names=module_names,
    )


def module_names_from_snapshot(snapshot: ProjectInventorySnapshot) -> list[str]:
    """Return module names captured by a snapshot."""
    return list(snapshot.module_names)


def _module_name_from_python_path(project_root: Path, file_path: Path) -> str | None:
    layout = resolve_project_import_layout(project_root)
    return module_name_for_file(layout, file_path)
