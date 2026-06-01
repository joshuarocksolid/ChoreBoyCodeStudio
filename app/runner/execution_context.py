"""Runtime execution context management for runner process."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import sys
from types import ModuleType
from typing import Iterator

from app.bootstrap.paths import project_manifest_path
from app.bootstrap.vendor_paths import ensure_vendor_path_on_sys_path
from app.core import constants
from app.core.errors import RunLifecycleError
from app.project.import_layout import resolve_project_import_layout
from app.project.project_manifest import load_project_manifest
from app.run.run_manifest import RunManifest


@dataclass(frozen=True)
class RunnerExecutionContext:
    """Resolved execution inputs derived from run manifest."""

    project_root: str
    working_directory: str
    entry_script_path: str
    argv: list[str]
    env_overrides: dict[str, str]

    @classmethod
    def from_manifest(cls, manifest: RunManifest) -> "RunnerExecutionContext":
        project_root = Path(manifest.project_root).expanduser().resolve()
        working_directory = Path(manifest.working_directory).expanduser().resolve()

        if manifest.mode == constants.RUN_MODE_PYTHON_REPL:
            entry_script_path = "<python_repl>"
        else:
            entry_candidate = Path(manifest.entry_file).expanduser()
            if not entry_candidate.is_absolute():
                entry_candidate = project_root / entry_candidate
            entry_script_path = str(entry_candidate.resolve())

            entry_path = Path(entry_script_path)
            if not entry_path.exists():
                raise RunLifecycleError(f"Entry file not found: {entry_script_path}")
            if not entry_path.is_file():
                raise RunLifecycleError(f"Entry path must be a file: {entry_script_path}")
        if not working_directory.exists() or not working_directory.is_dir():
            raise RunLifecycleError(f"Working directory is invalid: {working_directory}")

        return cls(
            project_root=str(project_root),
            working_directory=str(working_directory),
            entry_script_path=entry_script_path,
            argv=list(manifest.argv),
            env_overrides=dict(manifest.env),
        )


@contextmanager
def apply_execution_context(execution_context: RunnerExecutionContext) -> Iterator[None]:
    """Apply and restore runner execution context around user code execution."""
    previous_cwd = Path.cwd()
    previous_argv = list(sys.argv)
    previous_path = list(sys.path)
    previous_env: dict[str, str | None] = {}
    removed_app_modules: dict[str, ModuleType] = {}

    try:
        os.chdir(execution_context.working_directory)
        sys.argv = [execution_context.entry_script_path, *execution_context.argv]
        ensure_vendor_path_on_sys_path()
        _apply_project_sys_path(execution_context)

        for module_name in list(sys.modules.keys()):
            if module_name == "app" or module_name.startswith("app."):
                removed_app_modules[module_name] = sys.modules.pop(module_name)

        for key, value in execution_context.env_overrides.items():
            previous_env[key] = os.environ.get(key)
            os.environ[key] = value

        yield
    finally:
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


def _apply_project_sys_path(execution_context: RunnerExecutionContext) -> None:
    project_root = Path(execution_context.project_root).expanduser().resolve()
    metadata = None
    manifest_path = project_manifest_path(project_root)
    if manifest_path.is_file():
        try:
            metadata = load_project_manifest(manifest_path)
        except Exception:
            metadata = None
    layout = resolve_project_import_layout(project_root, metadata)
    sys.path.insert(0, str(project_root))
    for entry in reversed(layout.source_roots):
        entry_text = str(entry)
        if entry_text not in sys.path:
            sys.path.insert(0, entry_text)
    entry_script = execution_context.entry_script_path
    if entry_script != "<python_repl>":
        entry_parent = str(Path(entry_script).resolve().parent)
        if entry_parent not in sys.path:
            sys.path.insert(0, entry_parent)
