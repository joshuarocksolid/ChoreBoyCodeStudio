"""Apply resolved theme tokens to MainWindow shell child surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from PySide2.QtGui import QColor
from PySide2.QtWidgets import QApplication

from app.shell.icons import explorer_icon, search_icon, test_icon
from app.shell.menu_icons import apply_menu_icons
from app.shell.shell_theme_workflow import ShellThemeChildCallbacks
from app.shell.theme_tokens import ShellThemeTokens


@dataclass(frozen=True)
class ShellThemeSurfaceRefs:
    """Explicit widget references for shell theme surface application."""

    editor_manager: Any
    editor_widgets_by_path: dict[str, Any]
    tab_content_registry: Any
    python_console_widget: Any | None
    run_log_panel: Any | None
    search_sidebar: Any | None
    activity_bar: Any | None
    menu_registry: Any | None
    test_explorer_panel: Any | None
    outline_panel: Any | None
    problems_panel: Any | None
    shell_style_setter: Callable[[str], None]

    @classmethod
    def from_main_window(cls, window: Any) -> ShellThemeSurfaceRefs:
        return cls(
            editor_manager=window._editor_manager,
            editor_widgets_by_path=window._editor_widgets_by_path,
            tab_content_registry=window._tab_content_registry,
            python_console_widget=window._python_console_widget,
            run_log_panel=window._run_log_panel,
            search_sidebar=window._search_sidebar,
            activity_bar=window._activity_bar,
            menu_registry=window._menu_registry,
            test_explorer_panel=window._test_explorer_panel,
            outline_panel=window._outline_panel,
            problems_panel=window._problems_panel,
            shell_style_setter=window.setStyleSheet,
        )


def set_app_tooltip_style_sheet(style_sheet: str) -> None:
    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet(style_sheet)


def apply_editor_themes(refs: ShellThemeSurfaceRefs, tokens: ShellThemeTokens) -> None:
    active_tab = refs.editor_manager.active_tab()
    active_path = None if active_tab is None else active_tab.file_path
    deferred_widgets: list[Any] = []
    for file_path, editor_widget in refs.editor_widgets_by_path.items():
        defer_rehighlight = file_path != active_path
        editor_widget.apply_theme(tokens, defer_syntax_rehighlight=defer_rehighlight)
        if defer_rehighlight:
            deferred_widgets.append(editor_widget)
    for editor_widget in deferred_widgets:
        editor_widget.flush_pending_syntax_theme_refresh()


def apply_markdown_themes(refs: ShellThemeSurfaceRefs, tokens: ShellThemeTokens) -> None:
    refs.tab_content_registry.apply_all_markdown_themes(tokens)


def apply_python_console_theme(refs: ShellThemeSurfaceRefs, tokens: ShellThemeTokens) -> None:
    if refs.python_console_widget is not None:
        refs.python_console_widget.apply_theme(tokens)


def apply_run_log_theme(refs: ShellThemeSurfaceRefs, tokens: ShellThemeTokens) -> None:
    if refs.run_log_panel is not None:
        refs.run_log_panel.apply_theme(tokens)


def apply_search_sidebar_theme(refs: ShellThemeSurfaceRefs, tokens: ShellThemeTokens) -> None:
    if refs.search_sidebar is not None:
        refs.search_sidebar.apply_theme_tokens(
            match_bg=tokens.search_match_bg,
            text_primary=tokens.text_primary,
            text_muted=tokens.text_muted,
            badge_bg=tokens.badge_bg,
        )


def apply_activity_bar_view_icons(refs: ShellThemeSurfaceRefs, tokens: ShellThemeTokens) -> None:
    if refs.activity_bar is None:
        return
    normal = QColor(tokens.text_muted)
    active = QColor(tokens.text_primary)
    refs.activity_bar.set_view_icon(
        "explorer",
        explorer_icon(color_normal=normal, color_active=active),
    )
    refs.activity_bar.set_view_icon(
        "search",
        search_icon(color_normal=normal, color_active=active),
    )
    refs.activity_bar.set_view_icon(
        "test_explorer",
        test_icon(color_normal=normal, color_active=active),
    )


def apply_menu_bar_icons(refs: ShellThemeSurfaceRefs, tokens: ShellThemeTokens) -> None:
    apply_menu_icons(refs.menu_registry, tokens)


def apply_test_explorer_theme(refs: ShellThemeSurfaceRefs, tokens: ShellThemeTokens) -> None:
    if refs.test_explorer_panel is not None:
        refs.test_explorer_panel.apply_theme(tokens)


def apply_outline_theme(refs: ShellThemeSurfaceRefs, tokens: ShellThemeTokens) -> None:
    if refs.outline_panel is not None:
        refs.outline_panel.apply_theme_tokens(tokens)


def apply_problems_panel_theme(refs: ShellThemeSurfaceRefs, tokens: ShellThemeTokens) -> None:
    if refs.problems_panel is not None:
        refs.problems_panel.apply_theme(tokens)


def build_main_window_shell_theme_callbacks(window: Any) -> ShellThemeChildCallbacks:
    refs = ShellThemeSurfaceRefs.from_main_window(window)
    return ShellThemeChildCallbacks(
        set_shell_style_sheet=refs.shell_style_setter,
        set_app_tooltip_style_sheet=set_app_tooltip_style_sheet,
        apply_editor_themes=lambda tokens: apply_editor_themes(refs, tokens),
        apply_markdown_themes=lambda tokens: apply_markdown_themes(refs, tokens),
        apply_python_console_theme=lambda tokens: apply_python_console_theme(refs, tokens),
        apply_run_log_theme=lambda tokens: apply_run_log_theme(refs, tokens),
        apply_search_sidebar_theme=lambda tokens: apply_search_sidebar_theme(refs, tokens),
        apply_activity_bar_view_icons=lambda tokens: apply_activity_bar_view_icons(refs, tokens),
        apply_menu_bar_icons=lambda tokens: apply_menu_bar_icons(refs, tokens),
        apply_test_explorer_theme=lambda tokens: apply_test_explorer_theme(refs, tokens),
        apply_outline_theme=lambda tokens: apply_outline_theme(refs, tokens),
        apply_problems_panel_theme=lambda tokens: apply_problems_panel_theme(refs, tokens),
    )
