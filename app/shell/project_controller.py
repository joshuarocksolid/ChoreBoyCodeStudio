"""Project open/recent coordination helpers for shell layer."""

from __future__ import annotations

from logging import Logger
from typing import Callable

from app.core.errors import AppValidationError
from app.core.models import LoadedProject
from app.project.project_service import open_project_and_track_recent
from app.project.recent_projects import OPEN_RECENT_MENU_LIMIT, load_recent_projects
from app.shell.menus import MenuStubRegistry, build_recent_project_menu_items


class ProjectController:
    """Coordinates project open/recent flows outside the main window class."""

    def __init__(self, *, state_root: str | None, logger: Logger) -> None:
        self._state_root = state_root
        self._logger = logger

    def open_project_by_path(
        self,
        project_root: str,
        *,
        confirm_proceed: Callable[[str], bool],
        on_loaded: Callable[[LoadedProject], None],
        on_error: Callable[[str, str], None],
    ) -> bool:
        if not confirm_proceed("opening another project"):
            return False

        try:
            loaded_project = open_project_and_track_recent(
                project_root,
                state_root=self._state_root,
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
