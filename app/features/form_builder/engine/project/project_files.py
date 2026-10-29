"""The project's ``.qrc`` and ``.py`` files, for the pickers that list them (M5.0s).

``ProjectFileIndex(root)`` answers ``files(".qrc")`` and ``files(".py")`` with
project-relative paths that use ``/``, sorted. Only names are read, never file
contents, and nothing outside ``root`` is listed: a symlinked directory is not
entered, and a symlinked file that points out of the project is left out.

Skipped: hidden files and directories (a leading dot), ``vendor`` and
``vendor_*``, ``venv``, ``site-packages``, ``__pycache__``, ``node_modules`` and
any directory that holds a ``pyvenv.cfg``.

A directory's listing is kept with the directory's mtime. A later call lists
only the directories whose mtime changed (a file added, removed or renamed
changes its directory's mtime) and stats the rest. A listing made within
``RACY_SECONDS`` of its directory's mtime is not trusted, since a second write in
the same clock tick would not move the mtime, so it is read again.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple

from app.features.form_builder.engine.project.fs import inside_project

SUFFIXES = (".qrc", ".py")
RACY_SECONDS = 2.0

_SKIPPED_NAMES = frozenset({"vendor", "venv", "site-packages", "__pycache__", "node_modules"})


@dataclass(frozen=True)
class _Listing:
    mtime_ns: int
    listed_at: float
    directories: Tuple[str, ...]
    names: Tuple[str, ...]


class ProjectFileIndex:
    def __init__(self, project_root: str) -> None:
        self._root = os.path.abspath(project_root)
        self._cache: Dict[str, _Listing] = {}
        #: Directories listed from disk so far. Tests read it to see what a call cost.
        self.listings = 0

    @property
    def root(self) -> str:
        return self._root

    def files(self, suffix: str) -> Tuple[str, ...]:
        """Project-relative paths ending in ``suffix`` (``.qrc`` or ``.py``), sorted."""
        if suffix not in SUFFIXES:
            raise ValueError("the index lists %s files, not %r" % (" and ".join(SUFFIXES), suffix))
        found: List[str] = []
        stale = set(self._cache)
        pending = [""]
        while pending:
            rel = pending.pop()
            stale.discard(rel)
            directories, names = self._read(rel)
            pending.extend(directories)
            found.extend(name for name in names if name.endswith(suffix))
        for rel in stale:
            del self._cache[rel]
        return tuple(sorted(found))

    def resolve(self, relative: str) -> str:
        """The absolute path of an indexed file, or ``""`` when ``relative`` would leave the project."""
        path = os.path.abspath(os.path.join(self._root, *relative.split("/")))
        return path if inside_project(path, self._root) else ""

    def invalidate(self) -> None:
        """Forget every listing. The next call reads the whole tree."""
        self._cache.clear()

    def _read(self, rel: str) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
        path = os.path.join(self._root, *rel.split("/")) if rel else self._root
        try:
            mtime = os.stat(path).st_mtime_ns
        except OSError:
            self._cache.pop(rel, None)
            return (), ()
        cached = self._cache.get(rel)
        if cached is not None and cached.mtime_ns == mtime and mtime / 1e9 < cached.listed_at - RACY_SECONDS:
            return cached.directories, cached.names
        directories, names = self._list(path, rel)
        self._cache[rel] = _Listing(mtime, time.time(), directories, names)
        return directories, names

    def _list(self, path: str, rel: str) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
        self.listings += 1
        directories: List[str] = []
        names: List[str] = []
        try:
            entries = list(os.scandir(path))
        except OSError:
            return (), ()
        if any(entry.name == "pyvenv.cfg" for entry in entries):
            return (), ()
        for entry in entries:
            name = entry.name
            if name.startswith(".") or name in _SKIPPED_NAMES or name.startswith("vendor_"):
                continue
            child = rel + "/" + name if rel else name
            try:
                if entry.is_dir(follow_symlinks=False):
                    directories.append(child)
                elif entry.is_file(follow_symlinks=False):
                    if name.endswith(SUFFIXES):
                        names.append(child)
                elif entry.is_symlink() and entry.is_file() and name.endswith(SUFFIXES):
                    if inside_project(entry.path, self._root):
                        names.append(child)
            except OSError:
                continue
        return tuple(directories), tuple(names)


__all__ = ["RACY_SECONDS", "SUFFIXES", "ProjectFileIndex"]
