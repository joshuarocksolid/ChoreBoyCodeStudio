"""Shared FreeCAD/AppRun launch helpers used by editor-side supervisors."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Mapping

from app.core import constants

_APPRUN_ENV_KEYS_TO_DROP = ("VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT")
_FREECAD_EXECUTABLE_NAMES = {"AppRun", "freecad", "FreeCAD"}


def is_freecad_runtime_executable(runtime_executable: str) -> bool:
    runtime_path = Path(runtime_executable)
    return runtime_path.name in _FREECAD_EXECUTABLE_NAMES or runtime_path.suffix == ".AppImage"


def resolve_runtime_executable(runtime_executable: str | None) -> str:
    if runtime_executable:
        return str(Path(runtime_executable).expanduser().resolve())
    default_runtime = Path(constants.APP_RUN_PATH)
    if default_runtime.exists():
        return str(default_runtime.resolve())
    return sys.executable


def sanitize_apprun_child_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return an AppRun child environment without parent virtualenv activation."""
    resolved = dict(os.environ if env is None else env)
    for key in _APPRUN_ENV_KEYS_TO_DROP:
        resolved.pop(key, None)
    return resolved


def build_runpy_bootstrap_payload(
    *,
    script_path: str,
    path_entry: str | None = None,
    path_entries: tuple[str, ...] | None = None,
    argv: list[str] | None = None,
) -> str:
    resolved_script = str(Path(script_path).expanduser().resolve())
    statements: list[str] = ["import runpy, sys;"]
    resolved_entries: list[str] = []
    if path_entries:
        resolved_entries.extend(str(Path(entry).expanduser().resolve()) for entry in path_entries)
    elif path_entry:
        resolved_entries.append(str(Path(path_entry).expanduser().resolve()))
    for resolved_path_entry in reversed(resolved_entries):
        statements.append(
            f"sys.path.insert(0, {resolved_path_entry!r}) if {resolved_path_entry!r} not in sys.path else None;"
        )
    if argv is not None:
        statements.append(f"sys.argv={[str(a) for a in argv]!r};")
    statements.append(f"runpy.run_path({resolved_script!r}, run_name='__main__')")
    return "".join(statements)
