"""Dedicated REPL session manager independent of the script run lifecycle.

Owns a private ``ProcessSupervisor`` so the Python Console can run
simultaneously with script/debug sessions.  Supports auto-start on
app launch and auto-restart when the REPL process exits unexpectedly.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.bootstrap.paths import PathInput, ensure_directory
from app.core import constants
from app.run.host_process_manager import HostProcessManager
from app.run.process_supervisor import ProcessEvent
from app.run.run_manifest import RunManifest, save_run_manifest
from app.run.run_service import (
    build_repl_context_root,
    build_repl_log_path,
    build_repl_manifest_path,
    generate_run_id,
)

_logger = logging.getLogger(__name__)

_MAX_RAPID_RESTARTS = 5
_RAPID_RESTART_WINDOW_SECONDS = 10.0
_AUTO_RESTART_DELAY_SECONDS = 0.5


class ReplSessionManager:
    """Manages an always-on Python REPL subprocess."""

    def __init__(
        self,
        *,
        on_output: Callable[[str, str], None] | None = None,
        on_session_ended: Callable[[int | None, bool], None] | None = None,
        on_session_started: Callable[[], None] | None = None,
        runtime_executable: str | None = None,
        runner_boot_path: str | None = None,
        state_root: PathInput | None = None,
    ) -> None:
        self._on_output = on_output
        self._on_session_ended = on_session_ended
        self._on_session_started = on_session_started
        self._host_manager = HostProcessManager(
            on_event=self._handle_event,
            runtime_executable=runtime_executable,
            runner_boot_path=runner_boot_path,
        )
        self._state_root = state_root
        self._auto_restart = True
        self._shutting_down = False
        self._recent_exit_times: list[float] = []

    @property
    def is_running(self) -> bool:
        return self._host_manager.is_running()

    def start(self) -> None:
        """Launch the REPL subprocess (no-op if already running)."""
        if self._host_manager.is_running():
            return
        self._shutting_down = False
        self._auto_restart = True
        try:
            self._launch()
        except Exception:
            _logger.exception("Failed to start REPL session")
            return
        if self._on_session_started is not None:
            self._on_session_started()

    def stop(self) -> None:
        """Stop the REPL subprocess and suppress auto-restart."""
        self._auto_restart = False
        self._shutting_down = True
        if self._host_manager.is_running():
            self._host_manager.stop()

    def restart(self) -> None:
        """Stop then re-launch the REPL subprocess."""
        self.stop()
        self._shutting_down = False
        self._auto_restart = True
        self._recent_exit_times.clear()
        try:
            self._launch()
        except Exception:
            _logger.exception("Failed to restart REPL session")
            return
        if self._on_session_started is not None:
            self._on_session_started()

    def send_input(self, text: str) -> None:
        """Send *text* to the REPL subprocess stdin."""
        if not text.endswith("\n"):
            text += "\n"
        self._host_manager.send_input(text)

    def shutdown(self) -> None:
        """Permanent shutdown (call during app close)."""
        self._auto_restart = False
        self._shutting_down = True
        if self._host_manager.is_running():
            self._host_manager.stop()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _launch(self) -> None:
        run_id = generate_run_id(now=datetime.now())
        context_root = build_repl_context_root(state_root=self._state_root)
        manifest_path = build_repl_manifest_path(run_id, state_root=self._state_root)
        log_path = build_repl_log_path(run_id, state_root=self._state_root)

        home_dir = Path.home().expanduser().resolve()
        ensure_directory(Path(manifest_path).parent)
        ensure_directory(Path(log_path).parent)

        manifest = RunManifest(
            manifest_version=constants.RUN_MANIFEST_VERSION,
            run_id=run_id,
            project_root=str(context_root),
            entry_file="__repl__.py",
            working_directory=str(home_dir),
            log_file=str(log_path.resolve()),
            mode=constants.RUN_MODE_PYTHON_REPL,
            argv=[],
            env={},
            timestamp=datetime.now().isoformat(timespec="seconds"),
            breakpoints=[],
        )
        save_run_manifest(str(manifest_path), manifest)

        self._host_manager.start_manifest(
            manifest_path=manifest_path,
            cwd=str(home_dir),
        )

    def _handle_event(self, event: ProcessEvent) -> None:
        if event.event_type == "output" and event.text:
            stream = event.stream or "stdout"
            if self._on_output is not None:
                self._on_output(event.text, stream)
            return

        if event.event_type == "exit":
            return_code = event.return_code
            terminated_by_user = event.terminated_by_user
            if self._on_session_ended is not None:
                self._on_session_ended(return_code, terminated_by_user)
            self._maybe_auto_restart(terminated_by_user)

    def _maybe_auto_restart(self, terminated_by_user: bool) -> None:
        if not self._auto_restart or self._shutting_down or terminated_by_user:
            return
        now = datetime.now().timestamp()
        self._recent_exit_times = [
            t for t in self._recent_exit_times
            if now - t < _RAPID_RESTART_WINDOW_SECONDS
        ]
        self._recent_exit_times.append(now)
        if len(self._recent_exit_times) >= _MAX_RAPID_RESTARTS:
            _logger.warning("REPL crashed %d times in %.0fs — suppressing auto-restart",
                            _MAX_RAPID_RESTARTS, _RAPID_RESTART_WINDOW_SECONDS)
            return
        timer = threading.Timer(_AUTO_RESTART_DELAY_SECONDS, self._do_auto_restart)
        timer.daemon = True
        timer.start()

    def _do_auto_restart(self) -> None:
        if self._shutting_down or not self._auto_restart:
            return
        if self._host_manager.is_running():
            return
        _logger.info("Auto-restarting REPL session")
        try:
            self._launch()
        except Exception:
            _logger.exception("Auto-restart of REPL failed")
            return
        if self._on_session_started is not None:
            self._on_session_started()
