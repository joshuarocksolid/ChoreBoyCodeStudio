"""Shared runner command construction for AppRun and Python runtimes."""

from __future__ import annotations

from pathlib import Path

_FREECAD_EXECUTABLE_NAMES = {"AppRun", "freecad", "FreeCAD"}


def build_runner_command(*, runtime_executable: str, runner_boot_path: str, manifest_path: str) -> list[str]:
    """Build process command used to launch ``run_runner.py`` with a manifest."""
    resolved_runner_boot_path = str(Path(runner_boot_path).expanduser().resolve())
    runtime_path = Path(runtime_executable)
    if runtime_path.name in _FREECAD_EXECUTABLE_NAMES or runtime_path.suffix == ".AppImage":
        runner_parent = str(Path(resolved_runner_boot_path).parent)
        payload = (
            "import runpy, sys;"
            f"sys.path.insert(0, {runner_parent!r});"
            f"sys.argv={[resolved_runner_boot_path, '--manifest', manifest_path]!r};"
            f"runpy.run_path({resolved_runner_boot_path!r}, run_name='__main__')"
        )
        return [runtime_executable, "-c", payload]
    return [runtime_executable, resolved_runner_boot_path, "--manifest", manifest_path]
