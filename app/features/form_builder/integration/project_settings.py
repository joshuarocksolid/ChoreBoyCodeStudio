"""Project settings for ``form_builder.*`` keys (M5.0s).

They live in the ``form_builder`` object of ``<project>/cbcs/project.json``,
next to ``adopted_forms``. Lanes ask for a setting by its short name:
``get_setting(root, "custom_widgets")`` reads ``form_builder.custom_widgets``.

Every write reads the file again, changes only the named keys and swaps the
file in with a temporary file and ``os.replace`` (``OsFileSystem.write_bytes``),
so a crash between the two leaves either the old file or the new one, never a
half-written one. Other top-level keys and other ``form_builder`` keys are
kept. A manifest that cannot be read, or whose ``form_builder`` is not an
object, is never replaced: the call raises ``ProjectOpError`` and the file
stays as it was.

Concurrent writers. Inside this process, writes are serialized by one lock,
so two lanes changing different keys both keep their change. Another process
(or the shell's own project writer) that writes between our read and our
replace wins for the keys it wrote and loses nothing it did not; the file is
always one whole version, never a mix. The read is the last moment before
the replace, which keeps that window to one ``json.dumps``.
"""

from __future__ import annotations

import json
import os
import re
import threading
from typing import Any, Dict, Mapping, Optional

from app.features.form_builder.engine.project.adoption import (
    _new_manifest,  # pyright: ignore[reportPrivateUsage]
    manifest_path,
)
from app.features.form_builder.engine.project.fs import OsFileSystem, ProjectOpError

BLOCK = "form_builder"
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_WRITE_LOCK = threading.Lock()


def read_settings(project_root: str, fs: Optional[OsFileSystem] = None) -> Dict[str, Any]:
    """The ``form_builder`` object, as a new dict. Empty when the project has no manifest yet."""
    manifest = _read_manifest(project_root, fs or OsFileSystem())
    if manifest is None:
        return {}
    return dict(_block(manifest))


def get_setting(project_root: str, name: str, default: Any = None, fs: Optional[OsFileSystem] = None) -> Any:
    _check_name(name)
    return read_settings(project_root, fs).get(name, default)


def set_setting(project_root: str, name: str, value: Any, fs: Optional[OsFileSystem] = None) -> Dict[str, Any]:
    return update_settings(project_root, {name: value}, fs)


def update_settings(
    project_root: str,
    changes: Mapping[str, Any],
    fs: Optional[OsFileSystem] = None,
) -> Dict[str, Any]:
    """Apply ``changes`` in one write. A ``None`` value removes its key. Returns the new object."""
    for name in changes:
        _check_name(name)
    files = fs or OsFileSystem()
    root = os.path.abspath(project_root)
    with _WRITE_LOCK:
        return _update_locked(root, changes, files)


def _update_locked(root: str, changes: Mapping[str, Any], files: OsFileSystem) -> Dict[str, Any]:
    manifest = _read_manifest(root, files)
    if manifest is None:
        manifest = _new_manifest(root)
    block = dict(_block(manifest))
    for name, value in changes.items():
        if value is None:
            block.pop(name, None)
        else:
            block[name] = value
    if block:
        manifest[BLOCK] = block
    else:
        manifest.pop(BLOCK, None)
    try:
        text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    except (TypeError, ValueError) as exc:
        raise ProjectOpError("That setting can't be saved in cbcs/project.json.") from exc
    files.write_text(manifest_path(root), text)
    return block


def _check_name(name: str) -> None:
    if not isinstance(name, str) or _NAME.match(name) is None:
        raise ValueError("%r is not a form_builder setting name" % (name,))


def _read_manifest(project_root: str, fs: OsFileSystem) -> Optional[Dict[str, Any]]:
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


def _block(manifest: Dict[str, Any]) -> Dict[str, Any]:
    block = manifest.get(BLOCK)
    if block is None:
        return {}
    if not isinstance(block, dict):
        raise ProjectOpError("form_builder in cbcs/project.json is not an object.")
    return block


__all__ = ["BLOCK", "get_setting", "read_settings", "set_setting", "update_settings"]
