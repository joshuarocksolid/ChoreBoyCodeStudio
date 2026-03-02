"""Editor-side run orchestration: manifest generation and process control."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import sys
import uuid
from typing import Callable

from app.bootstrap.paths import (
    PathInput,
    ensure_directory,
    project_logs_dir,
    project_runs_dir,
    resolve_app_root,
    resolve_global_state_root,
)
from app.core import constants
from app.core.errors import RunLifecycleError
from app.core.models import LoadedProject
from app.debug.debug_event_protocol import parse_debug_output_line
from app.run.process_supervisor import ProcessEvent, ProcessSupervisor
from app.run.run_manifest import RunManifest, save_run_manifest


@dataclass(frozen=True)
class RunSession:
    """Immutable metadata for the currently active run."""

    run_id: str
    manifest_path: str
    log_file_path: str
    project_root: str
    entry_file: str
    mode: str


class RunService:
    """Coordinates runner manifest creation and process supervision."""

    def __init__(
        self,
        *,
        on_event: Callable[[ProcessEvent], None] | None = None,
        runtime_executable: str | None = None,
        runner_boot_path: str | None = None,
        now_factory: Callable[[], datetime] | None = None,
        state_root: PathInput | None = None,
    ) -> None:
        self._on_event = on_event
        self._runtime_executable = runtime_executable
        self._runner_boot_path = str((Path(runner_boot_path).expanduser().resolve()) if runner_boot_path else resolve_app_root() / "run_runner.py")
        self._now_factory = now_factory or datetime.now
        self._state_root = state_root
        self._supervisor = ProcessSupervisor(on_event=self._forward_event)
        self._current_session: RunSession | None = None
        self._is_debug_paused = False

    @property
    def supervisor(self) -> ProcessSupervisor:
        return self._supervisor

    @property
    def current_session(self) -> RunSession | None:
        return self._current_session

    @property
    def is_debug_mode(self) -> bool:
        return self._current_session is not None and self._current_session.mode == constants.RUN_MODE_PYTHON_DEBUG

    @property
    def is_debug_paused(self) -> bool:
        return self._is_debug_paused

    def start_run(
        self,
        loaded_project: LoadedProject | None,
        *,
        entry_file: str | None = None,
        mode: str | None = None,
        argv: list[str] | None = None,
        working_directory: str | None = None,
        env_overrides: dict[str, str] | None = None,
        safe_mode: bool | None = None,
        breakpoints: list[dict[str, int | str]] | None = None,
    ) -> RunSession:
        """Create run artifacts and launch a supervised runner process."""
        run_id = generate_run_id(now=self._now_factory())
        run_mode = mode or (
            loaded_project.metadata.default_mode
            if loaded_project is not None
            else constants.RUN_MODE_PYTHON_REPL
        )

        if loaded_project is None:
            if run_mode != constants.RUN_MODE_PYTHON_REPL:
                raise RunLifecycleError("Open a project before running code.")
            resolved_project_root = build_repl_context_root(state_root=self._state_root)
            entry = entry_file or "__repl__.py"
            arguments = [] if argv is None else list(argv)
            home_directory = Path.home().expanduser().resolve()
            configured_working_directory = working_directory or str(home_directory)
            working_directory_candidate = Path(configured_working_directory).expanduser()
            if working_directory_candidate.is_absolute():
                resolved_working_directory = working_directory_candidate.resolve()
            else:
                resolved_working_directory = (home_directory / working_directory_candidate).resolve()
            manifest_path = build_repl_manifest_path(run_id, state_root=self._state_root)
            log_path = build_repl_log_path(run_id, state_root=self._state_root)
            merged_env_overrides = {} if env_overrides is None else dict(env_overrides)
            effective_safe_mode = False if safe_mode is None else safe_mode
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
            effective_safe_mode = loaded_project.metadata.safe_mode if safe_mode is None else safe_mode
            launch_cwd = str(resolved_project_root)

        normalized_breakpoints = [] if breakpoints is None else list(breakpoints)
        ensure_directory(Path(manifest_path).parent)
        ensure_directory(Path(log_path).parent)

        timestamp = self._now_factory().isoformat(timespec="seconds")
        manifest = RunManifest(
            manifest_version=constants.RUN_MANIFEST_VERSION,
            run_id=run_id,
            project_root=str(resolved_project_root),
            entry_file=entry,
            working_directory=str(resolved_working_directory),
            log_file=str(Path(log_path).resolve()),
            mode=run_mode,
            argv=arguments,
            env=merged_env_overrides,
            safe_mode=effective_safe_mode,
            timestamp=timestamp,
            breakpoints=normalized_breakpoints,
        )
        save_run_manifest(manifest_path, manifest)

        command = self._build_runner_command(str(manifest_path))
        self._supervisor.start(command, cwd=launch_cwd, env=os.environ.copy())
        self._current_session = RunSession(
            run_id=run_id,
            manifest_path=str(manifest_path),
            log_file_path=str(Path(log_path).resolve()),
            project_root=str(resolved_project_root),
            entry_file=entry,
            mode=run_mode,
        )
        self._is_debug_paused = False
        return self._current_session

    def stop_run(self) -> int | None:
        """Stop active run process if running."""
        return self._supervisor.stop()

    def pause_run(self) -> bool:
        """Interrupt active run process to enter paused/debug interaction."""
        return self._supervisor.pause()

    def send_input(self, text: str) -> None:
        """Send stdin input to active runner process."""
        self._supervisor.send_input(text)

    def _build_runner_command(self, manifest_path: str) -> list[str]:
        runtime_executable = resolve_runtime_executable(self._runtime_executable)
        runtime_path = Path(runtime_executable)
        if runtime_path.name == "AppRun" or runtime_path.suffix == ".AppImage":
            runner_parent = str(Path(self._runner_boot_path).resolve().parent)
            payload = (
                "import runpy, sys;"
                f"sys.path.insert(0, {runner_parent!r});"
                f"sys.argv={[self._runner_boot_path, '--manifest', manifest_path]!r};"
                f"runpy.run_path({self._runner_boot_path!r}, run_name='__main__')"
            )
            return [runtime_executable, "-c", payload]
        return [runtime_executable, self._runner_boot_path, "--manifest", manifest_path]

    def _forward_event(self, event: ProcessEvent) -> None:
        if event.event_type == "output" and event.text:
            parsed_event = parse_debug_output_line(event.text)
            if parsed_event is not None:
                if parsed_event.event_type == "paused":
                    self._is_debug_paused = True
                elif parsed_event.event_type == "running":
                    self._is_debug_paused = False
        if event.event_type == "exit":
            self._current_session = None
            self._is_debug_paused = False
        if self._on_event is None:
            return
        self._on_event(event)


def generate_run_id(*, now: datetime | None = None) -> str:
    """Generate a run identifier with timestamp + random suffix."""
    instant = now or datetime.now()
    timestamp = instant.strftime(constants.RUN_ID_TIMESTAMP_FORMAT)
    unique_suffix = uuid.uuid4().hex[:6]
    return f"{timestamp}_{unique_suffix}"


def build_run_manifest_path(project_root: str | Path, run_id: str) -> Path:
    """Build run manifest path under `<project>/.cbcs/runs`."""
    runs_directory = project_runs_dir(str(Path(project_root).expanduser().resolve()))
    return runs_directory / f"{constants.RUN_MANIFEST_FILENAME_PREFIX}{run_id}.json"


def build_run_log_path(project_root: str | Path, run_id: str) -> Path:
    """Build run log path under `<project>/.cbcs/logs`."""
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


def resolve_runtime_executable(configured_runtime: str | None) -> str:
    """Resolve runtime executable path used to spawn runner process."""
    if configured_runtime:
        return str(Path(configured_runtime).expanduser().resolve())

    default_runtime = Path(constants.APP_RUN_PATH)
    if default_runtime.exists():
        return str(default_runtime.resolve())
    return sys.executable
