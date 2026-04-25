"""Single source of truth for project file traversal and exclusion.

All project-tree iteration in `app/` (search, symbol indexing, import rewrite,
diagnostics, project enumeration, packaging audit, intelligence helpers, the
shell entry-replacement dialog) routes through this module so that exclude
policy and ``cbcs/`` skipping cannot drift between callers.

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
from pathlib import Path
from typing import Callable, Iterable, Iterator, Sequence, Union

from app.core import constants
from app.core.errors import ProjectEnumerationError
from app.core.models import ProjectFileEntry
from app.project.file_excludes import should_exclude_name, should_exclude_relative_path

PathInput = Union[str, Path]

PATTERN_MODE_NAME = "name"
PATTERN_MODE_RELATIVE_PATH = "relative_path"


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
    pattern_mode: str = PATTERN_MODE_NAME,
    extra_top_level_skips: Iterable[str] = (),
    follow_symlinks: bool = False,
) -> Iterator[Path]:
    """Yield ``.py`` files under *project_root* in deterministic sorted order.

    Replaces the eight ``sorted(root.rglob('*.py')) + cbcs skip`` call sites.
    The default arguments preserve their behaviour exactly: only ``cbcs/`` is
    pruned. Pass ``extra_top_level_skips=('vendor',)`` for the packaging
    dependency audit, and ``exclude_patterns`` for callers that want effective
    project excludes (e.g. search-driven flows).
    """
    for current_path, _relative_dir, _dir_names, file_names in walk_project(
        project_root,
        exclude_patterns=exclude_patterns,
        pattern_mode=pattern_mode,
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
    follow_symlinks: bool = False,
) -> Iterator[ProjectFileEntry]:
    """Yield :class:`ProjectFileEntry` for every directory and file in the project.

    Includes the ``cbcs/`` metadata directory (project enumeration is the one
    consumer that needs the full on-disk tree, including project metadata).
    Walk-time exclusion uses ``"name"`` mode to match the historical behaviour
    of :func:`app.project.project_service.enumerate_project_entries`.
    """
    def _on_walk_error(error: OSError) -> None:
        raise ProjectEnumerationError(
            f"Failed to enumerate project files: {error}",
            project_root=_resolve_root(project_root),
        ) from error

    for current_path, relative_dir, dir_names, file_names in walk_project(
        project_root,
        exclude_patterns=exclude_patterns,
        pattern_mode=PATTERN_MODE_NAME,
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
