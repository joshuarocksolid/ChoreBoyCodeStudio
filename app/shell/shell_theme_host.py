"""MainWindow adapter for :class:`ShellThemeWorkflow`."""

from __future__ import annotations

from typing import Any, cast

from app.shell.shell_composition_context import MainWindowCompositionSurface
from app.shell.shell_theme_surface_appliers import build_main_window_shell_theme_callbacks
from app.shell.shell_theme_workflow import ExplorerThemeHost


class _WindowBackedExplorerThemeSink:
    """Explorer icon fields stored on ``MainWindow`` for project tree rendering."""

    def __init__(self, window: MainWindowCompositionSurface) -> None:
        self._window = cast(Any, window)

    @property
    def tree_file_icon(self) -> Any:
        return self._window._tree_file_icon

    @tree_file_icon.setter
    def tree_file_icon(self, value: Any) -> None:
        self._window._tree_file_icon = value

    @property
    def tree_file_icon_map(self) -> dict[str, Any]:
        return self._window._tree_file_icon_map

    @tree_file_icon_map.setter
    def tree_file_icon_map(self, value: dict[str, Any]) -> None:
        self._window._tree_file_icon_map = value

    @property
    def tree_filename_icon_map(self) -> dict[str, Any]:
        return self._window._tree_filename_icon_map

    @tree_filename_icon_map.setter
    def tree_filename_icon_map(self, value: dict[str, Any]) -> None:
        self._window._tree_filename_icon_map = value

    @property
    def tree_folder_icon(self) -> Any:
        return self._window._tree_folder_icon

    @tree_folder_icon.setter
    def tree_folder_icon(self, value: Any) -> None:
        self._window._tree_folder_icon = value

    @property
    def tree_folder_open_icon(self) -> Any:
        return self._window._tree_folder_open_icon

    @tree_folder_open_icon.setter
    def tree_folder_open_icon(self, value: Any) -> None:
        self._window._tree_folder_open_icon = value

    @property
    def tree_entrypoint_icon(self) -> Any:
        return self._window._tree_entrypoint_icon

    @tree_entrypoint_icon.setter
    def tree_entrypoint_icon(self, value: Any) -> None:
        self._window._tree_entrypoint_icon = value


class MainWindowShellThemeHost:
    """Live ``MainWindow`` view for :class:`ShellThemeWorkflow`."""

    def __init__(self, window: MainWindowCompositionSurface) -> None:
        backing = cast(Any, window)
        self._window = backing
        self.is_applying_theme_styles = False
        self.system_dark_theme_preference: bool | None = None
        self.child_callbacks = build_main_window_shell_theme_callbacks(backing)
        self.explorer = ExplorerThemeHost(
            sink=_WindowBackedExplorerThemeSink(window),
            explorer_new_file_btn=backing._explorer_new_file_btn,
            explorer_new_folder_btn=backing._explorer_new_folder_btn,
            explorer_refresh_btn=backing._explorer_refresh_btn,
            loaded_project=backing._loaded_project,
        )

    @property
    def palette_accessor(self) -> Any:
        return self._window

    @property
    def theme_mode(self) -> str:
        return self._window._theme_mode

    @property
    def ui_font_weight(self) -> str:
        return self._window._ui_font_weight

    @property
    def dark_chrome_palette(self) -> str:
        return self._window._dark_chrome_palette

    @property
    def syntax_color_overrides(self) -> dict[str, dict[str, str]]:
        return self._window._syntax_color_overrides
