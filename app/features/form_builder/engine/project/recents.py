"""Recent forms for one project, stored in ``cbcs/project.json``.

The list lives beside ``form_builder.adopted_forms``. Writing one key leaves
the other, and every other manifest key, untouched.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Optional, Tuple

from app.features.form_builder.engine.project.fs import (
    OsFileSystem,
    ProjectOpError,
    inside_project,
    relative_posix,
)

_BLOCK = "form_builder"
_LIST = "recent_forms"
RECENT_LIMIT = 8
EMPTY_RECENT_TEXT = "Forms you open show up here."


def recent_forms(project_root: str, fs: OsFileSystem) -> Tuple[str, ...]:
    """Project-relative ``.ui`` paths, newest first, at most eight."""
    payload = _read(project_root, fs)
    if payload is None:
        return ()
    block = payload.get(_BLOCK)
    if not isinstance(block, dict):
        return ()
    raw = block.get(_LIST)
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
    path = _manifest(project_root)
    if not fs.is_file(path):
        return None
    try:
        payload = json.loads(fs.read_text(path))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectOpError("cbcs/project.json could not be read.") from exc
    if not isinstance(payload, dict):
        raise ProjectOpError("cbcs/project.json is not an object.")
    return payload


def _write(project_root: str, fs: OsFileSystem, recent: Tuple[str, ...]) -> None:
    path = _manifest(project_root)
    payload = _read(project_root, fs)
    if payload is None:
        payload = _new_manifest(project_root)
    block = payload.get(_BLOCK)
    if not isinstance(block, dict):
        block = {}
    else:
        block = dict(block)
    if recent:
        block[_LIST] = list(recent)
    else:
        block.pop(_LIST, None)
    if block:
        payload[_BLOCK] = block
    else:
        payload.pop(_BLOCK, None)
    fs.write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _manifest(project_root: str) -> str:
    return os.path.join(os.path.abspath(project_root), "cbcs", "project.json")


def _new_manifest(project_root: str) -> dict:
    name = os.path.basename(project_root).strip() or "Project"
    return {
        "schema_version": 2,
        "project_id": "proj_%s" % uuid.uuid4().hex,
        "name": name,
        "default_entry": "main.py",
        "default_argv": [],
        "working_directory": ".",
        "template": "utility_script",
        "run_configs": [],
        "env_overrides": {},
        "project_notes": "",
    }
