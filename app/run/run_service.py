"""Editor-side run orchestration: manifest generation and process control."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import uuid
from typing import Callable

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
from app.debug.debug_transport import DebugTransportServer
from app.run.host_process_manager import HostProcessManager
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
        self._now_factory = now_factory or datetime.now
        self._state_root = state_root
        self._host_manager = HostProcessManager(
            on_event=self._forward_event,
            runtime_executable=runtime_executable,
            runner_boot_path=runner_boot_path,
        )
        self._current_session: RunSession | None = None
        self._is_debug_paused = False
        self._debug_transport_server: DebugTransportServer | None = None

    @property
    def supervisor(self) -> ProcessSupervisor:
        return self._host_manager.supervisor

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
        breakpoints: list[DebugBreakpoint] | list[dict[str, object]] | None = None,
        debug_exception_policy: DebugExceptionPolicy | None = None,
        source_maps: list[DebugSourceMap] | None = None,
    ) -> RunSession:
        """Create run artifacts and launch a supervised runner process."""
        run_id = generate_run_id(now=self._now_factory())
        run_mode = mode or (
            constants.RUN_MODE_PYTHON_SCRIPT
            if loaded_project is not None
            else constants.RUN_MODE_PYTHON_REPL
        )

        if loaded_project is None:
            if run_mode == constants.RUN_MODE_PYTHON_REPL:
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
            else:
                if entry_file is None:
                    raise RunLifecycleError("Provide a file entry before running without a project.")
                resolved_entry = Path(entry_file).expanduser().resolve()
                if not resolved_entry.exists() or not resolved_entry.is_file():
                    raise RunLifecycleError(f"Entry file not found: {resolved_entry}")
                resolved_project_root = resolved_entry.parent
                entry = str(resolved_entry)
                arguments = [] if argv is None else list(argv)
                configured_working_directory = working_directory or str(resolved_entry.parent)
                working_directory_candidate = Path(configured_working_directory).expanduser()
                if working_directory_candidate.is_absolute():
                    resolved_working_directory = working_directory_candidate.resolve()
                else:
                    resolved_working_directory = (resolved_entry.parent / working_directory_candidate).resolve()
            manifest_path = build_repl_manifest_path(run_id, state_root=self._state_root)
            log_path = build_repl_log_path(run_id, state_root=self._state_root)
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

        normalized_breakpoints = self._normalize_breakpoints(breakpoints)
        normalized_exception_policy = debug_exception_policy or DebugExceptionPolicy()
        normalized_source_maps = [] if source_maps is None else list(source_maps)
        debug_transport = None
        if run_mode == constants.RUN_MODE_PYTHON_DEBUG:
            self._close_debug_transport_server()
            self._debug_transport_server = DebugTransportServer(
                on_message=self._forward_debug_message,
                on_error=self._forward_debug_transport_error,
            )
            debug_transport = self._debug_transport_server.start()
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
            timestamp=timestamp,
            breakpoints=normalized_breakpoints,
            debug_transport=debug_transport,
            debug_exception_policy=normalized_exception_policy,
            source_maps=normalized_source_maps,
        )
        save_run_manifest(manifest_path, manifest)

        try:
            self._host_manager.start_manifest(
                manifest_path=str(manifest_path),
                cwd=launch_cwd,
            )
        except Exception:
            self._close_debug_transport_server()
            raise
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
        return self._host_manager.stop()

    def pause_run(self) -> bool:
        """Interrupt active run process to enter paused/debug interaction."""
        if self.is_debug_mode:
            self.send_debug_command("pause")
            return True
        return self._host_manager.pause()

    def send_input(self, text: str) -> None:
        """Send stdin input to active runner process."""
        self._host_manager.send_input(text)

    def send_debug_command(self, command_name: str, arguments: dict[str, object] | None = None) -> str:
        """Send one structured debug command over the dedicated transport."""

        if not self.is_debug_mode:
            raise RunLifecycleError("No active debug session is running.")
        if self._debug_transport_server is None:
            raise RunLifecycleError("Debug transport is not available.")
        try:
            return self._debug_transport_server.send_command(command_name, arguments)
        except Exception as exc:
            raise RunLifecycleError("Failed to send debug command: %s" % (exc,)) from exc

    def _forward_event(self, event: ProcessEvent) -> None:
        if event.event_type == "exit":
            self._current_session = None
            self._is_debug_paused = False
            self._close_debug_transport_server()
        if self._on_event is None:
            return
        self._on_event(event)

    def _forward_debug_message(self, message: dict[str, object]) -> None:
        kind = str(message.get("kind", "")).strip()
        if kind == "event":
            event_name = str(message.get("event", "")).strip()
            if event_name == "stopped":
                self._is_debug_paused = True
            elif event_name in {"continued", "session_ready", "session_ended"}:
                self._is_debug_paused = False
        if self._on_event is None:
            return
        self._on_event(ProcessEvent(event_type="debug", payload=dict(message)))

    def _forward_debug_transport_error(self, message: str) -> None:
        self._is_debug_paused = False
        if self._on_event is not None:
            self._on_event(
                ProcessEvent(
                    event_type="debug",
                    payload={
                        "kind": "event",
                        "event": "session_ended",
                        "body": {"message": str(message)},
                    },
                )
            )
            self._on_event(ProcessEvent(event_type="output", stream="stderr", text="[debug] %s\n" % (message,)))

    def _close_debug_transport_server(self) -> None:
        transport_server = self._debug_transport_server
        self._debug_transport_server = None
        if transport_server is not None:
            transport_server.close()

    @staticmethod
    def _normalize_breakpoints(
        raw_breakpoints: list[DebugBreakpoint] | list[dict[str, object]] | None,
    ) -> list[DebugBreakpoint]:
        if raw_breakpoints is None:
            return []
        normalized: list[DebugBreakpoint] = []
        for entry in raw_breakpoints:
            if isinstance(entry, DebugBreakpoint):
                normalized.append(entry)
                continue
            file_path = entry.get("file_path")
            line_number = entry.get("line_number")
            if not isinstance(file_path, str) or not isinstance(line_number, int):
                continue
            normalized.append(
                build_breakpoint(
                    file_path=file_path,
                    line_number=line_number,
                    breakpoint_id=str(entry.get("breakpoint_id", "")).strip() or None,
                    enabled=bool(entry.get("enabled", True)),
                    condition=str(entry.get("condition", "")).strip(),
                    hit_condition=int(entry["hit_condition"]) if isinstance(entry.get("hit_condition"), int) else None,
                )
            )
        return normalized


def generate_run_id(*, now: datetime | None = None) -> str:
    """Generate a run identifier with timestamp + random suffix."""
    instant = now or datetime.now()
    timestamp = instant.strftime(constants.RUN_ID_TIMESTAMP_FORMAT)
    unique_suffix = uuid.uuid4().hex[:6]
    return f"{timestamp}_{unique_suffix}"


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
