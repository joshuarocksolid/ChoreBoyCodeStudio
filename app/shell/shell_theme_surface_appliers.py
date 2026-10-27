"""Apply resolved theme tokens to MainWindow shell child surfaces."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from app.qt.QtCore import QEvent, QObject, Qt
from app.qt.QtGui import QColor, QFont, QPalette
from app.qt.QtWidgets import QApplication, QToolTip, QWidget
from app.qt.qt_compat import enum_value

from app.shell.icons import explorer_icon, search_icon, test_icon
from app.shell.menu_icons import apply_menu_icons
from app.shell.shell_theme_workflow import ShellThemeChildCallbacks
from app.shell.theme_tokens import ShellThemeTokens


@dataclass(frozen=True)
class ShellThemeSurfaceRefs:
    """Explicit widget references for shell theme surface application."""

    editor_manager: Any
    editor_widgets_by_buffer_id: dict[str, Any]
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
    apply_editor_tab_chrome_theme: Callable[[ShellThemeTokens], None] | None = None

    @classmethod
    def from_main_window(cls, window: Any) -> ShellThemeSurfaceRefs:
        return cls(
            editor_manager=window._editor_manager,
            editor_widgets_by_buffer_id=window._editor_widgets_by_path,
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
            apply_editor_tab_chrome_theme=_tab_chrome_theme_applier(window),
        )


def _tab_chrome_theme_applier(window: Any) -> Callable[[ShellThemeTokens], None] | None:
    coordinator = getattr(window, "_editor_tabs_coordinator", None)
    return None if coordinator is None else coordinator.apply_tab_chrome_theme


_TIP_SHEET = ""
_TIP_FILTER: Optional[QObject] = None
_COLOR_DECL = re.compile(r"(?m)^\s*(background-color|color|border)\s*:\s*([^;]+);")


class _TooltipWindowFilter(QObject):
    """Apply the tooltip sheet to the tip window only.

    An application style sheet wraps every widget in QStyleSheetStyle, including
    a realized form, and a later clear-and-restore repolishes the whole process.
    """

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() != QEvent.Show or not isinstance(watched, QWidget) or not watched.isWindow():
            return False
        window_type = enum_value(watched.windowFlags()) & 0xFF
        if window_type != enum_value(Qt.ToolTip):
            return False
        sheet = _TIP_SHEET
        if sheet and watched.styleSheet() != sheet:
            watched.setStyleSheet(sheet)
        return False


def set_app_tooltip_style_sheet(style_sheet: str) -> None:
    """Style tooltips from the shell tokens without an application style sheet."""
    global _TIP_SHEET
    _TIP_SHEET = style_sheet
    _apply_tooltip_palette(style_sheet)
    _install_tooltip_filter()


def _apply_tooltip_palette(style_sheet: str) -> None:
    background, foreground = _tooltip_colors(style_sheet)
    palette = QPalette(QToolTip.palette())
    roles = getattr(QPalette, "ColorRole", QPalette)
    if background:
        palette.setColor(getattr(roles, "ToolTipBase"), QColor(background))
    if foreground:
        palette.setColor(getattr(roles, "ToolTipText"), QColor(foreground))
    QToolTip.setPalette(palette)
    app = QApplication.instance()
    if isinstance(app, QApplication):
        QToolTip.setFont(QFont(app.font()))


def _tooltip_colors(style_sheet: str) -> tuple:
    background = ""
    foreground = ""
    for name, value in _COLOR_DECL.findall(style_sheet):
        if name == "background-color":
            background = value.strip()
        elif name == "color":
            foreground = value.strip()
    return background, foreground


def _install_tooltip_filter() -> None:
    global _TIP_FILTER
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    if _TIP_FILTER is None:
        _TIP_FILTER = _TooltipWindowFilter(app)
        app.installEventFilter(_TIP_FILTER)


def apply_editor_themes(refs: ShellThemeSurfaceRefs, tokens: ShellThemeTokens) -> None:
    active_tab = refs.editor_manager.active_tab()
    active_buffer_id = None if active_tab is None else active_tab.buffer_id
    deferred_widgets: list[Any] = []
    for buffer_id, editor_widget in refs.editor_widgets_by_buffer_id.items():
        defer_rehighlight = buffer_id != active_buffer_id
        editor_widget.apply_theme(tokens, defer_syntax_rehighlight=defer_rehighlight)
        if defer_rehighlight:
            deferred_widgets.append(editor_widget)
    for editor_widget in deferred_widgets:
        editor_widget.flush_pending_syntax_theme_refresh()
    if refs.apply_editor_tab_chrome_theme is not None:
        refs.apply_editor_tab_chrome_theme(tokens)


def apply_markdown_themes(refs: ShellThemeSurfaceRefs, tokens: ShellThemeTokens) -> None:
    registry = refs.tab_content_registry
    if registry is None:
        return
    registry.apply_all_themes(tokens)


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
