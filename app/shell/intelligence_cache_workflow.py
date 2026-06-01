"""Symbol cache rebuild and background indexing for the shell."""

from __future__ import annotations

import time
from typing import Any, Callable, Protocol

from PySide2.QtWidgets import QMessageBox

from app.intelligence.cache_controls import rebuild_symbol_cache
from app.intelligence.symbol_index import SymbolIndexWorker
from app.project.file_excludes import compute_effective_excludes


class IntelligenceCacheHost(Protocol):
    def dialog_parent(self) -> Any:
        ...

    def intelligence_cache_enabled(self) -> bool:
        ...

    def intelligence_metrics_logging_enabled(self) -> bool:
        ...

    def logger(self) -> Any:
        ...

    def symbol_cache_db_path(self) -> str:
        ...

    def loaded_project(self) -> Any | None:
        ...

    def load_effective_exclude_patterns(self, project_root: str | None) -> list[str]:
        ...

    def active_symbol_index_worker(self) -> SymbolIndexWorker | None:
        ...

    def set_active_symbol_index_worker(self, worker: SymbolIndexWorker | None) -> None:
        ...

    def symbol_index_generation(self) -> int:
        ...

    def bump_symbol_index_generation(self) -> int:
        ...

    def dispatch_to_main_thread(self, callback: Callable[[], None]) -> None:
        ...


class IntelligenceCacheWorkflow:
    """Owns symbol index worker lifecycle and cache rebuild."""

    def __init__(self, host: IntelligenceCacheHost) -> None:
        self._host = host

    def start_symbol_indexing(self, project_root: str, *, exclude_patterns: list[str] | None = None) -> None:
        if not self._host.intelligence_cache_enabled():
            return
        active_worker = self._host.active_symbol_index_worker()
        if active_worker is not None and active_worker.is_running():
            active_worker.cancel()
        generation = self._host.bump_symbol_index_generation()
        started_at = time.perf_counter()
        effective_excludes = exclude_patterns
        loaded_project = self._host.loaded_project()
        if effective_excludes is None and loaded_project is not None:
            effective_excludes = compute_effective_excludes(
                self._host.load_effective_exclude_patterns(loaded_project.project_root),
                loaded_project.metadata.exclude_patterns,
            )
        worker = SymbolIndexWorker(
            project_root=project_root,
            cache_db_path=self._host.symbol_cache_db_path(),
            exclude_patterns=effective_excludes or (),
            on_done=lambda count: self._handle_symbol_index_done(project_root, count, started_at, generation),
            on_error=lambda message: self._handle_symbol_index_error(project_root, message, generation),
            should_commit=lambda: generation == self._host.symbol_index_generation(),
        )
        self._host.set_active_symbol_index_worker(worker)
        worker.start()

    def rebuild_intelligence_cache(self) -> bool | None:
        active_worker = self._host.active_symbol_index_worker()
        if active_worker is not None and active_worker.is_running():
            active_worker.cancel()
        self._host.bump_symbol_index_generation()
        try:
            deleted = rebuild_symbol_cache(self._host.symbol_cache_db_path())
        except OSError as exc:
            QMessageBox.warning(
                self._host.dialog_parent(),
                "Rebuild Intelligence Cache",
                f"Unable to rebuild cache: {exc}",
            )
            return None
        return deleted

    def handle_rebuild_intelligence_cache_action(self) -> None:
        deleted = self.rebuild_intelligence_cache()
        if deleted is None:
            return
        loaded_project = self._host.loaded_project()
        if loaded_project is not None and self._host.intelligence_cache_enabled():
            self.start_symbol_indexing(loaded_project.project_root)
        if deleted:
            QMessageBox.information(
                self._host.dialog_parent(),
                "Rebuild Intelligence Cache",
                "Cache rebuilt successfully.",
            )
            return
        QMessageBox.information(
            self._host.dialog_parent(),
            "Rebuild Intelligence Cache",
            "No existing cache found. Reindex initialized.",
        )

    def _handle_symbol_index_done(
        self,
        project_root: str,
        symbol_count: int,
        started_at: float,
        generation: int,
    ) -> None:
        if generation != self._host.symbol_index_generation():
            return
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        if self._host.intelligence_metrics_logging_enabled():
            if elapsed_ms > 2500.0:
                self._host.logger().warning(
                    "Symbol index latency warning: root=%s symbols=%s elapsed_ms=%.2f",
                    project_root,
                    symbol_count,
                    elapsed_ms,
                )
            else:
                self._host.logger().info(
                    "Symbol index telemetry: root=%s symbols=%s elapsed_ms=%.2f",
                    project_root,
                    symbol_count,
                    elapsed_ms,
                )
        self._host.dispatch_to_main_thread(lambda: self._host.set_active_symbol_index_worker(None))

    def _handle_symbol_index_error(self, project_root: str, message: str, generation: int) -> None:
        if generation != self._host.symbol_index_generation():
            return
        self._host.logger().warning("Symbol index failed for %s: %s", project_root, message)
        self._host.dispatch_to_main_thread(lambda: self._host.set_active_symbol_index_worker(None))


class MainWindowIntelligenceCacheHost:
    """Host ports for ``IntelligenceCacheWorkflow`` backed by a MainWindow instance."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def dialog_parent(self) -> Any:
        return self._window

    def intelligence_cache_enabled(self) -> bool:
        return self._window._intelligence_runtime_settings.cache_enabled

    def intelligence_metrics_logging_enabled(self) -> bool:
        return self._window._intelligence_runtime_settings.metrics_logging_enabled

    def logger(self) -> Any:
        return self._window._logger

    def symbol_cache_db_path(self) -> str:
        return self._window._symbol_cache_db_path

    def loaded_project(self) -> Any | None:
        return self._window._loaded_project

    def load_effective_exclude_patterns(self, project_root: str | None) -> list[str]:
        return self._window._file_project_commands_workflow.load_effective_exclude_patterns(project_root)

    def active_symbol_index_worker(self) -> SymbolIndexWorker | None:
        return self._window._active_symbol_index_worker

    def set_active_symbol_index_worker(self, worker: SymbolIndexWorker | None) -> None:
        self._window._active_symbol_index_worker = worker

    def symbol_index_generation(self) -> int:
        return self._window._symbol_index_generation

    def bump_symbol_index_generation(self) -> int:
        self._window._symbol_index_generation += 1
        return self._window._symbol_index_generation

    def dispatch_to_main_thread(self, callback: Callable[[], None]) -> None:
        self._window._dispatch_to_main_thread(callback)


def build_intelligence_cache_workflow(window: Any) -> IntelligenceCacheWorkflow:
    return IntelligenceCacheWorkflow(MainWindowIntelligenceCacheHost(window))
