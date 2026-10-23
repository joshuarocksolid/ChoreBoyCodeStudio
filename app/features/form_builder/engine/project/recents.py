"""Recent forms for one project.

The list is per-user state in ``cbcs/recent_forms.json``, the same directory
the shell uses for ``cbcs/session.json``. This module never creates or
rewrites the project manifest.
"""

from __future__ import annotations

import json
import os
from typing import Optional, Tuple

from app.features.form_builder.engine.project.fs import (
    OsFileSystem,
    ProjectOpError,
    inside_project,
    relative_posix,
)

_LIST = "recent_forms"
_FILENAME = "recent_forms.json"
RECENT_LIMIT = 8
EMPTY_RECENT_TEXT = "Forms you open show up here."


def recent_forms(project_root: str, fs: OsFileSystem) -> Tuple[str, ...]:
    """Project-relative ``.ui`` paths, newest first, at most eight."""
    payload = _read(project_root, fs)
    if payload is None:
        return ()
    raw = payload.get(_LIST)
    if not isinstance(raw, list):
        return ()
    found = []
    for item in raw:
        if not isinstance(item, str):
            continue
        text = item.strip().replace("\\", "/")
        while text.startswith("./"):
            text = text[2:]
        if not text.endswith(".ui"):
            continue
        if not text or text == ".." or text.startswith("../") or "/../" in text:
            continue
        if text not in found:
            found.append(text)
        if len(found) == RECENT_LIMIT:
            break
    return tuple(found)


def remember_form(project_root: str, ui_path: str, fs: OsFileSystem) -> Tuple[str, ...]:
    """Put ``ui_path`` first and drop anything past the eighth entry."""
    root = os.path.abspath(project_root)
    if not inside_project(ui_path, root):
        raise ProjectOpError("That form is outside the project.")
    rel = relative_posix(ui_path, root)
    if not rel.endswith(".ui"):
        raise ProjectOpError("Recent forms are .ui files.")
    current = [item for item in recent_forms(root, fs) if item != rel]
    updated = tuple([rel] + current)[:RECENT_LIMIT]
    _write(root, fs, updated)
    return updated


def recent_folder(relative_path: str) -> str:
    """Folder shown in the faint colour. ``forms/invoice.ui`` becomes ``forms/``."""
    folder = os.path.dirname(relative_path.replace("\\", "/"))
    if not folder or folder == ".":
        return ""
    return folder + "/"


def recent_name(relative_path: str) -> str:
    return os.path.basename(relative_path.replace("\\", "/"))


def _read(project_root: str, fs: OsFileSystem) -> Optional[dict]:
    path = _store(project_root)
    if not fs.is_file(path):
        return None
    try:
        payload = json.loads(fs.read_text(path))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectOpError("cbcs/recent_forms.json could not be read.") from exc
    if not isinstance(payload, dict):
        raise ProjectOpError("cbcs/recent_forms.json is not an object.")
    return payload


def _write(project_root: str, fs: OsFileSystem, recent: Tuple[str, ...]) -> None:
    path = _store(project_root)
    fs.write_text(path, json.dumps({_LIST: list(recent)}, indent=2) + "\n")


def _store(project_root: str) -> str:
    return os.path.join(os.path.abspath(project_root), "cbcs", _FILENAME)
