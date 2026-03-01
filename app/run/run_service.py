"""Editor-side run orchestration: manifest generation and process control."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import sys
import uuid
from typing import Callable

from app.bootstrap.paths import ensure_directory, project_logs_dir, project_runs_dir, resolve_app_root
from app.core import constants
from app.core.models import LoadedProject
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


class RunService:
    """Coordinates runner manifest creation and process supervision."""

    def __init__(
        self,
        *,
        on_event: Callable[[ProcessEvent], None] | None = None,
        runtime_executable: str | None = None,
        runner_boot_path: str | None = None,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self._on_event = on_event
        self._runtime_executable = runtime_executable
        self._runner_boot_path = str((Path(runner_boot_path).expanduser().resolve()) if runner_boot_path else resolve_app_root() / "run_runner.py")
        self._now_factory = now_factory or datetime.now
        self._supervisor = ProcessSupervisor(on_event=self._forward_event)
        self._current_session: RunSession | None = None

    @property
    def supervisor(self) -> ProcessSupervisor:
        return self._supervisor

    @property
    def current_session(self) -> RunSession | None:
        return self._current_session

    def start_run(
        self,
        loaded_project: LoadedProject,
        *,
        entry_file: str | None = None,
        mode: str | None = None,
        argv: list[str] | None = None,
    ) -> RunSession:
        """Create run artifacts and launch a supervised runner process."""
        run_id = generate_run_id(now=self._now_factory())
        entry = entry_file or loaded_project.metadata.default_entry
        run_mode = mode or loaded_project.metadata.default_mode
        arguments = [] if argv is None else list(argv)

        resolved_project_root = Path(loaded_project.project_root).expanduser().resolve()
        resolved_working_directory = (resolved_project_root / loaded_project.metadata.working_directory).resolve()
        log_file_path = build_run_log_path(resolved_project_root, run_id)
        manifest_path = build_run_manifest_path(resolved_project_root, run_id)
        ensure_directory(Path(log_file_path).parent)
        ensure_directory(Path(manifest_path).parent)

        timestamp = self._now_factory().isoformat(timespec="seconds")
        manifest = RunManifest(
            manifest_version=constants.RUN_MANIFEST_VERSION,
            run_id=run_id,
            project_root=str(resolved_project_root),
            entry_file=entry,
            working_directory=str(resolved_working_directory),
            mode=run_mode,
            argv=arguments,
            env=dict(loaded_project.metadata.env_overrides),
            safe_mode=loaded_project.metadata.safe_mode,
            log_file=str(log_file_path),
            timestamp=timestamp,
        )
        save_run_manifest(manifest_path, manifest)

        command = self._build_runner_command(str(manifest_path))
        self._supervisor.start(command, cwd=str(resolved_project_root), env=os.environ.copy())
        self._current_session = RunSession(
            run_id=run_id,
            manifest_path=str(manifest_path),
            log_file_path=str(log_file_path),
            project_root=str(resolved_project_root),
            entry_file=entry,
        )
        return self._current_session

    def stop_run(self) -> int | None:
        """Stop active run process if running."""
        return self._supervisor.stop()

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
        if event.event_type == "exit":
            self._current_session = None
        if self._on_event is None:
            return
        self._on_event(event)


def generate_run_id(*, now: datetime | None = None) -> str:
    """Generate a run identifier with timestamp + random suffix."""
    instant = now or datetime.now()
    timestamp = instant.strftime(constants.RUN_ID_TIMESTAMP_FORMAT)
    unique_suffix = uuid.uuid4().hex[:6]
    return f"{timestamp}_{unique_suffix}"


def build_run_log_path(project_root: str | Path, run_id: str) -> Path:
    """Build per-run log path under `<project>/logs`."""
    logs_directory = project_logs_dir(str(Path(project_root).expanduser().resolve()))
    return logs_directory / f"{constants.RUN_LOG_FILENAME_PREFIX}{run_id}{constants.RUN_LOG_FILENAME_SUFFIX}"


def build_run_manifest_path(project_root: str | Path, run_id: str) -> Path:
    """Build run manifest path under `<project>/.cbcs/runs`."""
    runs_directory = project_runs_dir(str(Path(project_root).expanduser().resolve()))
    return runs_directory / f"{constants.RUN_MANIFEST_FILENAME_PREFIX}{run_id}.json"


def resolve_runtime_executable(configured_runtime: str | None) -> str:
    """Resolve runtime executable path used to spawn runner process."""
    if configured_runtime:
        return str(Path(configured_runtime).expanduser().resolve())

    default_runtime = Path(constants.APP_RUN_PATH)
    if default_runtime.exists():
        return str(default_runtime.resolve())
    return sys.executable
