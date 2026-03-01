"""Runtime execution context management for runner process."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import sys
from typing import Iterator

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
        )


@contextmanager
def apply_execution_context(execution_context: RunnerExecutionContext) -> Iterator[None]:
    """Apply and restore runner execution context around user code execution."""
    previous_cwd = Path.cwd()
    previous_argv = list(sys.argv)
    previous_path = list(sys.path)
    previous_env: dict[str, str | None] = {}

    try:
        os.chdir(execution_context.working_directory)
        sys.argv = [execution_context.entry_script_path, *execution_context.argv]
        if execution_context.project_root not in sys.path:
            sys.path.insert(0, execution_context.project_root)

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
        sys.argv = previous_argv
        sys.path[:] = previous_path
        os.chdir(previous_cwd)
