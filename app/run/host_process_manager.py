from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Callable, Mapping

from app.bootstrap.paths import resolve_app_root
from app.core import constants
from app.run.process_supervisor import ProcessEvent, ProcessSupervisor
from app.run.runner_command_builder import build_runner_command


class HostProcessManager:
    def __init__(
        self,
        *,
        on_event: Callable[[ProcessEvent], None] | None = None,
        runtime_executable: str | None = None,
        runner_boot_path: str | None = None,
    ) -> None:
        self._runtime_executable = runtime_executable
        self._runner_boot_path = str(
            Path(runner_boot_path).expanduser().resolve()
            if runner_boot_path
            else resolve_app_root() / "run_runner.py"
        )
        self._supervisor = ProcessSupervisor(on_event=on_event)

    @property
    def supervisor(self) -> ProcessSupervisor:
        return self._supervisor

    def is_running(self) -> bool:
        return self._supervisor.is_running()

    def start_manifest(
        self,
        *,
        manifest_path: str,
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

    def stop(self) -> int | None:
        return self._supervisor.stop()

    def pause(self) -> bool:
        return self._supervisor.pause()

    def send_input(self, text: str) -> None:
        self._supervisor.send_input(text)

    def _resolve_runtime_executable(self) -> str:
        if self._runtime_executable:
            return str(Path(self._runtime_executable).expanduser().resolve())
        default_runtime = Path(constants.APP_RUN_PATH)
        if default_runtime.exists():
            return str(default_runtime.resolve())
        return sys.executable
