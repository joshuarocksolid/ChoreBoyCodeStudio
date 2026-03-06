"""Shared runner command construction for AppRun and Python runtimes."""

from __future__ import annotations

from pathlib import Path

from app.run.runtime_launch import build_runpy_bootstrap_payload, is_freecad_runtime_executable


def build_runner_command(*, runtime_executable: str, runner_boot_path: str, manifest_path: str) -> list[str]:
    """Build process command used to launch ``run_runner.py`` with a manifest."""
    resolved_runner_boot_path = str(Path(runner_boot_path).expanduser().resolve())
    if is_freecad_runtime_executable(runtime_executable):
        payload = build_runpy_bootstrap_payload(
            script_path=resolved_runner_boot_path,
            path_entry=str(Path(resolved_runner_boot_path).parent),
            argv=[resolved_runner_boot_path, "--manifest", manifest_path],
        )
        return [runtime_executable, "-c", payload]
    return [runtime_executable, resolved_runner_boot_path, "--manifest", manifest_path]
