"""Diagnostics orchestration helpers for MainWindow."""

from __future__ import annotations

import logging
from typing import Callable

from app.bootstrap.paths import PathInput
from app.bootstrap.runtime_module_probe import probe_and_cache_runtime_modules


class DiagnosticsOrchestrator:
    """Coordinates realtime lint scheduling and runtime-module probing."""

    def __init__(
        self,
        *,
        diagnostics_enabled: Callable[[], bool],
        diagnostics_realtime: Callable[[], bool],
        set_pending_realtime_file_path: Callable[[str | None], None],
        get_pending_realtime_file_path: Callable[[], str | None],
        start_realtime_timer: Callable[[], None],
        get_active_tab_file_path: Callable[[], str | None],
        render_lint_for_file: Callable[..., None],
        get_open_editor_paths: Callable[[], list[str]],
        render_merged_problems_panel: Callable[[], None],
        set_known_runtime_modules: Callable[[frozenset[str]], None],
        run_background_task: Callable[..., None],
        state_root: Callable[[], PathInput | None],
        logger: logging.Logger,
        show_runtime_probe_warning: Callable[[str], None],
    ) -> None:
        self._diagnostics_enabled = diagnostics_enabled
        self._diagnostics_realtime = diagnostics_realtime
        self._set_pending_realtime_file_path = set_pending_realtime_file_path
        self._get_pending_realtime_file_path = get_pending_realtime_file_path
        self._start_realtime_timer = start_realtime_timer
        self._get_active_tab_file_path = get_active_tab_file_path
        self._render_lint_for_file = render_lint_for_file
        self._get_open_editor_paths = get_open_editor_paths
        self._render_merged_problems_panel = render_merged_problems_panel
        self._set_known_runtime_modules = set_known_runtime_modules
        self._run_background_task = run_background_task
        self._state_root = state_root
        self._logger = logger
        self._show_runtime_probe_warning = show_runtime_probe_warning

    def schedule_realtime_lint(self, file_path: str) -> None:
        if not self._diagnostics_enabled() or not self._diagnostics_realtime():
            return
        if not file_path.lower().endswith(".py"):
            return
        self._set_pending_realtime_file_path(file_path)
        self._start_realtime_timer()

    def run_scheduled_realtime_lint(self) -> None:
        file_path = self._get_pending_realtime_file_path()
        self._set_pending_realtime_file_path(None)
        if file_path is None:
            return
        if self._get_active_tab_file_path() != file_path:
            return
        self._render_lint_for_file(file_path, trigger="realtime")

    def relint_open_python_files(self) -> None:
        for file_path in self._get_open_editor_paths():
            if file_path.lower().endswith(".py"):
                self._render_lint_for_file(file_path, trigger="tab_change")
        self._render_merged_problems_panel()

    def start_runtime_module_probe(self, *, user_initiated: bool = False) -> None:
        state_root = self._state_root()

        def task(_cancel_event) -> object:  # type: ignore[no-untyped-def]
            return probe_and_cache_runtime_modules(state_root=state_root)

        def on_success(modules: object) -> None:
            if not isinstance(modules, frozenset):
                self._logger.warning(
                    "Runtime module probe returned unexpected payload type: %s",
                    type(modules).__name__,
                )
                if user_initiated:
                    self._show_runtime_probe_warning(
                        "Runtime module probe returned an unexpected result type."
                        " See app logs for details."
                    )
                return
            if not modules:
                self._logger.warning(
                    "Runtime module probe returned an empty module set; unresolved-import diagnostics may be incomplete."
                )
                if user_initiated:
                    self._show_runtime_probe_warning(
                        "Runtime module probe returned no modules."
                        " FreeCAD/runtime imports may still show unresolved until probing succeeds."
                    )
                return
            self._set_known_runtime_modules(modules)
            self._logger.info("Runtime module probe completed: %d modules discovered", len(modules))
            self.relint_open_python_files()

        def on_error(exc: Exception) -> None:
            self._logger.warning("Runtime module probe failed: %s", exc)
            if user_initiated:
                self._show_runtime_probe_warning(f"Runtime module probe failed: {exc}")

        self._run_background_task(
            key="runtime_module_probe",
            task=task,
            on_success=on_success,
            on_error=on_error,
        )
