"""Stylesheet section builders for a focused shell UI area."""

from __future__ import annotations

from app.shell.theme_tokens import ShellThemeTokens


def _chrome_icon_tool_button_qss(
    selector: str,
    tokens: ShellThemeTokens,
    *,
    padding: str = "3px",
    font_size: str | None = None,
    include_focus: bool = True,
) -> str:
    font_rule = f"\n    font-size: {font_size};" if font_size else ""
    focus_rule = ""
    if include_focus:
        focus_rule = f"""
{selector}:focus {{
    border: {tokens.focus_border_width}px solid {tokens.accent};
}}"""
    return f"""{selector} {{
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: {padding};{font_rule}
}}
{selector}:hover {{
    background: {tokens.tree_hover_bg};
}}
{selector}:pressed {{
    background: {tokens.tree_selected_bg};
}}{focus_rule}
"""


def _toolbar_accent_button_qss(
    selector: str,
    tokens: ShellThemeTokens,
    *,
    bg: str,
    hover_bg: str,
    pressed_bg: str,
    fg: str,
) -> str:
    return f"""{selector} {{
    background: {bg};
    color: {fg};
}}
{selector}:hover {{
    background: {hover_bg};
}}
{selector}:pressed {{
    background: {pressed_bg};
}}
"""


def shell_section_chrome_font_weight(tokens: ShellThemeTokens) -> str:
    """Apply the user's UI font-weight preference to chrome surfaces.

    The selectors deliberately:

    - Exclude ``QPlainTextEdit`` and ``QTextEdit`` so the code editor and
      read-only output viewers keep their own weight.
    - Exclude ``QTabBar`` / ``QTabWidget`` because some dialogs (e.g. the
      settings dialog) set tab fonts via ``QWidget.setFont`` and Qt merges
      stylesheet font properties into the widget font, which would override
      the explicit DemiBold weight.

    More specific rules later in the stylesheet (e.g. ``font-weight: 700`` on
    a panel title) still win because they have higher selector specificity.
    """
    return f"""/* -- Chrome font weight (user preference) -------------------------------- */
QMenuBar, QMenu, QToolBar, QStatusBar,
QLabel, QPushButton, QToolButton,
QGroupBox, QGroupBox::title,
QLineEdit, QComboBox, QSpinBox, QCheckBox, QRadioButton,
QTreeView, QListView, QTableView, QHeaderView::section,
QDialog, QDockWidget, QDockWidget::title {{
    font-weight: {tokens.ui_font_weight_css};
}}
"""


def shell_section_main_window_menus(tokens: ShellThemeTokens) -> str:
    return f"""QMainWindow#shell\\.mainWindow {{
    background: {tokens.window_bg};
    color: {tokens.text_primary};
}}
/* -- Menu bar and dropdown menus ---------------------------------------- */
QMenuBar#shell\\.menuBar {{
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
    border-bottom: 1px solid {tokens.border};
    padding: 2px 4px;
    spacing: 1px;
    font-size: 12px;
}}
QMenuBar#shell\\.menuBar::item {{
    background: transparent;
    color: {tokens.text_muted};
    padding: 5px 10px;
    border-radius: 4px;
    margin: 1px 0px;
}}
QMenuBar#shell\\.menuBar::item:selected {{
    background: {tokens.tree_hover_bg};
    color: {tokens.text_primary};
}}
QMenuBar#shell\\.menuBar::item:pressed {{
    background: {tokens.tree_selected_bg};
    color: {tokens.text_primary};
}}
QMenu {{
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 6px;
    padding: 4px 0px;
    font-size: 12px;
}}
QMenu::item {{
    padding: 6px 32px 6px 12px;
    border-radius: 4px;
    margin: 1px 4px;
}}
QMenu::item:selected {{
    background: {tokens.tree_hover_bg};
    color: {tokens.text_primary};
}}
QMenu::separator {{
    height: 1px;
    background: {tokens.border};
    margin: 4px 8px;
}}
QMenu::right-arrow {{
    width: 8px;
    height: 8px;
    margin-right: 8px;
}}
"""


def shell_section_explorer_status_toolbar_chrome(tokens: ShellThemeTokens) -> str:
    explorer_action_btn = _chrome_icon_tool_button_qss("QToolButton#shell\\.explorerAction", tokens)
    return f"""QLabel#shell\\.leftRegion\\.title {{
    color: {tokens.text_muted};
    font-size: 11px;
    font-weight: bold;
    padding: 0px;
}}
QLabel#shell\\.leftRegion\\.body {{
    color: {tokens.text_muted};
}}
QWidget#shell\\.explorerHeader {{
    background: transparent;
}}
{explorer_action_btn}
QStatusBar#shell\\.statusBar {{
    border-top: 1px solid {tokens.border};
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
}}
QStatusBar#shell\\.statusBar::item {{
    border: none;
    background: transparent;
}}
QStatusBar#shell\\.statusBar QLabel {{
    color: {tokens.text_muted};
    background: transparent;
    font-size: 11px;
    padding: 0 4px;
}}
QLabel#shell\\.startupStatusLabel[startupSeverity="warning"],
QLabel#shell\\.startupStatusLabel[startupSeverity="unknown"] {{
    color: {tokens.diag_warning_color};
}}
QLabel#shell\\.pythonToolingStatusLabel[pythonToolingSeverity="warning"] {{
    color: {tokens.diag_warning_color};
}}
QLabel#shell\\.diagnosticsStatusLabel[diagnosticsSeverity="error"] {{
    color: {tokens.diag_error_color};
}}
QLabel#shell\\.diagnosticsStatusLabel[diagnosticsSeverity="warning"] {{
    color: {tokens.diag_warning_color};
}}
QLabel#shell\\.runStatusLabel[runSeverity="idle"] {{
    color: {tokens.text_muted};
}}
QLabel#shell\\.runStatusLabel[runSeverity="running"] {{
    color: {tokens.debug_running_color};
}}
QLabel#shell\\.runStatusLabel[runSeverity="stopping"],
QLabel#shell\\.runStatusLabel[runSeverity="warning"] {{
    color: {tokens.diag_warning_color};
}}
QLabel#shell\\.runStatusLabel[runSeverity="error"] {{
    color: {tokens.diag_error_color};
}}
QLabel#shell\\.runStatusLabel[runSeverity="ok"] {{
    color: {tokens.debug_running_color};
}}
QToolButton#shell\\.statusBar\\.activeRunConfig {{
    background: transparent;
    color: {tokens.text_muted};
    border: none;
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 11px;
}}
QToolButton#shell\\.statusBar\\.activeRunConfig:hover {{
    background: {tokens.tree_hover_bg};
    color: {tokens.text_primary};
}}
QToolButton#shell\\.statusBar\\.activeRunConfig:pressed {{
    background: {tokens.tree_selected_bg};
}}
QToolButton#shell\\.statusBar\\.activeRunConfig:focus {{
    border: {tokens.focus_border_width}px solid {tokens.accent};
}}
QWidget#shell\\.toolbar\\.runDebug {{
    background: {tokens.panel_bg};
    border-bottom: 1px solid {tokens.border};
}}
"""


