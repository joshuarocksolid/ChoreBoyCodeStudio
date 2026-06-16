"""Intelligence cache workflow using the shared background task scheduler."""

from __future__ import annotations

import time
from typing import Any, Callable, Protocol

from PySide2.QtWidgets import QMessageBox

from app.intelligence.cache_controls import rebuild_symbol_cache
from app.intelligence.symbol_index import update_symbol_index_cache
from app.project.file_excludes import compute_effective_excludes

SYMBOL_INDEX_TASK_PREFIX = "symbol_index:"


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

    def background_tasks(self) -> Any:
        ...

    def symbol_index_generation(self) -> int:
        ...

    def bump_symbol_index_generation(self) -> int:
        ...

    def dispatch_to_main_thread(self, callback: Callable[[], None]) -> None:
        ...


class IntelligenceCacheWorkflow:
    """Owns symbol index scheduling and cache rebuild."""

    def __init__(self, host: IntelligenceCacheHost) -> None:
        self._host = host

    def start_symbol_indexing(self, project_root: str, *, exclude_patterns: list[str] | None = None) -> None:
        if not self._host.intelligence_cache_enabled():
            return
        generation = self._host.bump_symbol_index_generation()
        started_at = time.perf_counter()
        effective_excludes = exclude_patterns
        loaded_project = self._host.loaded_project()
        if effective_excludes is None and loaded_project is not None:
            effective_excludes = compute_effective_excludes(
                self._host.load_effective_exclude_patterns(loaded_project.project_root),
                loaded_project.metadata.exclude_patterns,
            )
        task_key = f"{SYMBOL_INDEX_TASK_PREFIX}{project_root}"

        def task(cancel_event) -> int | None:  # type: ignore[no-untyped-def]
            return update_symbol_index_cache(
                project_root=project_root,
                cache_db_path=self._host.symbol_cache_db_path(),
                exclude_patterns=effective_excludes or (),
                cancel_event=cancel_event,
                should_commit=lambda: generation == self._host.symbol_index_generation(),
            )

        def on_success(symbol_count: int | None) -> None:
            if symbol_count is None or generation != self._host.symbol_index_generation():
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

        def on_error(message: Exception) -> None:
            if generation != self._host.symbol_index_generation():
                return
            self._host.logger().warning("Symbol index failed for %s: %s", project_root, message)

        self._host.background_tasks().run(
            key=task_key,
            task=task,
            on_success=on_success,
            on_error=on_error,
        )

    def cancel_symbol_indexing(self, project_root: str | None = None) -> None:
        if project_root is None:
            loaded = self._host.loaded_project()
            if loaded is None:
                return
            project_root = loaded.project_root
        self._host.background_tasks().cancel(f"{SYMBOL_INDEX_TASK_PREFIX}{project_root}")

    def rebuild_intelligence_cache(self) -> bool | None:
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

    def background_tasks(self) -> Any:
        return self._window._background_tasks

    def symbol_index_generation(self) -> int:
        return self._window._symbol_index_generation

    def bump_symbol_index_generation(self) -> int:
        self._window._symbol_index_generation += 1
        return self._window._symbol_index_generation

    def dispatch_to_main_thread(self, callback: Callable[[], None]) -> None:
        self._window._dispatch_to_main_thread(callback)


def build_intelligence_cache_workflow(window: Any) -> IntelligenceCacheWorkflow:
    return IntelligenceCacheWorkflow(MainWindowIntelligenceCacheHost(window))
