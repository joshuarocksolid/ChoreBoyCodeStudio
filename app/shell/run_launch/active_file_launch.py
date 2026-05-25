"""Active-file and transient entry launch helpers."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Callable, Protocol

from app.core import constants
from app.debug.debug_models import DebugBreakpoint, DebugExceptionPolicy, DebugSourceMap


class ActiveFileLaunchHost(Protocol):
    def editor_manager(self) -> Any:
        ...

    def debug_control_workflow(self) -> Any:
        ...

    def debug_exception_policy(self) -> DebugExceptionPolicy:
        ...

    def run_debug_presenter(self) -> Any:
        ...

    def show_warning(self, title: str, message: str) -> None:
        ...

    def set_active_transient_entry_file_path(self, path: str | None) -> None:
        ...

    def logger(self) -> Any:
        ...


class ActiveFileLaunchWorkflow:
    """Launch run/debug sessions for the active editor file."""

    def __init__(self, host: ActiveFileLaunchHost) -> None:
        self._host = host

    def start_active_file_session(
        self,
        *,
        mode: str,
        record_debug_target: Callable[[str], None],
        start_session: Callable[..., bool],
    ) -> bool:
        active_tab = self._host.editor_manager().active_tab()
        if active_tab is None:
            self._host.show_warning("Run unavailable", "Open a file tab before running.")
            return False
        entry_path = Path(active_tab.file_path).expanduser().resolve()
        active_file_path = str(entry_path)
        if entry_path.suffix.lower() != ".py":
            self._host.show_warning("Run unavailable", "Active file must be a Python file.")
            return False
        transient_entry_file: str | None = None
        entry_file = active_file_path
        skip_save = False
        source_maps: list[DebugSourceMap] | None = None
        if active_tab.is_dirty:
            transient_entry_file = self.write_transient_entry_file(
                source_file_path=active_tab.file_path,
                source_content=active_tab.current_content,
            )
            entry_file = transient_entry_file
            skip_save = True
            source_maps = [DebugSourceMap(runtime_path=transient_entry_file, source_path=active_file_path)]
        breakpoints: list[DebugBreakpoint] | None = None
        if mode == constants.RUN_MODE_PYTHON_DEBUG:
            breakpoints = self._host.debug_control_workflow().build_debug_breakpoints_for_launch(
                active_file_path=active_file_path,
                remapped_active_path=transient_entry_file,
            )
        started = start_session(
            mode=mode,
            entry_file=entry_file,
            breakpoints=breakpoints,
            debug_exception_policy=self._host.debug_exception_policy()
            if mode == constants.RUN_MODE_PYTHON_DEBUG
            else None,
            source_maps=source_maps,
            skip_save=skip_save,
        )
        if started and mode == constants.RUN_MODE_PYTHON_DEBUG:
            record_debug_target(active_file_path)
        if transient_entry_file is not None:
            if started:
                self._host.set_active_transient_entry_file_path(transient_entry_file)
            else:
                self.delete_transient_entry_file(transient_entry_file)
        return started

    @staticmethod
    def write_transient_entry_file(*, source_file_path: str, source_content: str) -> str:
        source_name = Path(source_file_path).name
        safe_stem = Path(source_name).stem or "buffer"
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".py",
            prefix=f"cbcs_{safe_stem}_",
            delete=False,
        ) as handle:
            handle.write(source_content)
            return str(Path(handle.name).resolve())

    def delete_transient_entry_file(self, path: str) -> None:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            self._host.logger().warning("Failed to delete transient run file: %s", path)