def shell_section_toolbar_buttons(tokens: ShellThemeTokens) -> str:
    run_btn = _toolbar_accent_button_qss(
        "QToolButton#shell\\.toolbar\\.btn\\.run",
        tokens,
        bg=tokens.toolbar_run_bg,
        hover_bg=tokens.toolbar_run_hover_bg,
        pressed_bg=tokens.toolbar_run_pressed_bg,
        fg=tokens.toolbar_run_fg,
    )
    stop_btn = _toolbar_accent_button_qss(
        "QToolButton#shell\\.toolbar\\.btn\\.stop",
        tokens,
        bg=tokens.toolbar_stop_bg,
        hover_bg=tokens.toolbar_stop_hover_bg,
        pressed_bg=tokens.toolbar_stop_pressed_bg,
        fg=tokens.toolbar_stop_fg,
    )
    debug_btn = _toolbar_accent_button_qss(
        "QToolButton#shell\\.toolbar\\.btn\\.debug",
        tokens,
        bg=tokens.toolbar_debug_bg,
        hover_bg=tokens.toolbar_debug_hover_bg,
        pressed_bg=tokens.toolbar_debug_pressed_bg,
        fg=tokens.toolbar_debug_fg,
    )
    package_btn = _toolbar_accent_button_qss(
        "QToolButton#shell\\.toolbar\\.btn\\.package",
        tokens,
        bg=tokens.toolbar_package_bg,
        hover_bg=tokens.toolbar_package_hover_bg,
        pressed_bg=tokens.toolbar_package_pressed_bg,
        fg=tokens.toolbar_package_fg,
    )
    return f"""/* -- Default toolbar button style --------------------------------------- */
QToolButton[objectName^="shell.toolbar.btn"] {{
    background: transparent;
    color: {tokens.text_primary};
    border: none;
    border-radius: 5px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 600;
}}
QToolButton[objectName^="shell.toolbar.btn"]:hover {{
    background: {tokens.tree_hover_bg};
}}
QToolButton[objectName^="shell.toolbar.btn"]:pressed {{
    background: {tokens.tree_selected_bg};
}}
QToolButton[objectName^="shell.toolbar.btn"]:focus {{
    border: {tokens.focus_border_width}px solid {tokens.accent};
}}
{run_btn}
{stop_btn}
{debug_btn}
{package_btn}
QFrame#shell\\.toolbar\\.separator {{
    color: {tokens.border};
}}
"""


def shell_section_tab_bar(tokens: ShellThemeTokens) -> str:
    return f"""QTabBar::tab {{
    background: {tokens.panel_bg};
    color: {tokens.text_muted};
    padding: 6px 10px;
    border: 1px solid {tokens.border};
    border-bottom: none;
}}
QTabBar::tab:selected {{
    color: {tokens.text_primary};
    border-top: 2px solid {tokens.accent};
}}
QTabBar::close-button {{
    image: url({tokens.tab_close_icon_path});
    padding: 2px;
}}
QTabBar::close-button:hover {{
    image: url({tokens.tab_close_icon_hover_path});
    background: {tokens.chrome_hover_overlay};
    border-radius: 3px;
}}
"""


def shell_section_activity_bar(tokens: ShellThemeTokens) -> str:
    activity_btn = _chrome_icon_tool_button_qss(
        'QToolButton[objectName^="shell.activityBar.btn"]',
        tokens,
        padding="4px",
        font_size="14px",
        include_focus=True,
    )
    return f"""/* -- Activity bar -------------------------------------------------------- */
QWidget#shell\\.activityBar {{
    background: {tokens.activity_bar_bg};
    border-right: 1px solid {tokens.border};
}}
{activity_btn}
QToolButton[objectName^="shell.activityBar.btn"] {{
    color: {tokens.text_muted};
}}
QToolButton[objectName^="shell.activityBar.btn"]:hover {{
    color: {tokens.text_primary};
}}
QToolButton[objectName^="shell.activityBar.btn"]:checked {{
    background: {tokens.tree_selected_bg};
    color: {tokens.text_primary};
    border-left: 2px solid {tokens.accent};
}}
"""
