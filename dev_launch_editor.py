"""Dev-only launcher for ChoreBoy-like FreeCAD runtime startup.

This intentionally mirrors the discovery launch contract while adding an
explicit repo-root bootstrap for FreeCAD `-c` mode, where `sys.path` may not
include the working directory.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Mapping, Sequence

from app.run.runtime_launch import build_runpy_bootstrap_payload, sanitize_apprun_child_env

DEFAULT_DEV_APPRUN_PATH = Path("/opt/freecad/AppRun")
DEFAULT_EDITOR_BOOT_FILENAME = "run_editor.py"
DEFAULT_ARTIFACTS_DIRNAME = "ChoreBoyCodeStudio_artifacts"
VENDOR_DIRNAME = "vendor"
VENDOR_PY39_DIRNAME = "vendor_py39"
VENDOR_PY311_DIRNAME = "vendor_py311"
LEGACY_VENDOR_DIRNAME = "vendor"
VENDOR_PY39_PROFILE = "py39"
VENDOR_PY311_PROFILE = "py311"
APP_RUN_ENV_VAR = "CBCS_APPRUN"
FREECAD_APPRUN_ENV_VAR = "FREECAD_APPRUN"
ARTIFACTS_DIR_ENV_VAR = "CBCS_ARTIFACTS_DIR"
VENDOR_PROFILE_ENV_VAR = "CBCS_VENDOR_PROFILE"
LOCAL_DEV_APPRUN_RELATIVE = Path("opt/freecad/AppRun")
APPRUN_SOABI_PROBE_TIMEOUT_SECONDS = 10


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
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Run the tree-sitter runtime probe through AppRun and exit.",
    )
    return parser.parse_args(argv)


def resolve_repo_root() -> Path:
    """Return repository root for this launcher script."""
    return Path(__file__).resolve().parent


def resolve_editor_boot_path(repo_root: Path | None = None) -> Path:
    """Return absolute path to run_editor.py."""
    resolved_root = resolve_repo_root() if repo_root is None else repo_root.resolve()
    return (resolved_root / DEFAULT_EDITOR_BOOT_FILENAME).resolve()


def resolve_local_dev_apprun_path(home: Path | None = None) -> Path:
    """Return the conventional local conda dev AppRun path under the home directory."""
    resolved_home = Path.home() if home is None else home.expanduser().resolve()
    return (resolved_home / LOCAL_DEV_APPRUN_RELATIVE).resolve()


def resolve_apprun_path(
    cli_apprun: str | None,
    env: Mapping[str, str] | None = None,
    *,
    home: Path | None = None,
) -> Path:
    """Resolve FreeCAD runtime path from CLI, env, or default."""
    env_values = os.environ if env is None else env
    if cli_apprun:
        return Path(cli_apprun).expanduser().resolve()

    configured_path = env_values.get(APP_RUN_ENV_VAR)
    if configured_path:
        return Path(configured_path).expanduser().resolve()

    freecad_apprun = env_values.get(FREECAD_APPRUN_ENV_VAR)
    if freecad_apprun:
        return Path(freecad_apprun).expanduser().resolve()

    local_apprun = resolve_local_dev_apprun_path(home=home)
    if local_apprun.exists() and os.access(local_apprun, os.X_OK):
        return local_apprun

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


def vendor_dirname_for_profile(profile: str) -> str:
    if profile == VENDOR_PY39_PROFILE:
        return VENDOR_PY39_DIRNAME
    if profile == VENDOR_PY311_PROFILE:
        return VENDOR_PY311_DIRNAME
    raise ValueError(f"unsupported vendor profile: {profile}")


def setup_script_for_profile(profile: str) -> str:
    if profile == VENDOR_PY39_PROFILE:
        return "./scripts/setup_vendor_py39.sh"
    return "./scripts/setup_vendor_py311.sh"


def probe_apprun_soabi(app_run_path: Path, timeout: float = APPRUN_SOABI_PROBE_TIMEOUT_SECONDS) -> str | None:
    """Return the AppRun Python SOABI string, or None when probing fails."""
    if not app_run_path.exists() or not os.access(app_run_path, os.X_OK):
        return None
    command = [
        str(app_run_path),
        "-c",
        "import sysconfig; print(sysconfig.get_config_var('SOABI') or '')",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=sanitize_apprun_child_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    value = (completed.stdout or "").strip()
    return value or None


def resolve_vendor_profile(
    app_run_path: Path | None,
    env: Mapping[str, str] | None = None,
) -> str:
    """Map the selected AppRun runtime to a vendor profile name."""
    env_values = os.environ if env is None else env
    override = env_values.get(VENDOR_PROFILE_ENV_VAR, "").strip().lower()
    if override in {VENDOR_PY39_PROFILE, VENDOR_PY311_PROFILE}:
        return override

    if app_run_path is None:
        _eprint(
            "Cannot resolve vendor profile: AppRun path is missing. "
            f"Set {VENDOR_PROFILE_ENV_VAR}=py39|py311 or configure AppRun."
        )
        raise SystemExit(1)

    soabi = probe_apprun_soabi(app_run_path)
    if soabi is not None and soabi.startswith("cpython-39"):
        return VENDOR_PY39_PROFILE
    if soabi is not None and soabi.startswith("cpython-311"):
        return VENDOR_PY311_PROFILE
    _eprint(
        "Cannot detect AppRun Python SOABI (probe failed or unsupported version). "
        f"Set {VENDOR_PROFILE_ENV_VAR}=py39|py311 explicitly."
    )
    raise SystemExit(1)


def resolve_artifacts_vendor_dir(artifacts_dir: Path, profile: str) -> Path:
    """Return the artifacts vendor directory for a profile."""
    return (artifacts_dir / vendor_dirname_for_profile(profile)).resolve()


def ensure_vendor_symlink(
    repo_root: Path,
    artifacts_dir: Path,
    *,
    app_run_path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    """Symlink ``<repo_root>/vendor`` to the profile-matched artifacts vendor tree."""
    profile = resolve_vendor_profile(app_run_path, env=env)
    artifacts_vendor = resolve_artifacts_vendor_dir(artifacts_dir, profile)
    repo_vendor = repo_root / VENDOR_DIRNAME

    if not artifacts_vendor.is_dir():
        _eprint(
            f"Vendor directory not found for profile '{profile}': {artifacts_vendor}\n"
            f"Run {setup_script_for_profile(profile)} or set {VENDOR_PROFILE_ENV_VAR}.\n"
            "The editor will launch without vendored dependencies (tree-sitter, pyflakes)."
        )
        return

    if repo_vendor.is_symlink():
        if repo_vendor.resolve() == artifacts_vendor:
            return
        repo_vendor.unlink()
    elif repo_vendor.exists():
        _eprint(
            f"Refusing to replace existing vendor directory: {repo_vendor}\n"
            "Remove it or migrate with scripts/migrate_vendor_to_py311.sh, then retry."
        )
        raise SystemExit(1)

    repo_vendor.symlink_to(artifacts_vendor)
    print(f"Linked vendor profile '{profile}': {repo_vendor} -> {artifacts_vendor}")


def build_apprun_command(app_run_path: Path, editor_boot_path: Path) -> list[str]:
    """Build AppRun command that executes run_editor.py in-runtime."""
    repo_root = editor_boot_path.parent.resolve()
    payload = _build_bootstrap_payload(repo_root=repo_root, editor_boot_path=editor_boot_path.resolve())
    return [str(app_run_path), "-c", payload]


def build_treesitter_probe_command(app_run_path: Path, repo_root: Path) -> list[str]:
    """Build AppRun command that runs the tree-sitter runtime probe."""
    resolved_root = str(repo_root.resolve())
    probe_payload = (
        "import json, os, sys; "
        f"root={resolved_root!r}; "
        "sys.path.insert(0, root); "
        "os.chdir(root); "
        "from pathlib import Path; "
        "from testing.treesitter_runtime_probe import run_probe; "
        "result = run_probe(Path(root)); "
        "print(json.dumps(result, indent=2, sort_keys=True))"
    )
    return [str(app_run_path), "-c", probe_payload]


def run_treesitter_probe(app_run_path: Path, repo_root: Path) -> int:
    """Execute the tree-sitter runtime probe through AppRun."""
    validation_code = _validate_launch_paths(app_run_path, resolve_editor_boot_path(repo_root=repo_root))
    if validation_code != 0:
        return validation_code

    command = build_treesitter_probe_command(app_run_path, repo_root)
    try:
        completed = subprocess.run(
            command,
            cwd=str(repo_root),
            check=False,
            capture_output=True,
            text=True,
            env=sanitize_apprun_child_env(),
        )
    except OSError as exc:
        _eprint(f"Failed to run tree-sitter probe: {exc}")
        return 1

    if completed.stdout:
        print(completed.stdout.rstrip())
    if completed.stderr:
        print(completed.stderr.rstrip(), file=sys.stderr)

    if completed.returncode != 0:
        return int(completed.returncode)

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        _eprint("Tree-sitter probe did not return valid JSON.")
        return 1

    return 0 if payload.get("is_available") else 1


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
    app_run_path = resolve_apprun_path(args.apprun)
    editor_boot_path = resolve_editor_boot_path(repo_root=repo_root)

    if args.dry_run:
        command = build_apprun_command(app_run_path=app_run_path, editor_boot_path=editor_boot_path)
        _print_dry_run(command, app_run_path, editor_boot_path, args.foreground)
        return 0

    ensure_vendor_symlink(repo_root, artifacts_dir, app_run_path=app_run_path)

    if args.probe:
        profile = resolve_vendor_profile(app_run_path)
        soabi = probe_apprun_soabi(app_run_path)
        print(f"AppRun path: {app_run_path}")
        print(f"Vendor profile: {profile}")
        if soabi:
            print(f"AppRun SOABI: {soabi}")
        return run_treesitter_probe(app_run_path, repo_root)

    command = build_apprun_command(app_run_path=app_run_path, editor_boot_path=editor_boot_path)

    validation_code = _validate_launch_paths(app_run_path, editor_boot_path)
    if validation_code != 0:
        return validation_code

    try:
        if args.foreground:
            completed = subprocess.run(
                command,
                cwd=str(repo_root),
                check=False,
                env=sanitize_apprun_child_env(),
            )
            return int(completed.returncode)

        process = subprocess.Popen(
            command,
            cwd=str(repo_root),
            env=sanitize_apprun_child_env(),
            start_new_session=True,
        )
    except OSError as exc:
        _eprint(f"Failed to launch FreeCAD runtime: {exc}")
        return 1

    print(f"Launched editor in detached mode (pid={process.pid}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
