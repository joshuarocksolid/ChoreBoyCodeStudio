"""Dev-only launcher for ChoreBoy-like FreeCAD runtime startup.

This intentionally mirrors the discovery launch contract while adding an
explicit repo-root bootstrap for FreeCAD `-c` mode, where `sys.path` may not
include the working directory.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Mapping, Sequence

from app.run.runtime_launch import build_runpy_bootstrap_payload

DEFAULT_DEV_APPRUN_PATH = Path("/opt/freecad/AppRun")
DEFAULT_EDITOR_BOOT_FILENAME = "run_editor.py"
APP_RUN_ENV_VAR = "CBCS_APPRUN"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse launcher CLI options."""
    parser = argparse.ArgumentParser(
        description="Dev-only launcher that boots run_editor.py through FreeCAD AppRun/AppImage."
    )
    parser.add_argument(
        "--apprun",
        help=f"Path to FreeCAD AppRun/AppImage executable. Defaults to {DEFAULT_DEV_APPRUN_PATH}.",
    )
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="Run in foreground and return the child process exit code.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolved launch command and exit without launching.",
    )
    return parser.parse_args(argv)


def resolve_repo_root() -> Path:
    """Return repository root for this launcher script."""
    return Path(__file__).resolve().parent


def resolve_editor_boot_path(repo_root: Path | None = None) -> Path:
    """Return absolute path to run_editor.py."""
    resolved_root = resolve_repo_root() if repo_root is None else repo_root.resolve()
    return (resolved_root / DEFAULT_EDITOR_BOOT_FILENAME).resolve()


def resolve_apprun_path(cli_apprun: str | None, env: Mapping[str, str] | None = None) -> Path:
    """Resolve FreeCAD runtime path from CLI, env, or default."""
    env_values = os.environ if env is None else env
    if cli_apprun:
        return Path(cli_apprun).expanduser().resolve()

    configured_path = env_values.get(APP_RUN_ENV_VAR)
    if configured_path:
        return Path(configured_path).expanduser().resolve()

    return DEFAULT_DEV_APPRUN_PATH


def build_apprun_command(app_run_path: Path, editor_boot_path: Path) -> list[str]:
    """Build AppRun command that executes run_editor.py in-runtime."""
    repo_root = editor_boot_path.parent.resolve()
    payload = _build_bootstrap_payload(repo_root=repo_root, editor_boot_path=editor_boot_path.resolve())
    return [str(app_run_path), "-c", payload]


def _build_bootstrap_payload(repo_root: Path, editor_boot_path: Path) -> str:
    """Build inline bootstrap payload for FreeCAD `-c` execution."""
    return build_runpy_bootstrap_payload(
        script_path=str(editor_boot_path),
        path_entry=str(repo_root),
    )


def _print_dry_run(command: list[str], app_run_path: Path, editor_boot_path: Path, foreground: bool) -> None:
    mode = "foreground" if foreground else "detached"
    print(f"AppRun path: {app_run_path}")
    print(f"Editor boot script: {editor_boot_path}")
    print(f"Launch mode: {mode}")
    print(f"Command: {shlex.join(command)}")


def _validate_launch_paths(app_run_path: Path, editor_boot_path: Path) -> int:
    if not app_run_path.exists():
        _eprint(
            f"FreeCAD runtime path not found: {app_run_path}\n"
            f"Pass --apprun <path> or set {APP_RUN_ENV_VAR}."
        )
        return 2

    if not os.access(app_run_path, os.X_OK):
        _eprint(
            f"FreeCAD runtime is not executable: {app_run_path}\n"
            "Fix permissions or provide a different --apprun path."
        )
        return 2

    if not editor_boot_path.exists():
        _eprint(
            f"Editor boot script not found: {editor_boot_path}\n"
            "Run this launcher from the repository where run_editor.py exists."
        )
        return 3

    return 0


def _eprint(message: str) -> None:
    print(message, file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    """Launch run_editor.py through FreeCAD runtime in dev parity mode."""
    args = parse_args(argv)
    repo_root = resolve_repo_root()
    app_run_path = resolve_apprun_path(args.apprun)
    editor_boot_path = resolve_editor_boot_path(repo_root=repo_root)
    command = build_apprun_command(app_run_path=app_run_path, editor_boot_path=editor_boot_path)

    if args.dry_run:
        _print_dry_run(command, app_run_path, editor_boot_path, args.foreground)
        return 0

    validation_code = _validate_launch_paths(app_run_path, editor_boot_path)
    if validation_code != 0:
        return validation_code

    try:
        if args.foreground:
            completed = subprocess.run(command, cwd=str(repo_root), check=False)
            return int(completed.returncode)

        process = subprocess.Popen(command, cwd=str(repo_root), start_new_session=True)
    except OSError as exc:
        _eprint(f"Failed to launch FreeCAD runtime: {exc}")
        return 1

    print(f"Launched editor in detached mode (pid={process.pid}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
