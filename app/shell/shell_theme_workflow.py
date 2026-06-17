"""Theme token resolution and shell-wide style application."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping, Protocol, cast

from app.core import constants
from app.shell.file_type_icons import clear_icon_caches as clear_file_type_icon_caches
from app.shell.icon_provider import (
    clear_icon_caches as clear_context_icon_caches,
    file_icon,
    file_type_icon_map,
    filename_icon_map,
    folder_icon,
    folder_open_icon,
    new_file_icon,
    new_folder_icon,
    refresh_icon,
)
from app.shell.outline.outline_icons import clear_icon_caches as clear_outline_icon_caches
from app.shell.problems_panel import clear_icon_caches as clear_problems_icon_caches
from app.shell.test_explorer_icons import clear_icon_caches as clear_test_explorer_icon_caches
from app.shell.settings_models import parse_editor_settings_snapshot
from app.shell.style_sheet import build_app_tooltip_style_sheet, build_shell_style_sheet
from app.shell.syntax_color_preferences import parse_syntax_color_overrides
from app.shell.theme_tokens import ShellThemeTokens, apply_syntax_token_overrides, tokens_from_palette
from app.shell.toolbar_icons import ensure_tab_close_icons, icon_run


class PaletteAccessor(Protocol):
    """Minimal palette surface used for theme token derivation."""

    def palette(self) -> object:
        ...


class ThemeSettingsReader(Protocol):
    """Minimal settings surface for theme preference loading."""

    def load_global(self) -> Mapping[str, Any]:
        ...


class ExplorerToolbarButton(Protocol):
    def setIcon(self, icon: object) -> None:
        ...


@dataclass(frozen=True)
class ShellThemeChildCallbacks:
    """Callbacks that apply resolved tokens to shell child widgets."""

    set_shell_style_sheet: Callable[[str], None]
    set_app_tooltip_style_sheet: Callable[[str], None]
    apply_editor_themes: Callable[[ShellThemeTokens], None]
    apply_markdown_themes: Callable[[ShellThemeTokens], None]
    apply_python_console_theme: Callable[[ShellThemeTokens], None] | None = None
    apply_run_log_theme: Callable[[ShellThemeTokens], None] | None = None
    apply_search_sidebar_theme: Callable[[ShellThemeTokens], None] | None = None
    apply_activity_bar_view_icons: Callable[[ShellThemeTokens], None] | None = None
    apply_menu_bar_icons: Callable[[ShellThemeTokens], None] | None = None
    apply_test_explorer_theme: Callable[[ShellThemeTokens], None] | None = None
    apply_outline_theme: Callable[[ShellThemeTokens], None] | None = None


@dataclass
class ExplorerThemeSink:
    """Mutable explorer tree icon state updated during theme application."""

    tree_file_icon: Any = None
    tree_file_icon_map: dict[str, Any] = field(default_factory=dict)
    tree_filename_icon_map: dict[str, Any] = field(default_factory=dict)
    tree_folder_icon: Any = None
    tree_folder_open_icon: Any = None
    tree_entrypoint_icon: Any = None


@dataclass
class ExplorerThemeHost:
    """Explorer chrome references used when applying explorer theme."""

    sink: ExplorerThemeSink
    explorer_new_file_btn: ExplorerToolbarButton | None = None
    explorer_new_folder_btn: ExplorerToolbarButton | None = None
    explorer_refresh_btn: ExplorerToolbarButton | None = None
    loaded_project: object | None = None
    populate_project_tree: Callable[[], None] | None = None


@dataclass
class ShellThemeWorkflowHost:
    """Typed host surface for :class:`ShellThemeWorkflow` (not ``window: Any``)."""

    palette_accessor: Callable[[], object] | PaletteAccessor
    theme_mode: str
    ui_font_weight: str
    dark_chrome_palette: str
    syntax_color_overrides: dict[str, dict[str, str]]
    child_callbacks: ShellThemeChildCallbacks
    explorer: ExplorerThemeHost | None = None
    is_applying_theme_styles: bool = False
    system_dark_theme_preference: bool | None = None


class ShellThemeWorkflow:
    """Resolves theme tokens and applies shell-wide styles through a typed host."""

    def __init__(self, host: ShellThemeWorkflowHost | Any) -> None:
        self._host = host

    @property
    def host(self) -> Any:
        return self._host

    @staticmethod
    def load_theme_mode(settings_service: ThemeSettingsReader) -> str:
        settings_payload = settings_service.load_global()
        snapshot = parse_editor_settings_snapshot(settings_payload)
        return snapshot.theme_mode

    @staticmethod
    def load_ui_font_weight(settings_service: ThemeSettingsReader) -> str:
        settings_payload = settings_service.load_global()
        snapshot = parse_editor_settings_snapshot(settings_payload)
        return snapshot.ui_font_weight

    @staticmethod
    def load_dark_chrome_palette(settings_service: ThemeSettingsReader) -> str:
        settings_payload = settings_service.load_global()
        snapshot = parse_editor_settings_snapshot(settings_payload)
        return snapshot.dark_chrome_palette

    @staticmethod
    def load_syntax_color_overrides(settings_service: ThemeSettingsReader) -> dict[str, dict[str, str]]:
        settings_payload = settings_service.load_global()
        return parse_syntax_color_overrides(settings_payload)

    def resolve_theme_tokens(self) -> ShellThemeTokens:
        host = self._host
        if callable(host.palette_accessor):
            palette = cast(Any, host.palette_accessor())
        else:
            palette = cast(Any, host.palette_accessor.palette())
        mode = host.theme_mode
        if mode in (
            constants.UI_THEME_MODE_LIGHT,
            constants.UI_THEME_MODE_DARK,
            constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
            constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
        ):
            base_tokens = tokens_from_palette(
                palette,
                force_mode=mode,
                ui_font_weight=host.ui_font_weight,
                dark_chrome_palette=host.dark_chrome_palette,
            )
        else:
            base_tokens = tokens_from_palette(
                palette,
                prefer_dark=self.system_prefers_dark_theme(),
                ui_font_weight=host.ui_font_weight,
                dark_chrome_palette=host.dark_chrome_palette,
            )
        if base_tokens.is_high_contrast:
            theme_key = (
                constants.UI_SYNTAX_COLORS_HIGH_CONTRAST_DARK_KEY
                if base_tokens.is_dark
                else constants.UI_SYNTAX_COLORS_HIGH_CONTRAST_LIGHT_KEY
            )
        else:
            theme_key = (
                constants.UI_SYNTAX_COLORS_DARK_KEY
                if base_tokens.is_dark
                else constants.UI_SYNTAX_COLORS_LIGHT_KEY
            )
        syntax_overrides = host.syntax_color_overrides.get(theme_key, {})
        return apply_syntax_token_overrides(base_tokens, syntax_overrides)

    @staticmethod
    def _clear_theme_icon_caches() -> None:
        clear_context_icon_caches()
        clear_file_type_icon_caches()
        clear_outline_icon_caches()
        clear_problems_icon_caches()
        clear_test_explorer_icon_caches()

    def apply_theme_styles(self) -> None:
        host = self._host
        if host.is_applying_theme_styles:
            return
        host.is_applying_theme_styles = True
        try:
            self._clear_theme_icon_caches()
            tokens = self.resolve_theme_tokens()
            close_normal, close_hover = ensure_tab_close_icons(
                tokens.text_muted,
                tokens.text_primary,
            )
            tokens = replace(
                tokens,
                tab_close_icon_path=close_normal,
                tab_close_icon_hover_path=close_hover,
            )
            callbacks = host.child_callbacks
            callbacks.set_shell_style_sheet(build_shell_style_sheet(tokens))
            callbacks.set_app_tooltip_style_sheet(build_app_tooltip_style_sheet(tokens))
            callbacks.apply_editor_themes(tokens)
            callbacks.apply_markdown_themes(tokens)
            if callbacks.apply_python_console_theme is not None:
                callbacks.apply_python_console_theme(tokens)
            self.apply_explorer_theme(tokens)
            if callbacks.apply_run_log_theme is not None:
                callbacks.apply_run_log_theme(tokens)
            if callbacks.apply_search_sidebar_theme is not None:
                callbacks.apply_search_sidebar_theme(tokens)
            if callbacks.apply_activity_bar_view_icons is not None:
                callbacks.apply_activity_bar_view_icons(tokens)
            if callbacks.apply_menu_bar_icons is not None:
                callbacks.apply_menu_bar_icons(tokens)
            if callbacks.apply_test_explorer_theme is not None:
                callbacks.apply_test_explorer_theme(tokens)
            if callbacks.apply_outline_theme is not None:
                callbacks.apply_outline_theme(tokens)
        finally:
            host.is_applying_theme_styles = False

    def apply_explorer_theme(self, tokens: ShellThemeTokens) -> None:
        explorer = self._host.explorer
        if explorer is None:
            return
        sink = explorer.sink
        sink.tree_file_icon = file_icon(tokens.icon_primary)
        sink.tree_file_icon_map = file_type_icon_map()
        sink.tree_filename_icon_map = filename_icon_map()
        sink.tree_folder_icon = folder_icon(tokens.icon_muted)
        sink.tree_folder_open_icon = folder_open_icon(tokens.icon_muted)
        sink.tree_entrypoint_icon = icon_run(tokens.debug_running_color)
        if explorer.explorer_new_file_btn is not None:
            explorer.explorer_new_file_btn.setIcon(
                new_file_icon(tokens.icon_primary, tokens.icon_muted)
            )
        if explorer.explorer_new_folder_btn is not None:
            explorer.explorer_new_folder_btn.setIcon(
                new_folder_icon(tokens.icon_primary, tokens.icon_muted)
            )
        if explorer.explorer_refresh_btn is not None:
            explorer.explorer_refresh_btn.setIcon(refresh_icon(tokens.icon_primary))

    def system_prefers_dark_theme(self) -> bool:
        host = self._host
        cached_preference = host.system_dark_theme_preference
        if cached_preference is not None:
            return cached_preference
        try:
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            host.system_dark_theme_preference = False
            return False
        if result.returncode != 0:
            host.system_dark_theme_preference = False
            return False
        host.system_dark_theme_preference = "prefer-dark" in result.stdout
        return host.system_dark_theme_preference

    def invalidate_system_dark_theme_preference(self) -> None:
        self._host.system_dark_theme_preference = None
