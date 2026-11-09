"""Locate FreeCAD .ui files on the machine running the tests.

FreeCAD's forms are LGPL, so they are not committed in this corpus. Callers
pass the returned paths to the reader under test and skip the FreeCAD slice
when the list is empty.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence


def _is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def default_search_roots() -> List[Path]:
    """Roots that may hold a FreeCAD install or an extracted AppImage."""
    roots = [
        Path("/Applications/FreeCAD.app"),
        Path("/opt/freecad"),
        Path.home() / "opt" / "freecad",
        Path("/home/joshua/opt/freecad"),
    ]
    override = os.environ.get("CBCS_FREECAD_ROOT")
    if override:
        roots.insert(0, Path(override))
    tmp = Path("/tmp")
    if _is_dir(tmp):
        direct = tmp / "squashfs-root"
        if _is_dir(direct):
            roots.append(direct)
        try:
            children = list(tmp.iterdir())
        except OSError:
            children = []
        for child in children:
            extracted = child / "squashfs-root"
            if _is_dir(extracted):
                roots.append(extracted)
    return roots


def _ui_under(root: Path) -> Iterator[Path]:
    for dirpath, _dirnames, filenames in os.walk(root, onerror=lambda _exc: None):
        for name in filenames:
            if name.endswith(".ui"):
                yield Path(dirpath) / name


def find_freecad_ui_files(roots: Optional[Sequence[os.PathLike]] = None) -> List[str]:
    """Return sorted absolute paths of ``*.ui`` files under ``roots``.

    Missing roots are skipped. When ``roots`` is omitted, :func:`default_search_roots`
    is used. An empty list means this machine has no FreeCAD forms to load.
    """
    chosen: Iterable[os.PathLike]
    if roots is None:
        chosen = default_search_roots()
    else:
        chosen = roots
    found = []
    seen = set()
    for raw in chosen:
        root = Path(raw)
        if not _is_dir(root):
            continue
        for path in _ui_under(root):
            try:
                resolved = str(path.resolve())
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            found.append(resolved)
    found.sort()
    return found
