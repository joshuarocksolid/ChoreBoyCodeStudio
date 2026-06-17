"""Shared native extension discovery for project trees (Wave 4 stub / Wave 5 SSOT)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, Sequence

COMPILED_EXTENSION_SUFFIXES: tuple[str, ...] = (".so", ".pyd", ".dll", ".dylib")


def is_native_artifact_path(path: Path) -> bool:
    """Return True when *path* is a compiled extension file."""
    return path.is_file() and path.suffix.lower() in COMPILED_EXTENSION_SUFFIXES


def import_resolves_to_native(base: Path, top_level: str) -> bool:
    """Return True if *base* looks like it ships a compiled extension for *top_level*."""
    if not top_level or not base.exists():
        return False
    for suffix in COMPILED_EXTENSION_SUFFIXES:
        if any(base.glob(f"{top_level}*{suffix}")):
            return True
        package_dir = base / top_level
        if package_dir.exists() and any(package_dir.glob(f"*{suffix}")):
            return True
    return False


def iter_native_artifacts_in_tree(base: Path) -> Iterator[Path]:
    """Yield compiled extension files under *base* in deterministic sorted order."""
    resolved = base.expanduser().resolve()
    if not resolved.is_dir():
        return
    for path in sorted(resolved.rglob("*")):
        if is_native_artifact_path(path):
            yield path


def tree_contains_native_artifacts(base: Path) -> bool:
    """Return True when any compiled extension exists under *base*."""
    return any(iter_native_artifacts_in_tree(base))


def scan_archive_namelist(names: Sequence[str]) -> bool:
    """Return True when any archive member looks like a compiled extension."""
    return any(Path(name).suffix.lower() in COMPILED_EXTENSION_SUFFIXES for name in names)
