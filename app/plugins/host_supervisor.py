from __future__ import annotations

from pathlib import Path
import sys
from typing import Callable, Mapping

from app.bootstrap.paths import PathInput, resolve_app_root
from app.core import constants
from app.run.process_supervisor import ProcessEvent, ProcessSupervisor


class PluginHostSupervisor:
    def __init__(
        self,
        *,
        on_event: Callable[[ProcessEvent], None] | None = None,
        runtime_executable: str | None = None,
        host_boot_path: str | None = None,
        state_root: PathInput | None = None,
    ) -> None:
        self._runtime_executable = runtime_executable
        self._host_boot_path = str(
            Path(host_boot_path).expanduser().resolve()
            if host_boot_path
            else resolve_app_root() / "run_plugin_host.py"
        )
        self._state_root = state_root
        self._supervisor = ProcessSupervisor(on_event=on_event)

    @property
    def supervisor(self) -> ProcessSupervisor:
        return self._supervisor

    def start(self, *, env: Mapping[str, str] | None = None) -> int:
        return self._supervisor.start(
            self._build_command(),
            cwd=str(resolve_app_root()),
            env=env,
        )

    def stop(self) -> int | None:
        return self._supervisor.stop()

    def is_running(self) -> bool:
        return self._supervisor.is_running()

    def send_input(self, text: str) -> None:
        self._supervisor.send_input(text)

    def _build_command(self) -> list[str]:
        runtime_executable = self._resolve_runtime_executable()
        state_root = None if self._state_root is None else str(Path(self._state_root).expanduser().resolve())
        if Path(runtime_executable).name in {"AppRun", "freecad", "FreeCAD"}:
            bootstrap_parent = str(Path(self._host_boot_path).parent)
            argv = [self._host_boot_path]
            if state_root is not None:
                argv.extend(["--state-root", state_root])
            payload = (
                "import runpy, sys;"
                f"sys.path.insert(0, {bootstrap_parent!r});"
                f"sys.argv={argv!r};"
                f"runpy.run_path({self._host_boot_path!r}, run_name='__main__')"
            )
            return [runtime_executable, "-c", payload]
        command = [runtime_executable, self._host_boot_path]
        if state_root is not None:
            command.extend(["--state-root", state_root])
        return command

    def _resolve_runtime_executable(self) -> str:
        if self._runtime_executable:
            return str(Path(self._runtime_executable).expanduser().resolve())
        default_runtime = Path(constants.APP_RUN_PATH)
        if default_runtime.exists():
            return str(default_runtime.resolve())
        return sys.executable
