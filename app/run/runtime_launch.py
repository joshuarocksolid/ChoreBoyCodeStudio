"""Shared FreeCAD/AppRun launch helpers used by editor-side supervisors."""

from __future__ import annotations

from pathlib import Path
import sys

from app.core import constants

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


def build_runpy_bootstrap_payload(
    *,
    script_path: str,
    path_entry: str | None = None,
    argv: list[str] | None = None,
) -> str:
    resolved_script = str(Path(script_path).expanduser().resolve())
    statements: list[str] = ["import runpy, sys;"]
    if path_entry:
        resolved_path_entry = str(Path(path_entry).expanduser().resolve())
        statements.append(f"sys.path.insert(0, {resolved_path_entry!r}) if {resolved_path_entry!r} not in sys.path else None;")
    if argv is not None:
        statements.append(f"sys.argv={list(argv)!r};")
    statements.append(f"runpy.run_path({resolved_script!r}, run_name='__main__')")
    return "".join(statements)
