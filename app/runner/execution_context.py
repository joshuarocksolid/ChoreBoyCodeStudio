"""Runtime execution context management for runner process."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType
from typing import Any, Iterator

from app.core.errors import RunLifecycleError
from app.run.run_manifest import RunManifest


@dataclass(frozen=True)
class RunnerExecutionContext:
    """Resolved execution inputs derived from run manifest."""

    project_root: str
    working_directory: str
    entry_script_path: str
    argv: list[str]
    env_overrides: dict[str, str]
    safe_mode: bool

    @classmethod
    def from_manifest(cls, manifest: RunManifest) -> "RunnerExecutionContext":
        project_root = Path(manifest.project_root).expanduser().resolve()
        working_directory = Path(manifest.working_directory).expanduser().resolve()

        entry_candidate = Path(manifest.entry_file).expanduser()
        if not entry_candidate.is_absolute():
            entry_candidate = project_root / entry_candidate
        entry_script_path = entry_candidate.resolve()

        if not entry_script_path.exists():
            raise RunLifecycleError(f"Entry file not found: {entry_script_path}")
        if not entry_script_path.is_file():
            raise RunLifecycleError(f"Entry path must be a file: {entry_script_path}")
        if not working_directory.exists() or not working_directory.is_dir():
            raise RunLifecycleError(f"Working directory is invalid: {working_directory}")

        return cls(
            project_root=str(project_root),
            working_directory=str(working_directory),
            entry_script_path=str(entry_script_path),
            argv=list(manifest.argv),
            env_overrides=dict(manifest.env),
            safe_mode=manifest.safe_mode,
        )


@contextmanager
def apply_execution_context(execution_context: RunnerExecutionContext) -> Iterator[None]:
    """Apply and restore runner execution context around user code execution."""
    previous_cwd = Path.cwd()
    previous_argv = list(sys.argv)
    previous_path = list(sys.path)
    previous_env: dict[str, str | None] = {}
    removed_app_modules: dict[str, ModuleType] = {}
    safe_mode_originals: dict[str, object] = {}

    try:
        os.chdir(execution_context.working_directory)
        sys.argv = [execution_context.entry_script_path, *execution_context.argv]
        sys.path.insert(0, execution_context.project_root)

        for module_name in list(sys.modules.keys()):
            if module_name == "app" or module_name.startswith("app."):
                removed_app_modules[module_name] = sys.modules.pop(module_name)

        for key, value in execution_context.env_overrides.items():
            previous_env[key] = os.environ.get(key)
            os.environ[key] = value

        if execution_context.safe_mode:
            safe_mode_originals = _enable_safe_mode_subprocess_guards()

        yield
    finally:
        if safe_mode_originals:
            _restore_safe_mode_subprocess_guards(safe_mode_originals)
        for key, old_value in previous_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value
        for module_name, module in removed_app_modules.items():
            sys.modules[module_name] = module
        sys.argv = previous_argv
        sys.path[:] = previous_path
        os.chdir(previous_cwd)


def _enable_safe_mode_subprocess_guards() -> dict[str, object]:
    originals = {
        "run": subprocess.run,
        "call": subprocess.call,
        "check_call": subprocess.check_call,
        "check_output": subprocess.check_output,
        "Popen": subprocess.Popen,
    }

    def blocked(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise PermissionError("subprocess execution is disabled in safe mode.")

    subprocess_any: Any = subprocess
    subprocess_any.run = blocked
    subprocess_any.call = blocked
    subprocess_any.check_call = blocked
    subprocess_any.check_output = blocked
    subprocess_any.Popen = blocked
    return originals


def _restore_safe_mode_subprocess_guards(originals: dict[str, object]) -> None:
    subprocess_any: Any = subprocess
    subprocess_any.run = originals["run"]
    subprocess_any.call = originals["call"]
    subprocess_any.check_call = originals["check_call"]
    subprocess_any.check_output = originals["check_output"]
    subprocess_any.Popen = originals["Popen"]
