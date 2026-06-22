"""Editor-side run orchestration: manifest generation and process control."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import secrets
import socket
import uuid
from typing import Callable, Mapping

from app.bootstrap.paths import PathInput, ensure_directory, resolve_app_root
from app.core import constants
from app.core.errors import RunLifecycleError
from app.core.models import LoadedProject
from app.debug.debug_models import DebugBreakpoint, DebugExceptionPolicy, DebugSourceMap, DebugTransportConfig
from app.debug.debug_transport import DebugTransportServer
from app.run.launch_context import (
    LaunchContext,
    build_repl_context_root,
    build_repl_log_path,
    build_repl_manifest_path,
    build_run_log_path,
    build_run_manifest_path,
    plan_launch,
)
from app.run.process_supervisor import ProcessEvent, ProcessSupervisor
from app.run.run_manifest import ReplControlConfig, RunManifest, save_run_manifest
from app.run.runner_command_builder import build_runner_command
from app.run.runtime_launch import resolve_runtime_executable
from app.runner.repl_protocol import REPL_CONTROL_PROTOCOL


def build_repl_sidecar_launch(
    *,
    run_id: str,
    now: datetime,
    state_root: PathInput | None = None,
) -> ReplSidecarLaunch:
    """Build manifest artifacts for a REPL sidecar without starting a process."""
    context_root = build_repl_context_root(state_root=state_root)
    manifest_path = build_repl_manifest_path(run_id, state_root=state_root)
    log_path = build_repl_log_path(run_id, state_root=state_root)
    home_dir = Path.home().expanduser().resolve()
    repl_control = _build_repl_control_config(run_id)
    manifest = RunManifest(
        manifest_version=constants.RUN_MANIFEST_VERSION,
        run_id=run_id,
        project_root=str(context_root),
        entry_file="__repl__.py",
        working_directory=str(home_dir),
        log_file=str(log_path.resolve()),
        mode=constants.RUN_MODE_PYTHON_REPL,
        argv=(),
        env=(),
        timestamp=now.isoformat(timespec="seconds"),
        breakpoints=(),
        repl_control=repl_control,
    )
    ensure_directory(Path(manifest_path).parent)
    ensure_directory(Path(log_path).parent)
    save_run_manifest(str(manifest_path), manifest)
    return ReplSidecarLaunch(
        run_id=run_id,
        manifest_path=str(manifest_path),
        log_path=str(log_path.resolve()),
        launch_cwd=str(home_dir),
        repl_control=repl_control,
    )


__all__ = [
    "RunService",
    "RunSession",
    "ReplSidecarLaunch",
    "build_repl_sidecar_launch",
    "build_repl_context_root",
    "build_repl_log_path",
    "build_repl_manifest_path",
    "build_run_log_path",
    "build_run_manifest_path",
    "generate_run_id",
]


@dataclass(frozen=True)
class RunSession:
    """Immutable metadata for the currently active run."""

    run_id: str
    manifest_path: str
    log_file_path: str
    project_root: str
    entry_file: str
    mode: str


@dataclass(frozen=True)
class ReplSidecarLaunch:
    """Artifacts for one REPL sidecar subprocess launch."""

    run_id: str
    manifest_path: str
    log_path: str
    launch_cwd: str
    repl_control: ReplControlConfig


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
        self._runtime_executable = runtime_executable
        self._runner_boot_path = str(
            Path(runner_boot_path).expanduser().resolve()
            if runner_boot_path
            else resolve_app_root() / "run_runner.py"
        )
        self._supervisor = ProcessSupervisor(on_event=self._forward_event)
        self._current_session: RunSession | None = None
        self._debug_transport_server: DebugTransportServer | None = None

    @property
    def supervisor(self) -> ProcessSupervisor:
        return self._supervisor

    @property
    def current_session(self) -> RunSession | None:
        return self._current_session

    @property
    def is_debug_mode(self) -> bool:
        return self._current_session is not None and self._current_session.mode == constants.RUN_MODE_PYTHON_DEBUG

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
        self._assert_idle()
        launch = plan_launch(
            run_id=generate_run_id(now=self._now_factory()),
            loaded_project=loaded_project,
            entry_file=entry_file,
            mode=mode,
            argv=argv,
            working_directory=working_directory,
            env_overrides=env_overrides,
            breakpoints=breakpoints,
            debug_exception_policy=debug_exception_policy,
            source_maps=source_maps,
            state_root=self._state_root,
        )
        debug_transport = self._start_debug_transport_if_needed(launch.mode)
        manifest = self._build_run_manifest(launch, debug_transport=debug_transport)
        self._persist_run_manifest(launch, manifest)
        try:
            self._start_manifest(str(launch.manifest_path), cwd=launch.launch_cwd)
        except (RunLifecycleError, OSError, RuntimeError):
            self._close_debug_transport_server()
            self._remove_manifest_file(launch.manifest_path)
            raise
        self._current_session = RunSession(
            run_id=launch.run_id,
            manifest_path=str(launch.manifest_path),
            log_file_path=str(launch.log_path.resolve()),
            project_root=launch.project_root,
            entry_file=launch.entry_file,
            mode=launch.mode,
        )
        return self._current_session

    def plan_repl_sidecar(self) -> ReplSidecarLaunch:
        """Build manifest artifacts for a REPL sidecar without starting a process."""
        return build_repl_sidecar_launch(
            run_id=generate_run_id(now=self._now_factory()),
            now=self._now_factory(),
            state_root=self._state_root,
        )

    def start_repl_sidecar(self, *, supervisor: ProcessSupervisor | None = None) -> ReplSidecarLaunch:
        """Build REPL manifest artifacts and launch the sidecar subprocess."""
        launch = self.plan_repl_sidecar()
        target_supervisor = supervisor or self._supervisor
        command = build_runner_command(
            runtime_executable=self._resolve_runtime_executable(),
            runner_boot_path=self._runner_boot_path,
            manifest_path=launch.manifest_path,
        )
        target_supervisor.start(command, cwd=launch.launch_cwd, env=os.environ.copy())
        return launch

    def stop_run(self) -> int | None:
        """Stop active run process if running."""
        return self._supervisor.stop()

    def pause_run(self) -> bool:
        """Interrupt active run process to enter paused/debug interaction."""
        if self.is_debug_mode:
            self.send_debug_command("pause")
            return True
        return self._supervisor.pause()

    def send_input(self, text: str) -> None:
        """Send stdin input to active runner process."""
        self._supervisor.send_input(text)

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

    def _start_manifest(
        self,
        manifest_path: str,
        *,
        cwd: str,
        env: Mapping[str, str] | None = None,
    ) -> int:
        command = build_runner_command(
            runtime_executable=self._resolve_runtime_executable(),
            runner_boot_path=self._runner_boot_path,
            manifest_path=manifest_path,
        )
        launch_env = os.environ.copy() if env is None else dict(env)
        return self._supervisor.start(command, cwd=cwd, env=launch_env)

    def _resolve_runtime_executable(self) -> str:
        return resolve_runtime_executable(self._runtime_executable)

    def _start_debug_transport_if_needed(self, run_mode: str) -> DebugTransportConfig | None:
        if run_mode != constants.RUN_MODE_PYTHON_DEBUG:
            return None
        self._close_debug_transport_server()
        self._debug_transport_server = DebugTransportServer(
            on_message=self._forward_debug_message,
            on_error=self._forward_debug_transport_error,
        )
        return self._debug_transport_server.start()

    def _build_run_manifest(
        self,
        launch: LaunchContext,
        *,
        debug_transport: DebugTransportConfig | None,
    ) -> RunManifest:
        repl_control = (
            _build_repl_control_config(launch.run_id)
            if launch.mode == constants.RUN_MODE_PYTHON_REPL
            else None
        )
        return RunManifest(
            manifest_version=constants.RUN_MANIFEST_VERSION,
            run_id=launch.run_id,
            project_root=launch.project_root,
            entry_file=launch.entry_file,
            working_directory=launch.working_directory,
            log_file=str(launch.log_path.resolve()),
            mode=launch.mode,
            argv=tuple(launch.argv),
            env=tuple(sorted(launch.env.items())),
            timestamp=self._now_factory().isoformat(timespec="seconds"),
            breakpoints=tuple(launch.breakpoints),
            debug_transport=debug_transport,
            repl_control=repl_control,
            debug_exception_policy=launch.debug_exception_policy,
            source_maps=tuple(launch.source_maps),
        )

    def _persist_run_manifest(self, launch: LaunchContext, manifest: RunManifest) -> None:
        ensure_directory(launch.manifest_path.parent)
        ensure_directory(launch.log_path.parent)
        save_run_manifest(str(launch.manifest_path), manifest)

    @staticmethod
    def _remove_manifest_file(manifest_path: Path) -> None:
        manifest_file = Path(manifest_path)
        if manifest_file.exists():
            try:
                manifest_file.unlink()
            except OSError:
                pass

    def _forward_event(self, event: ProcessEvent) -> None:
        if event.event_type == "exit":
            self._current_session = None
            self._close_debug_transport_server()
        if self._on_event is None:
            return
        self._on_event(event)

    def _forward_debug_message(self, message: dict[str, object]) -> None:
        if self._on_event is None:
            return
        self._on_event(ProcessEvent(event_type="debug", payload=dict(message)))

    def _forward_debug_transport_error(self, message: str) -> None:
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
        self._close_debug_transport_server()

    def _close_debug_transport_server(self) -> None:
        transport_server = self._debug_transport_server
        self._debug_transport_server = None
        if transport_server is not None:
            transport_server.close()

    def _assert_idle(self) -> None:
        if self._supervisor.is_running():
            raise RunLifecycleError("A run session is already active.")


def generate_run_id(*, now: datetime | None = None) -> str:
    """Generate a run identifier with timestamp + random suffix."""
    instant = now or datetime.now()
    timestamp = instant.strftime(constants.RUN_ID_TIMESTAMP_FORMAT)
    unique_suffix = uuid.uuid4().hex[:6]
    return f"{timestamp}_{unique_suffix}"


def _build_repl_control_config(run_id: str) -> ReplControlConfig:
    return ReplControlConfig(
        protocol=REPL_CONTROL_PROTOCOL,
        host="127.0.0.1",
        port=_allocate_loopback_port(),
        session_token=f"repl_{run_id}_{secrets.token_hex(8)}",
        connect_timeout_ms=800,
    )


def _allocate_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
