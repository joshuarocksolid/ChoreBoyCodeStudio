"""Pure launch planning for editor-side run orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.bootstrap.paths import (
    PathInput,
    ensure_directory,
    project_logs_dir,
    project_runs_dir,
    resolve_global_state_root,
)
from app.core import constants
from app.core.errors import RunLifecycleError
from app.core.models import LoadedProject
from app.debug.debug_breakpoints import build_breakpoint
from app.debug.debug_models import DebugBreakpoint, DebugExceptionPolicy, DebugSourceMap


@dataclass(frozen=True)
class LaunchContext:
    """Resolved paths, environment, mode, and debug settings for one run launch."""

    run_id: str
    mode: str
    project_root: str
    entry_file: str
    working_directory: str
    launch_cwd: str
    manifest_path: Path
    log_path: Path
    argv: list[str]
    env: dict[str, str]
    breakpoints: list[DebugBreakpoint]
    debug_exception_policy: DebugExceptionPolicy
    source_maps: list[DebugSourceMap]


def plan_launch(
    *,
    run_id: str,
    loaded_project: LoadedProject | None,
    entry_file: str | None = None,
    mode: str | None = None,
    argv: list[str] | None = None,
    working_directory: str | None = None,
    env_overrides: dict[str, str] | None = None,
    breakpoints: list[DebugBreakpoint] | list[dict[str, object]] | None = None,
    debug_exception_policy: DebugExceptionPolicy | None = None,
    source_maps: list[DebugSourceMap] | None = None,
    state_root: PathInput | None = None,
) -> LaunchContext:
    """Resolve launch paths, cwd, env, and debug settings without process side effects."""

    run_mode = mode or (
        constants.RUN_MODE_PYTHON_SCRIPT
        if loaded_project is not None
        else constants.RUN_MODE_PYTHON_REPL
    )

    if loaded_project is None:
        if run_mode == constants.RUN_MODE_PYTHON_REPL:
            resolved_project_root = build_repl_context_root(state_root=state_root)
            entry = entry_file or "__repl__.py"
            arguments = [] if argv is None else list(argv)
            home_directory = Path.home().expanduser().resolve()
            resolved_working_directory = resolve_working_directory(
                home_directory,
                working_directory,
                str(home_directory),
            )
        else:
            if entry_file is None:
                raise RunLifecycleError("Provide a file entry before running without a project.")
            resolved_entry = Path(entry_file).expanduser().resolve()
            if not resolved_entry.exists() or not resolved_entry.is_file():
                raise RunLifecycleError(f"Entry file not found: {resolved_entry}")
            resolved_project_root = resolved_entry.parent
            entry = str(resolved_entry)
            arguments = [] if argv is None else list(argv)
            resolved_working_directory = resolve_working_directory(
                resolved_entry.parent,
                working_directory,
                str(resolved_entry.parent),
            )
        manifest_path = build_repl_manifest_path(run_id, state_root=state_root)
        log_path = build_repl_log_path(run_id, state_root=state_root)
        merged_env_overrides = {} if env_overrides is None else dict(env_overrides)
        launch_cwd = str(resolved_working_directory)
    else:
        entry = entry_file or loaded_project.metadata.default_entry
        arguments = list(loaded_project.metadata.default_argv) if argv is None else list(argv)
        resolved_project_root = Path(loaded_project.project_root).expanduser().resolve()
        configured_working_directory = working_directory or loaded_project.metadata.working_directory
        resolved_working_directory = (resolved_project_root / configured_working_directory).resolve()
        manifest_path = build_run_manifest_path(resolved_project_root, run_id)
        log_path = build_run_log_path(resolved_project_root, run_id)
        merged_env_overrides = dict(loaded_project.metadata.env_overrides)
        if env_overrides is not None:
            merged_env_overrides.update(env_overrides)
        launch_cwd = str(resolved_project_root)

    return LaunchContext(
        run_id=run_id,
        mode=run_mode,
        project_root=str(resolved_project_root),
        entry_file=entry,
        working_directory=str(resolved_working_directory),
        launch_cwd=launch_cwd,
        manifest_path=manifest_path,
        log_path=log_path,
        argv=arguments,
        env=merged_env_overrides,
        breakpoints=normalize_breakpoints(breakpoints),
        debug_exception_policy=debug_exception_policy or DebugExceptionPolicy(),
        source_maps=[] if source_maps is None else list(source_maps),
    )


def resolve_working_directory(
    base_directory: Path,
    configured_working_directory: str | None,
    default_working_directory: str,
) -> Path:
    """Resolve an absolute working directory from a base and optional relative path."""

    configured = configured_working_directory or default_working_directory
    candidate = Path(configured).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_directory / candidate).resolve()


def normalize_breakpoints(
    raw_breakpoints: list[DebugBreakpoint] | list[dict[str, object]] | None,
) -> list[DebugBreakpoint]:
    """Normalize caller breakpoint payloads into debug breakpoint models."""

    if raw_breakpoints is None:
        return []
    normalized: list[DebugBreakpoint] = []
    for entry in raw_breakpoints:
        if isinstance(entry, DebugBreakpoint):
            normalized.append(entry)
            continue
        file_path = entry.get("file_path")
        line_number = entry.get("line_number")
        hit_condition = entry.get("hit_condition")
        if not isinstance(file_path, str) or not isinstance(line_number, int):
            continue
        normalized.append(
            build_breakpoint(
                file_path=file_path,
                line_number=line_number,
                breakpoint_id=str(entry.get("breakpoint_id", "")).strip() or None,
                enabled=bool(entry.get("enabled", True)),
                condition=str(entry.get("condition", "")).strip(),
                hit_condition=int(hit_condition) if isinstance(hit_condition, int) else None,
            )
        )
    return normalized


def build_run_manifest_path(project_root: str | Path, run_id: str) -> Path:
    """Build run manifest path under `<project>/cbcs/runs`."""

    runs_directory = project_runs_dir(str(Path(project_root).expanduser().resolve()))
    return runs_directory / f"{constants.RUN_MANIFEST_FILENAME_PREFIX}{run_id}.json"


def build_run_log_path(project_root: str | Path, run_id: str) -> Path:
    """Build run log path under `<project>/cbcs/logs`."""

    return project_logs_dir(project_root) / f"run_{run_id}.log"


def build_repl_context_root(*, state_root: PathInput | None = None) -> Path:
    """Build global state-backed root for projectless REPL artifacts."""

    return ensure_directory(resolve_global_state_root(state_root) / "repl")


def build_repl_manifest_path(run_id: str, *, state_root: PathInput | None = None) -> Path:
    """Build projectless REPL manifest path under global state."""

    runs_directory = ensure_directory(build_repl_context_root(state_root=state_root) / "runs")
    return runs_directory / f"{constants.RUN_MANIFEST_FILENAME_PREFIX}{run_id}.json"


def build_repl_log_path(run_id: str, *, state_root: PathInput | None = None) -> Path:
    """Build projectless REPL log path under global state."""

    logs_directory = ensure_directory(build_repl_context_root(state_root=state_root) / "logs")
    return logs_directory / f"run_{run_id}.log"
