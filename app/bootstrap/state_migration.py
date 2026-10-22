"""Copy leftover settings JSON into the active settings root.

History, caches, SQLite databases, and their WAL or SHM files stay where
they are. The source tree is not deleted or modified. Copy runs only when
the destination has no settings.json.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Optional, Union

from app.bootstrap import paths as path_api
from app.bootstrap.paths import PathInput, normalize_state_root_identity
from app.bootstrap.state_roots import resolve_settings_root
from app.core import constants

_SETTINGS_FILES = (
    constants.GLOBAL_SETTINGS_FILENAME,
    constants.GLOBAL_RECENT_PROJECTS_FILENAME,
    constants.GLOBAL_PYTHON_CONSOLE_HISTORY_FILENAME,
)

_LAST_OUTCOME: Optional["MigrationOutcome"] = None


@dataclass(frozen=True)
class SettingsImported:
    dest: Path
    source: Path
    leftover_count: int
    message: str


@dataclass(frozen=True)
class SettingsAlreadyPresent:
    dest: Path


@dataclass(frozen=True)
class NoSettingsToImport:
    dest: Path
    leftover_count: int


@dataclass(frozen=True)
class SettingsImportFailed:
    dest: Path
    source: Path
    error: str


MigrationOutcome = Union[
    SettingsImported,
    SettingsAlreadyPresent,
    NoSettingsToImport,
    SettingsImportFailed,
]


def last_migration_outcome() -> Optional[MigrationOutcome]:
    """Return the outcome from the last ``migrate_legacy_global_state`` call."""
    return _LAST_OUTCOME


def migrate_legacy_global_state(state_root: Optional[PathInput] = None) -> MigrationOutcome:
    """Copy settings JSON from the first leftover root that has settings.json."""
    global _LAST_OUTCOME
    dest = resolve_settings_root(state_root).path
    if _is_file(dest / constants.GLOBAL_SETTINGS_FILENAME):
        outcome: MigrationOutcome = SettingsAlreadyPresent(dest=dest)
        _LAST_OUTCOME = outcome
        return outcome

    leftovers = _leftover_dirs(dest)
    source = next(
        (candidate for candidate in leftovers if _is_file(candidate / constants.GLOBAL_SETTINGS_FILENAME)),
        None,
    )
    if source is None:
        outcome = NoSettingsToImport(dest=dest, leftover_count=len(leftovers))
        _LAST_OUTCOME = outcome
        return outcome

    try:
        dest.mkdir(parents=True, exist_ok=True)
        for name in _SETTINGS_FILES:
            src = source / name
            target = dest / name
            if _is_file(src) and not _is_file(target):
                shutil.copy2(src, target)
    except OSError as exc:
        outcome = SettingsImportFailed(dest=dest, source=source, error=str(exc))
        _LAST_OUTCOME = outcome
        return outcome

    if len(leftovers) > 1:
        message = f"Several leftover folders were found and settings came from {source}."
    else:
        message = f"Settings imported from {source}."
    outcome = SettingsImported(
        dest=dest,
        source=source,
        leftover_count=len(leftovers),
        message=message,
    )
    _LAST_OUTCOME = outcome
    return outcome


def _leftover_dirs(dest: Path) -> list[Path]:
    dest_id = normalize_state_root_identity(dest)
    found: list[Path] = []
    for candidate in path_api.DEFAULT_PRODUCT_STATE_LAYOUT.legacy_source_roots(Path.home()):
        if not _is_directory(candidate):
            continue
        identity = normalize_state_root_identity(candidate)
        if identity == dest_id:
            continue
        found.append(identity)
    return found


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _is_directory(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False
