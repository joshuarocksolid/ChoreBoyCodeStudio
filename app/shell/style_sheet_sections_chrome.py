"""Stylesheet section builders for a focused shell UI area."""

from __future__ import annotations

from app.shell.theme_tokens import ShellThemeTokens


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
QMenu::item:disabled {{
    color: {tokens.text_muted};
}}
QMenu::separator {{
    height: 1px;
    background: {tokens.border};
    margin: 4px 12px;
}}
QMenu::indicator {{
    width: 14px;
    height: 14px;
    margin-left: 6px;
}}
QMenu::indicator:checked {{
    background: {tokens.accent};
    border-radius: 3px;
}}
QMenu::indicator:unchecked {{
    background: transparent;
}}
QMenu::right-arrow {{
    width: 8px;
    height: 8px;
    margin-right: 8px;
}}
"""
def shell_section_explorer_status_toolbar_chrome(tokens: ShellThemeTokens) -> str:
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
QToolButton#shell\\.explorerAction {{
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 3px;
}}
QToolButton#shell\\.explorerAction:hover {{
    background: {tokens.tree_hover_bg};
}}
QToolButton#shell\\.explorerAction:pressed {{
    background: {tokens.tree_selected_bg};
}}
QStatusBar#shell\\.statusBar {{
    border-top: 1px solid {tokens.border};
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
}}
QLabel#shell\\.startupStatusLabel,
QLabel#shell\\.runStatusLabel,
QLabel#shell\\.projectStatusLabel,
QLabel#shell\\.editorStatusLabel,
QLabel#shell\\.diagnosticsStatusLabel {{
    color: {tokens.text_muted};
    background: transparent;
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
QWidget#shell\\.toolbar\\.runDebug {{
    background: {tokens.panel_bg};
    border-bottom: 1px solid {tokens.border};
}}
"""
def shell_section_toolbar_buttons(tokens: ShellThemeTokens) -> str:
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
/* -- Run button (green accent) ------------------------------------------ */
QToolButton#shell\\.toolbar\\.btn\\.run {{
    background: {"#1B3D1B" if tokens.is_dark else "#E6F4EA"};
    color: {"#4ADE80" if tokens.is_dark else "#15803D"};
}}
QToolButton#shell\\.toolbar\\.btn\\.run:hover {{
    background: {"#22502A" if tokens.is_dark else "#D1EDDA"};
}}
QToolButton#shell\\.toolbar\\.btn\\.run:pressed {{
    background: {"#2A6434" if tokens.is_dark else "#B7DFC6"};
}}
/* -- Stop button (red accent) ------------------------------------------- */
QToolButton#shell\\.toolbar\\.btn\\.stop {{
    background: {"#3D1B1B" if tokens.is_dark else "#FEE2E2"};
    color: {"#F87171" if tokens.is_dark else "#B91C1C"};
}}
QToolButton#shell\\.toolbar\\.btn\\.stop:hover {{
    background: {"#502222" if tokens.is_dark else "#FECACA"};
}}
QToolButton#shell\\.toolbar\\.btn\\.stop:pressed {{
    background: {"#642A2A" if tokens.is_dark else "#FCA5A5"};
}}
/* -- Debug button (amber accent) ---------------------------------------- */
QToolButton#shell\\.toolbar\\.btn\\.debug {{
    background: {"#3D2E0A" if tokens.is_dark else "#FEF3C7"};
    color: {"#FBBF24" if tokens.is_dark else "#B45309"};
}}
QToolButton#shell\\.toolbar\\.btn\\.debug:hover {{
    background: {"#50400E" if tokens.is_dark else "#FDE68A"};
}}
QToolButton#shell\\.toolbar\\.btn\\.debug:pressed {{
    background: {"#645214" if tokens.is_dark else "#FCD34D"};
}}
/* -- Package button (blue accent) -------------------------------------- */
QToolButton#shell\\.toolbar\\.btn\\.package {{
    background: {"#1B2A4A" if tokens.is_dark else "#E8EEFF"};
    color: {"#7EA8FF" if tokens.is_dark else "#2952CC"};
}}
QToolButton#shell\\.toolbar\\.btn\\.package:hover {{
    background: {"#243758" if tokens.is_dark else "#D6E0FF"};
}}
QToolButton#shell\\.toolbar\\.btn\\.package:pressed {{
    background: {"#2E4468" if tokens.is_dark else "#C4D4FF"};
}}
QFrame#shell\\.toolbar\\.separator {{
    color: {tokens.border};
}}
"""
def shell_section_tab_bar(tokens: ShellThemeTokens) -> str:
    return f"""QToolButton#shell\\.explorerAction,
QToolButton {{
    color: {tokens.text_primary};
}}
QTabBar::tab {{
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
    background: {"rgba(255, 255, 255, 0.1)" if tokens.is_dark else "rgba(0, 0, 0, 0.08)"};
    border-radius: 3px;
}}
"""
def shell_section_activity_bar(tokens: ShellThemeTokens) -> str:
    return f"""/* -- Activity bar -------------------------------------------------------- */
QWidget#shell\\.activityBar {{
    background: {tokens.activity_bar_bg};
    border-right: 1px solid {tokens.border};
}}
QToolButton[objectName^="shell.activityBar.btn"] {{
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 4px;
    font-size: 14px;
    color: {tokens.text_muted};
}}
QToolButton[objectName^="shell.activityBar.btn"]:hover {{
    background: {tokens.tree_hover_bg};
    color: {tokens.text_primary};
}}
QToolButton[objectName^="shell.activityBar.btn"]:checked {{
    background: {tokens.tree_selected_bg};
    color: {tokens.text_primary};
    border-left: 2px solid {tokens.accent};
}}
"""
