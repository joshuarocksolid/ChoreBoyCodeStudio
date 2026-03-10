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
DEFAULT_ARTIFACTS_DIRNAME = "ChoreBoyCodeStudio_artifacts"
VENDOR_DIRNAME = "vendor"
APP_RUN_ENV_VAR = "CBCS_APPRUN"
ARTIFACTS_DIR_ENV_VAR = "CBCS_ARTIFACTS_DIR"


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


def resolve_artifacts_dir(
    repo_root: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the artifacts directory from env var or sibling convention."""
    env_values = os.environ if env is None else env
    configured = env_values.get(ARTIFACTS_DIR_ENV_VAR)
    if configured:
        return Path(configured).expanduser().resolve()
    root = resolve_repo_root() if repo_root is None else repo_root.resolve()
    return (root.parent / DEFAULT_ARTIFACTS_DIRNAME).resolve()


def ensure_vendor_symlink(repo_root: Path, artifacts_dir: Path) -> None:
    """Symlink <repo_root>/vendor to <artifacts_dir>/vendor if needed.

    In development the vendored dependencies live in the artifacts directory
    (outside the workspace) while the application code resolves ``vendor/``
    relative to the repo root.  A symlink bridges the two without modifying
    any application code.
    """
    repo_vendor = repo_root / VENDOR_DIRNAME
    if repo_vendor.exists() or repo_vendor.is_symlink():
        return

    artifacts_vendor = artifacts_dir / VENDOR_DIRNAME
    if not artifacts_vendor.is_dir():
        _eprint(
            f"Vendor directory not found at {artifacts_vendor}\n"
            f"Set {ARTIFACTS_DIR_ENV_VAR} or populate the artifacts vendor directory.\n"
            "The editor will launch without vendored dependencies (tree-sitter, pyflakes)."
        )
        return

    repo_vendor.symlink_to(artifacts_vendor)


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
    artifacts_dir = resolve_artifacts_dir(repo_root=repo_root)
    ensure_vendor_symlink(repo_root, artifacts_dir)
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
