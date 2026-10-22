"""File I/O for the project layer.

Tests pass ``OsFileSystem`` on ``tmp_path`` or a subclass that fails a write.
Nothing here imports Qt.
"""

from __future__ import annotations

import os
import secrets
from typing import Dict, Optional, Tuple


class ProjectOpError(Exception):
    """A project operation stopped before it changed the project."""


class OsFileSystem:
    """The real filesystem. Writes are a temp file plus ``os.replace``."""

    def read_bytes(self, path: str) -> bytes:
        with open(path, "rb") as handle:
            return handle.read()

    def read_text(self, path: str) -> str:
        return self.read_bytes(path).decode("utf-8")

    def write_bytes(self, path: str, data: bytes) -> None:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = os.path.join(directory or ".", "cbcs_write_%s.tmp" % secrets.token_hex(8))
        try:
            with open(tmp, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except Exception:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            raise

    def write_text(self, path: str, text: str) -> None:
        self.write_bytes(path, text.encode("utf-8"))

    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    def is_file(self, path: str) -> bool:
        return os.path.isfile(path)

    def is_dir(self, path: str) -> bool:
        return os.path.isdir(path)

    def listdir(self, path: str) -> Tuple[str, ...]:
        return tuple(sorted(os.listdir(path)))

    def makedirs(self, path: str) -> None:
        if path:
            os.makedirs(path, exist_ok=True)

    def remove(self, path: str) -> None:
        os.remove(path)

    def replace(self, source: str, destination: str) -> None:
        directory = os.path.dirname(destination)
        if directory:
            os.makedirs(directory, exist_ok=True)
        os.replace(source, destination)


def _existing_prefix(path: str) -> str:
    """Real path of the deepest ancestor of ``path`` that already exists."""
    current = os.path.abspath(path)
    while not os.path.exists(current):
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return os.path.realpath(current)


def inside_project(path: str, root: str) -> bool:
    """True when ``path`` stays inside ``root``.

    The logical path is checked first, so ``..`` cannot escape. Then the
    existing ancestors are resolved, so a symlink that points out of the
    project is refused too. A root that has not been created yet still
    contains a path underneath it.
    """
    root_abs = os.path.abspath(root)
    path_abs = os.path.abspath(path)
    try:
        if os.path.commonpath((path_abs, root_abs)) != root_abs:
            return False
    except ValueError:
        return False
    try:
        root_real = _existing_prefix(root_abs)
        path_real = _existing_prefix(path_abs)
        return os.path.commonpath((path_real, root_real)) == root_real
    except ValueError:
        return False


def relative_posix(path: str, root: str) -> str:
    """Project-relative path with ``/`` separators. Raises when ``path`` escapes."""
    if not inside_project(path, root):
        raise ProjectOpError("That path is outside the project.")
    rel = os.path.relpath(os.path.abspath(path), os.path.abspath(root)).replace(os.sep, "/")
    if rel == ".." or rel.startswith("../"):
        raise ProjectOpError("That path is outside the project.")
    return rel


def same_path(left: str, right: str) -> bool:
    return os.path.abspath(left) == os.path.abspath(right)


class Journal:
    """Remember file bytes and put them back when a later write fails."""

    def __init__(self, fs: OsFileSystem) -> None:
        self.fs = fs
        self.originals = {}  # type: Dict[str, Optional[bytes]]

    def note(self, path: str) -> None:
        if path in self.originals:
            return
        self.originals[path] = self.fs.read_bytes(path) if self.fs.is_file(path) else None

    def put(self, path: str, data: bytes) -> None:
        self.note(path)
        self.fs.write_bytes(path, data)

    def rollback(self) -> None:
        for path, data in self.originals.items():
            if data is None:
                if self.fs.is_file(path):
                    self.fs.remove(path)
                continue
            self.fs.write_bytes(path, data)


def snapshot(fs: OsFileSystem, paths: Tuple[str, ...]) -> Dict[str, Optional[bytes]]:
    found = {}  # type: Dict[str, Optional[bytes]]
    for path in paths:
        if path in found:
            continue
        found[path] = fs.read_bytes(path) if fs.is_file(path) else None
    return found


def restore(fs: OsFileSystem, originals: Dict[str, Optional[bytes]]) -> None:
    for path, data in originals.items():
        if data is None:
            if fs.is_file(path):
                fs.remove(path)
            continue
        fs.write_bytes(path, data)
