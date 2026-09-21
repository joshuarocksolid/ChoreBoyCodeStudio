"""One-shot copy of leftover global state into the product dest."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union
import os
import shutil

from app.bootstrap.paths import (
    DEFAULT_PRODUCT_STATE_LAYOUT,
    PathInput,
    normalize_state_root_identity,
    resolve_global_state_root,
)


@dataclass(frozen=True)
class CopiedLegacyState:
    dest: Path
    source: Path


@dataclass(frozen=True)
class OccupiedStateRoot:
    dest: Path
    settings_path: Path


@dataclass(frozen=True)
class NoLegacyStateFound:
    dest: Path


@dataclass(frozen=True)
class PromotedStaging:
    dest: Path
    staging: Path


@dataclass(frozen=True)
class MigrationFailed:
    dest: Path
    source: Path
    staging: Path
    error: str


MigrationOutcome = Union[
    CopiedLegacyState,
    OccupiedStateRoot,
    NoLegacyStateFound,
    PromotedStaging,
    MigrationFailed,
]


def migrate_legacy_global_state(
    state_root: Optional[PathInput] = None,
) -> MigrationOutcome:
    """Copy the first leftover legacy tree into dest when dest has no settings.json."""
    dest = resolve_global_state_root(state_root)
    layout = DEFAULT_PRODUCT_STATE_LAYOUT
    settings = layout.occupancy_path(dest)
    if _is_file(settings):
        _remove_stale_staging(layout.staging_path(dest))
        return OccupiedStateRoot(dest=dest, settings_path=settings)

    staging = layout.staging_path(dest)
    if _is_file(layout.occupancy_path(staging)) and not dest.exists():
        try:
            _promote_staging(staging, dest)
        except OSError as exc:
            return MigrationFailed(dest=dest, source=staging, staging=staging, error=str(exc))
        return PromotedStaging(dest=dest, staging=staging)

    source = _first_legacy_source(dest)
    if source is None:
        return NoLegacyStateFound(dest=dest)

    try:
        _replace_tree(source, staging)
        _promote_staging(staging, dest)
    except OSError as exc:
        return MigrationFailed(dest=dest, source=source, staging=staging, error=str(exc))
    return CopiedLegacyState(dest=dest, source=source)


def _first_legacy_source(dest: Path) -> Optional[Path]:
    dest_id = normalize_state_root_identity(dest)
    for candidate in DEFAULT_PRODUCT_STATE_LAYOUT.legacy_source_roots(Path.home()):
        if not _is_directory(candidate):
            continue
        if normalize_state_root_identity(candidate) == dest_id:
            continue
        return normalize_state_root_identity(candidate)
    return None


def _replace_tree(source: Path, staging: Path) -> None:
    if staging.exists() or staging.is_symlink():
        _remove_path(staging)
    shutil.copytree(source, staging, symlinks=True)


def _promote_staging(staging: Path, dest: Path) -> None:
    if not dest.exists() and not dest.is_symlink():
        os.rename(str(staging), str(dest))
        return
    if dest.is_dir() and not dest.is_symlink():
        try:
            dest.rmdir()
        except OSError:
            _copy_children_without_overwrite(staging, dest)
            _remove_path(staging)
            return
        os.rename(str(staging), str(dest))
        return
    _copy_children_without_overwrite(staging, dest)
    _remove_path(staging)


def _copy_children_without_overwrite(staging: Path, dest: Path) -> None:
    if not dest.is_dir():
        dest.mkdir(parents=True, exist_ok=True)
    for child in staging.iterdir():
        target = dest / child.name
        if child.is_dir() and _is_directory(target):
            _copy_children_without_overwrite(child, target)
            continue
        if target.exists() or target.is_symlink():
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.copytree(child, target, symlinks=True)
        else:
            shutil.copy2(child, target, follow_symlinks=False)


def _remove_stale_staging(staging: Path) -> None:
    if staging.exists() or staging.is_symlink():
        _remove_path(staging)


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


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
