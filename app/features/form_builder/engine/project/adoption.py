"""Adopted forms live in ``cbcs/project.json`` under ``form_builder.adopted_forms``.

Paths are project-relative and use ``/``. A form under ``forms/`` belongs to
the project without an entry. Un-adopt removes an entry and leaves the file.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Optional, Tuple

from app.features.form_builder.engine.project.forms import FormScope, classify_form
from app.features.form_builder.engine.project.fs import (
    OsFileSystem,
    ProjectOpError,
    inside_project,
    relative_posix,
)

_KEY = "form_builder"
_LIST = "adopted_forms"


def manifest_path(project_root: str) -> str:
    return os.path.join(os.path.abspath(project_root), "cbcs", "project.json")


def adopted_forms(project_root: str, fs: OsFileSystem) -> Tuple[str, ...]:
    """Project-relative paths recorded by Adopt this form."""
    payload = _read(project_root, fs)
    if payload is None:
        return ()
    block = payload.get(_KEY)
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
        if not text or text == ".." or text.startswith("../") or "/../" in text:
            continue
        found.append(text)
    return tuple(found)


def scope_for(ui_path: str, project_root: str, fs: OsFileSystem) -> FormScope:
    """``classify_form`` using the adopted list in the project manifest."""
    return classify_form(
        ui_path,
        project_root=project_root,
        adopted=adopted_forms(project_root, fs),
    )


def adopt_form(project_root: str, ui_path: str, fs: OsFileSystem) -> Tuple[str, ...]:
    """Record ``ui_path``. A form already under ``forms/`` is unchanged."""
    root = os.path.abspath(project_root)
    if not inside_project(ui_path, root):
        raise ProjectOpError("That form is outside the project.")
    rel = relative_posix(ui_path, root)
    if _under_forms(root, ui_path):
        raise ProjectOpError("This form is already in forms/, so it belongs to the project.")
    current = list(adopted_forms(root, fs))
    if rel not in current:
        current.append(rel)
    _write(root, fs, tuple(current))
    return tuple(current)


def unadopt_form(project_root: str, ui_path: str, fs: OsFileSystem) -> Tuple[str, ...]:
    """Drop ``ui_path`` from the adopted list. The file stays where it is."""
    root = os.path.abspath(project_root)
    if not inside_project(ui_path, root):
        raise ProjectOpError("That form is outside the project.")
    if _under_forms(root, ui_path):
        raise ProjectOpError("This form is in forms/. Move it out of forms/ if it should leave the project.")
    rel = relative_posix(ui_path, root)
    current = tuple(item for item in adopted_forms(root, fs) if item != rel)
    _write(root, fs, current)
    return current


def retarget_adoption(
    project_root: str,
    old_ui: str,
    new_ui: str,
    fs: OsFileSystem,
) -> Optional[Tuple[str, ...]]:
    """The adopted list after a move, or None when the list does not change.

    A form that leaves ``forms/`` is adopted. A form that enters ``forms/`` is
    removed from the list.
    """
    root = os.path.abspath(project_root)
    old_rel = relative_posix(old_ui, root)
    new_rel = relative_posix(new_ui, root)
    current = list(adopted_forms(root, fs))
    updated = [item for item in current if item != old_rel and item != new_rel]
    if not _under_forms(root, new_ui):
        updated.append(new_rel)
    if tuple(updated) == tuple(current):
        return None
    return tuple(updated)


def write_adopted(project_root: str, fs: OsFileSystem, adopted: Tuple[str, ...]) -> None:
    """Replace the adopted list, preserving every other manifest key."""
    _write(os.path.abspath(project_root), fs, adopted)


def _under_forms(root: str, ui_path: str) -> bool:
    return inside_project(ui_path, os.path.join(root, "forms"))


def _read(project_root: str, fs: OsFileSystem) -> Optional[dict]:
    path = manifest_path(project_root)
    if not fs.is_file(path):
        return None
    try:
        payload = json.loads(fs.read_text(path))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectOpError("cbcs/project.json could not be read.") from exc
    if not isinstance(payload, dict):
        raise ProjectOpError("cbcs/project.json is not an object.")
    return payload


def _write(project_root: str, fs: OsFileSystem, adopted: Tuple[str, ...]) -> None:
    path = manifest_path(project_root)
    payload = _read(project_root, fs)
    if payload is None:
        payload = _new_manifest(project_root)
    block = payload.get(_KEY)
    if not isinstance(block, dict):
        block = {}
    else:
        block = dict(block)
    if adopted:
        block[_LIST] = list(adopted)
    else:
        block.pop(_LIST, None)
    if block:
        payload[_KEY] = block
    else:
        payload.pop(_KEY, None)
    fs.write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


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
