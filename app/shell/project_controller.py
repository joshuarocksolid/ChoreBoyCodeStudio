"""Project open/recent coordination helpers for shell layer."""

from __future__ import annotations

import os
from logging import Logger
from typing import Callable

from app.core.errors import AppValidationError
from app.core.models import LoadedProject
from app.project.project_open_worker import ProjectOpenWorker
from app.project.project_service import open_project_and_track_recent
from app.project.recent_projects import OPEN_RECENT_MENU_LIMIT, load_recent_projects
from app.shell.menus import MenuStubRegistry, build_recent_project_menu_items

DispatchToMainThread = Callable[[Callable[[], None]], None]


class ProjectController:
    """Coordinates project open/recent flows outside the main window class."""

    def __init__(
        self,
        *,
        state_root: str | None,
        logger: Logger,
        dispatch_to_main_thread: DispatchToMainThread | None = None,
    ) -> None:
        self._state_root = state_root
        self._logger = logger
        self._dispatch_to_main_thread = dispatch_to_main_thread
        self._default_async_open = os.environ.get("CBCS_SYNC_PROJECT_OPEN") != "1"
        self._open_generation = 0
        self._active_open_worker: ProjectOpenWorker | None = None

    def open_project_by_path(
        self,
        project_root: str,
        *,
        confirm_proceed: Callable[[str], bool],
        on_loaded: Callable[[LoadedProject], None],
        on_error: Callable[[str, str], None],
        on_loading: Callable[[], None] | None = None,
        exclude_patterns: list[str] | None = None,
        async_open: bool | None = None,
    ) -> bool:
        if async_open is None:
            async_open = self._default_async_open
        if not confirm_proceed("opening another project"):
            return False

        if not async_open:
            return self._open_project_sync(
                project_root,
                on_loaded=on_loaded,
                on_error=on_error,
                exclude_patterns=exclude_patterns,
            )

        self._cancel_active_open()
        self._open_generation += 1
        generation = self._open_generation
        if on_loading is not None:
            on_loading()

        worker = ProjectOpenWorker(
            project_root=project_root,
            state_root=self._state_root,
            exclude_patterns=exclude_patterns,
            should_commit=lambda: generation == self._open_generation,
            on_success=lambda loaded_project: self._handle_open_success(
                generation,
                project_root,
                loaded_project,
                on_loaded=on_loaded,
            ),
            on_error=lambda details: self._handle_open_error(
                generation,
                project_root,
                details,
                on_error=on_error,
            ),
        )
        self._active_open_worker = worker
        worker.start()
        return True

    def cancel_active_open(self) -> None:
        self._cancel_active_open()

    def _open_project_sync(
        self,
        project_root: str,
        *,
        on_loaded: Callable[[LoadedProject], None],
        on_error: Callable[[str, str], None],
        exclude_patterns: list[str] | None,
    ) -> bool:
        try:
            loaded_project = open_project_and_track_recent(
                project_root,
                state_root=self._state_root,
                exclude_patterns=exclude_patterns,
            )
        except (AppValidationError, ValueError) as exc:
            on_error(project_root, str(exc))
            return False
        except Exception as exc:  # pragma: no cover - defensive shell guard
            self._logger.exception("Unexpected error while opening project: %s", project_root)
            on_error(project_root, f"Unexpected error: {exc}")
            return False

        on_loaded(loaded_project)
        return True

    def _dispatch(self, callback: Callable[[], None]) -> None:
        if self._dispatch_to_main_thread is not None:
            self._dispatch_to_main_thread(callback)
            return
        callback()

    def _handle_open_success(
        self,
        generation: int,
        project_root: str,
        loaded_project: LoadedProject,
        *,
        on_loaded: Callable[[LoadedProject], None],
    ) -> None:
        def apply() -> None:
            if generation != self._open_generation:
                return
            self._active_open_worker = None
            from app.project.recent_projects import remember_recent_project

            remember_recent_project(loaded_project.project_root, state_root=self._state_root)
            on_loaded(loaded_project)

        self._dispatch(apply)

    def _handle_open_error(
        self,
        generation: int,
        project_root: str,
        details: str,
        *,
        on_error: Callable[[str, str], None],
    ) -> None:
        def apply() -> None:
            if generation != self._open_generation:
                return
            self._active_open_worker = None
            on_error(project_root, details)

        self._dispatch(apply)

    def _cancel_active_open(self) -> None:
        self._open_generation += 1
        if self._active_open_worker is not None:
            self._active_open_worker.cancel()
            self._active_open_worker = None

    def refresh_open_recent_menu(
        self,
        menu_registry: MenuStubRegistry | None,
        *,
        open_project_by_path: Callable[[str], bool],
    ) -> None:
        if menu_registry is None:
            return

        open_recent_menu = menu_registry.menu("shell.menu.file.openRecent")
        if open_recent_menu is None:
            return

        open_recent_menu.clear()
        recent_paths = load_recent_projects(
            state_root=self._state_root, max_entries=OPEN_RECENT_MENU_LIMIT,
        )
        recent_items = build_recent_project_menu_items(recent_paths)

        if not recent_items:
            placeholder_action = open_recent_menu.addAction("(No recent projects)")
            placeholder_action.setEnabled(False)
            return

        for recent_item in recent_items:
            action = open_recent_menu.addAction(recent_item.display_text)
            action.setToolTip(recent_item.project_path)
            action.triggered.connect(
                lambda _checked=False, project_path=recent_item.project_path: open_project_by_path(project_path)
            )
