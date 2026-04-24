"""Stylesheet section builders grouped by shell UI area (internal helpers)."""

from __future__ import annotations

from app.shell.theme_tokens import ShellThemeTokens


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

def shell_section_workspace_tree_editors(tokens: ShellThemeTokens) -> str:
    return f"""QWidget#shell\\.leftRegion,
QTabWidget#shell\\.editorTabs,
QTabWidget#shell\\.bottomRegion\\.tabs {{
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
}}
QTreeWidget#shell\\.projectTree {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: none;
    border-top: 1px solid {tokens.border};
    outline: none;
}}
QTreeWidget#shell\\.projectTree::item {{
    padding: 3px 4px;
}}
QTreeWidget#shell\\.projectTree::item:hover {{
    background: {tokens.tree_hover_bg};
}}
QTreeWidget#shell\\.projectTree::item:selected {{
    background: {tokens.tree_selected_bg};
    color: {tokens.text_primary};
}}
QTreeWidget#shell\\.projectTree::branch:hover {{
    background: {tokens.tree_hover_bg};
}}
QTreeWidget#shell\\.projectTree::branch:selected {{
    background: {tokens.tree_selected_bg};
}}
QTreeWidget#shell\\.projectTree::branch:has-children:closed {{
    image: none;
    border-image: none;
}}
QTreeWidget#shell\\.projectTree::branch:has-children:open {{
    image: none;
    border-image: none;
}}
QPlainTextEdit#shell\\.editorTabs\\.textEditor,
QPlainTextEdit#shell\\.bottom\\.console {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
}}
QTextEdit#shell\\.bottom\\.pythonConsole {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    padding: 2px;
}}
QToolButton#shell\\.bottom\\.pythonConsole\\.clearBtn {{
    background: transparent;
    color: {tokens.text_muted};
    border: none;
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 10px;
}}
QToolButton#shell\\.bottom\\.pythonConsole\\.clearBtn:hover {{
    background: {tokens.tree_hover_bg};
    color: {tokens.text_primary};
}}
QToolButton#shell\\.bottom\\.pythonConsole\\.clearBtn:pressed {{
    background: {tokens.tree_selected_bg};
}}
"""

def shell_section_run_log_panel(tokens: ShellThemeTokens) -> str:
    return f"""/* -- Run Log panel ------------------------------------------------------ */
QWidget#shell\\.bottom\\.runLog {{
    background: {tokens.editor_bg};
}}
QWidget#shell\\.bottom\\.runLog\\.toolbar {{
    background: {tokens.panel_bg};
    border-bottom: 1px solid {tokens.border};
}}
QLabel#shell\\.bottom\\.runLog\\.metaLabel {{
    color: {tokens.text_muted};
    font-size: 11px;
    padding: 0 4px;
}}
QLabel#shell\\.bottom\\.runLog\\.statusDot {{
    border-radius: 4px;
}}
QLabel#shell\\.bottom\\.runLog\\.statusDot[runLogState="idle"] {{
    background: {tokens.text_muted};
}}
QLabel#shell\\.bottom\\.runLog\\.statusDot[runLogState="success"] {{
    background: {tokens.debug_running_color};
}}
QLabel#shell\\.bottom\\.runLog\\.statusDot[runLogState="running"] {{
    background: {tokens.accent};
}}
QLabel#shell\\.bottom\\.runLog\\.statusDot[runLogState="error"] {{
    background: {tokens.diag_error_color};
}}
QTextEdit#shell\\.bottom\\.runLog\\.textArea {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: none;
    padding: 4px;
}}
QToolButton#shell\\.bottom\\.runLog\\.clearBtn,
QToolButton#shell\\.bottom\\.runLog\\.openBtn {{
    background: transparent;
    color: {tokens.text_muted};
    border: none;
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 10px;
}}
QToolButton#shell\\.bottom\\.runLog\\.clearBtn:hover,
QToolButton#shell\\.bottom\\.runLog\\.openBtn:hover {{
    background: {tokens.tree_hover_bg};
    color: {tokens.text_primary};
}}
QToolButton#shell\\.bottom\\.runLog\\.clearBtn:pressed,
QToolButton#shell\\.bottom\\.runLog\\.openBtn:pressed {{
    background: {tokens.tree_selected_bg};
}}
"""

def shell_section_problems_panel(tokens: ShellThemeTokens) -> str:
    return f"""/* -- Problems panel (VS Code-style) ------------------------------------ */
QWidget#shell\\.problemsPanel {{
    background: {tokens.editor_bg};
}}
QWidget#shell\\.problemsPanel\\.toolbar {{
    background: {tokens.panel_bg};
    border-bottom: 1px solid {tokens.border};
}}
QLabel#shell\\.problemsPanel\\.sourceLabel {{
    color: {tokens.text_muted};
    font-size: 11px;
    padding: 0 4px;
}}
QToolButton#shell\\.problemsPanel\\.filterErrors,
QToolButton#shell\\.problemsPanel\\.filterWarnings,
QToolButton#shell\\.problemsPanel\\.filterInfo {{
    color: {tokens.text_muted};
    background: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 1px 7px;
    font-size: 11px;
}}
QToolButton#shell\\.problemsPanel\\.filterErrors:checked {{
    color: {tokens.diag_error_color};
    border-color: {tokens.diag_error_color};
    background: {tokens.row_alt_bg};
}}
QToolButton#shell\\.problemsPanel\\.filterWarnings:checked {{
    color: {tokens.diag_warning_color};
    border-color: {tokens.diag_warning_color};
    background: {tokens.row_alt_bg};
}}
QToolButton#shell\\.problemsPanel\\.filterInfo:checked {{
    color: {tokens.diag_info_color};
    border-color: {tokens.diag_info_color};
    background: {tokens.row_alt_bg};
}}
QToolButton#shell\\.problemsPanel\\.filterErrors:hover,
QToolButton#shell\\.problemsPanel\\.filterWarnings:hover,
QToolButton#shell\\.problemsPanel\\.filterInfo:hover {{
    background: {tokens.tree_hover_bg};
}}
QTreeWidget#shell\\.problemsPanel\\.tree {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: none;
    outline: none;
}}
QTreeWidget#shell\\.problemsPanel\\.tree::item {{
    padding: 2px 4px;
}}
QTreeWidget#shell\\.problemsPanel\\.tree::item:hover {{
    background: {tokens.tree_hover_bg};
}}
QTreeWidget#shell\\.problemsPanel\\.tree::item:selected {{
    background: {tokens.tree_selected_bg};
}}
QTreeWidget#shell\\.problemsPanel\\.tree::branch {{
    background: transparent;
}}
QTreeWidget#shell\\.problemsPanel\\.tree QHeaderView::section {{
    background: {tokens.panel_bg};
    color: {tokens.text_muted};
    border: none;
    border-bottom: 1px solid {tokens.border};
    padding: 2px 6px;
    font-size: 11px;
}}
QLabel#shell\\.problemsPanel\\.emptyLabel {{
    color: {tokens.text_muted};
    font-size: 12px;
}}
"""

def shell_section_debug_panel(tokens: ShellThemeTokens) -> str:
    return f"""/* -- Debug panel -------------------------------------------------------- */
QWidget#shell\\.debug\\.panel {{
    background: {tokens.panel_bg};
}}
QWidget#shell\\.debug\\.statusHeader {{
    background: {tokens.editor_bg};
    border-bottom: 1px solid {tokens.border};
}}
QLabel#shell\\.debug\\.statusLabel {{
    color: {tokens.text_primary};
    font-size: 11px;
}}
QLabel#shell\\.debug\\.statusDot {{
    border-radius: 5px;
}}
QLabel#shell\\.debug\\.statusDot[debugState="idle"] {{
    background: {tokens.text_muted};
}}
QLabel#shell\\.debug\\.statusDot[debugState="running"] {{
    background: {tokens.debug_running_color};
}}
QLabel#shell\\.debug\\.statusDot[debugState="paused"] {{
    background: {tokens.debug_paused_color};
}}
QWidget#shell\\.debug\\.sectionHeader {{
    background: {tokens.panel_bg};
    border-bottom: 1px solid {tokens.border};
}}
QLabel#shell\\.debug\\.sectionTitle {{
    color: {tokens.text_muted};
    font-size: 10px;
    font-weight: 600;
}}
QLabel#shell\\.debug\\.sectionCount {{
    color: {tokens.text_muted};
    font-size: 9px;
}}
QToolButton#shell\\.debug\\.sectionBtn {{
    background: transparent;
    color: {tokens.text_muted};
    border: none;
    border-radius: 3px;
    padding: 2px 6px;
    font-size: 10px;
}}
QToolButton#shell\\.debug\\.sectionBtn:hover {{
    background: {tokens.tree_hover_bg};
    color: {tokens.text_primary};
}}
QToolButton#shell\\.debug\\.sectionBtn:pressed {{
    background: {tokens.tree_selected_bg};
}}
QToolButton#shell\\.debug\\.sectionBtn:disabled {{
    color: {tokens.text_muted};
}}
QTreeWidget#shell\\.debug\\.stackTree,
QTreeWidget#shell\\.debug\\.variablesTree,
QTreeWidget#shell\\.debug\\.watchTree,
QTreeWidget#shell\\.debug\\.breakpointsTree {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: none;
    outline: none;
    alternate-background-color: {tokens.row_alt_bg};
}}
QTreeWidget#shell\\.debug\\.stackTree::item,
QTreeWidget#shell\\.debug\\.variablesTree::item,
QTreeWidget#shell\\.debug\\.watchTree::item,
QTreeWidget#shell\\.debug\\.breakpointsTree::item {{
    padding: 2px 4px;
}}
QTreeWidget#shell\\.debug\\.stackTree::item:hover,
QTreeWidget#shell\\.debug\\.variablesTree::item:hover,
QTreeWidget#shell\\.debug\\.watchTree::item:hover,
QTreeWidget#shell\\.debug\\.breakpointsTree::item:hover {{
    background: {tokens.tree_hover_bg};
}}
QTreeWidget#shell\\.debug\\.stackTree::item:selected,
QTreeWidget#shell\\.debug\\.variablesTree::item:selected,
QTreeWidget#shell\\.debug\\.watchTree::item:selected,
QTreeWidget#shell\\.debug\\.breakpointsTree::item:selected {{
    background: {tokens.tree_selected_bg};
    color: {tokens.text_primary};
}}
QTreeWidget#shell\\.debug\\.stackTree QHeaderView::section,
QTreeWidget#shell\\.debug\\.variablesTree QHeaderView::section,
QTreeWidget#shell\\.debug\\.watchTree QHeaderView::section {{
    background: {tokens.panel_bg};
    color: {tokens.text_muted};
    border: none;
    border-bottom: 1px solid {tokens.border};
    border-right: 1px solid {tokens.border};
    padding: 2px 6px;
    font-size: 10px;
}}
QPlainTextEdit#shell\\.debug\\.output {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: none;
}}
QWidget#shell\\.debug\\.watchInputRow {{
    background: {tokens.editor_bg};
    border-bottom: 1px solid {tokens.border};
}}
QLineEdit#shell\\.debug\\.watchInput {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 3px;
    padding: 2px 4px;
    font-size: 11px;
}}
QLineEdit#shell\\.debug\\.watchInput:focus {{
    border-color: {tokens.accent};
}}
QWidget#shell\\.debug\\.commandInputRow {{
    background: {tokens.editor_bg};
    border-bottom: 1px solid {tokens.border};
}}
QLineEdit#shell\\.debug\\.commandInput {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 3px;
    padding: 2px 4px;
    font-size: 11px;
}}
QLineEdit#shell\\.debug\\.commandInput:focus {{
    border-color: {tokens.accent};
}}
QLineEdit#shell\\.debug\\.commandInput:disabled {{
    color: {tokens.text_muted};
}}
QSplitter#shell\\.debug\\.mainSplitter::handle,
QSplitter#shell\\.debug\\.leftSplitter::handle,
QSplitter#shell\\.debug\\.rightSplitter::handle {{
    background: {tokens.border};
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

def shell_section_welcome(tokens: ShellThemeTokens) -> str:
    return f"""/* -- Welcome screen ------------------------------------------------------ */
QWidget#shell\\.welcome {{
    background: {tokens.editor_bg};
}}
QWidget#shell\\.welcome\\.container {{
    background: transparent;
}}
QLabel#shell\\.welcome\\.title {{
    font-size: 22px;
    font-weight: 700;
    color: {tokens.text_primary};
    padding-bottom: 4px;
}}
QLabel#shell\\.welcome\\.subtitle {{
    font-size: 13px;
    color: {tokens.text_muted};
    padding-bottom: 4px;
}}
QWidget#shell\\.welcome\\.onboardingCard {{
    background: {tokens.panel_bg};
    border: 1px solid {tokens.border};
    border-radius: 8px;
}}
QLabel#shell\\.welcome\\.onboardingTitle {{
    font-size: 14px;
    font-weight: 700;
    color: {tokens.text_primary};
}}
QLabel#shell\\.welcome\\.onboardingRuntimeSummary,
QLabel#shell\\.welcome\\.onboardingChecklist {{
    color: {tokens.text_primary};
    font-size: 12px;
}}
QLabel#shell\\.welcome\\.onboardingReminder {{
    color: {tokens.text_muted};
    font-size: 11px;
}}
QPushButton#shell\\.welcome\\.newProjectBtn,
QPushButton#shell\\.welcome\\.openProjectBtn {{
    background: {tokens.accent};
    color: #FFFFFF;
    border: none;
    border-radius: 5px;
    padding: 8px 20px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#shell\\.welcome\\.newProjectBtn:hover,
QPushButton#shell\\.welcome\\.openProjectBtn:hover {{
    background: {"#4D7AFF" if tokens.is_dark else "#2952CC"};
}}
QPushButton#shell\\.welcome\\.newProjectBtn:pressed,
QPushButton#shell\\.welcome\\.openProjectBtn:pressed {{
    background: {"#3D6AEE" if tokens.is_dark else "#1F3FA6"};
}}
QPushButton#shell\\.welcome\\.onboardingPrimaryBtn {{
    background: {tokens.accent};
    color: #FFFFFF;
    border: none;
    border-radius: 5px;
    padding: 7px 14px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#shell\\.welcome\\.onboardingPrimaryBtn:hover {{
    background: {"#4D7AFF" if tokens.is_dark else "#2952CC"};
}}
QPushButton#shell\\.welcome\\.onboardingActionBtn,
QPushButton#shell\\.welcome\\.onboardingSecondaryBtn {{
    background: {tokens.input_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 5px;
    padding: 7px 12px;
    font-size: 12px;
}}
QPushButton#shell\\.welcome\\.onboardingActionBtn:hover,
QPushButton#shell\\.welcome\\.onboardingSecondaryBtn:hover {{
    background: {tokens.tree_hover_bg};
    border-color: {tokens.accent};
}}
QPushButton#shell\\.welcome\\.onboardingActionBtn:disabled {{
    color: {tokens.text_muted};
    border-color: {tokens.border};
}}
QLineEdit#shell\\.welcome\\.searchInput {{
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 4px;
    padding: 6px 8px;
    font-size: 12px;
}}
QLineEdit#shell\\.welcome\\.searchInput:focus {{
    border-color: {tokens.accent};
}}
QLabel#shell\\.welcome\\.recentLabel {{
    font-size: 11px;
    font-weight: 600;
    color: {tokens.text_muted};
    padding: 2px 0px;
}}
QListWidget#shell\\.welcome\\.projectList {{
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 4px;
    outline: none;
    font-size: 12px;
}}
QListWidget#shell\\.welcome\\.projectList::item {{
    padding: 6px 8px;
    border-bottom: 1px solid {tokens.border};
}}
QListWidget#shell\\.welcome\\.projectList::item:last {{
    border-bottom: none;
}}
QListWidget#shell\\.welcome\\.projectList::item:hover {{
    background: {tokens.tree_hover_bg};
}}
QListWidget#shell\\.welcome\\.projectList::item:selected {{
    background: {tokens.tree_selected_bg};
    color: {tokens.text_primary};
}}
QLabel#shell\\.welcome\\.emptyLabel {{
    color: {tokens.text_muted};
    font-size: 12px;
    padding: 16px;
}}
"""

def shell_section_find_bar(tokens: ShellThemeTokens) -> str:
    return f"""/* -- Find/Replace bar ---------------------------------------------------- */
QWidget#shell\\.findBar {{
    background: {tokens.panel_bg};
    border-bottom: 2px solid {tokens.border};
}}
QToolButton#shell\\.findBar\\.chevronBtn {{
    background: transparent;
    color: {tokens.text_muted};
    border: none;
    border-radius: 4px;
    font-size: 9px;
}}
QToolButton#shell\\.findBar\\.chevronBtn:hover {{
    background: {tokens.tree_hover_bg};
    color: {tokens.text_primary};
}}
QToolButton#shell\\.findBar\\.chevronBtn:checked {{
    color: {tokens.text_primary};
}}
QLineEdit#shell\\.findBar\\.findInput,
QLineEdit#shell\\.findBar\\.replaceInput {{
    background: {tokens.input_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}}
QLineEdit#shell\\.findBar\\.findInput:focus,
QLineEdit#shell\\.findBar\\.replaceInput:focus {{
    border-color: {tokens.accent};
}}
QLabel#shell\\.findBar\\.matchCount {{
    color: {tokens.text_muted};
    background: {tokens.badge_bg};
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}
QToolButton#shell\\.findBar\\.caseBtn,
QToolButton#shell\\.findBar\\.wordBtn,
QToolButton#shell\\.findBar\\.regexBtn {{
    background: transparent;
    color: {tokens.text_muted};
    border: 1px solid transparent;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 600;
}}
QToolButton#shell\\.findBar\\.caseBtn:hover,
QToolButton#shell\\.findBar\\.wordBtn:hover,
QToolButton#shell\\.findBar\\.regexBtn:hover {{
    background: {tokens.tree_hover_bg};
    color: {tokens.text_primary};
}}
QToolButton#shell\\.findBar\\.caseBtn:pressed,
QToolButton#shell\\.findBar\\.wordBtn:pressed,
QToolButton#shell\\.findBar\\.regexBtn:pressed {{
    background: {tokens.tree_selected_bg};
}}
QToolButton#shell\\.findBar\\.caseBtn:checked,
QToolButton#shell\\.findBar\\.wordBtn:checked,
QToolButton#shell\\.findBar\\.regexBtn:checked {{
    background: {tokens.tree_selected_bg};
    color: {tokens.accent};
    border-bottom: 2px solid {tokens.accent};
}}
QToolButton#shell\\.findBar\\.prevBtn,
QToolButton#shell\\.findBar\\.nextBtn {{
    background: transparent;
    color: {tokens.text_muted};
    border: 1px solid transparent;
    border-radius: 4px;
    font-size: 12px;
}}
QToolButton#shell\\.findBar\\.prevBtn:hover,
QToolButton#shell\\.findBar\\.nextBtn:hover {{
    background: {tokens.tree_hover_bg};
    color: {tokens.text_primary};
}}
QToolButton#shell\\.findBar\\.prevBtn:pressed,
QToolButton#shell\\.findBar\\.nextBtn:pressed {{
    background: {tokens.tree_selected_bg};
}}
QToolButton#shell\\.findBar\\.closeBtn {{
    background: transparent;
    color: {tokens.text_muted};
    border: none;
    border-radius: 4px;
    font-size: 12px;
}}
QToolButton#shell\\.findBar\\.closeBtn:hover {{
    background: {tokens.tree_hover_bg};
    color: {tokens.text_primary};
}}
QToolButton#shell\\.findBar\\.closeBtn:pressed {{
    background: {tokens.tree_selected_bg};
}}
QPushButton#shell\\.findBar\\.replaceBtn,
QPushButton#shell\\.findBar\\.replaceAllBtn {{
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 4px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
}}
QPushButton#shell\\.findBar\\.replaceBtn:hover,
QPushButton#shell\\.findBar\\.replaceAllBtn:hover {{
    background: {tokens.tree_hover_bg};
    color: {tokens.accent};
    border-color: {tokens.accent};
}}
QPushButton#shell\\.findBar\\.replaceBtn:pressed,
QPushButton#shell\\.findBar\\.replaceAllBtn:pressed {{
    background: {tokens.tree_selected_bg};
}}
"""

def shell_section_quick_open(tokens: ShellThemeTokens) -> str:
    return f"""/* -- Quick Open dialog --------------------------------------------------- */
QDialog#shell\\.quickOpen {{
    background: {tokens.panel_bg};
    border: 1px solid {tokens.border};
    border-radius: 8px;
}}
QLineEdit#shell\\.quickOpen\\.input {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: none;
    border-bottom: 1px solid {tokens.border};
    padding: 10px 14px 10px 6px;
    font-size: 14px;
}}
QLineEdit#shell\\.quickOpen\\.input:focus {{
    border-bottom: 2px solid {tokens.accent};
}}
QListView#shell\\.quickOpen\\.results {{
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
    border: none;
    outline: none;
}}
QListView#shell\\.quickOpen\\.results::item {{
    padding: 0px;
    border-bottom: 1px solid {tokens.border};
}}
QListView#shell\\.quickOpen\\.results::item:last {{
    border-bottom: none;
}}
QListView#shell\\.quickOpen\\.results::item:hover {{
    background: {tokens.tree_hover_bg};
}}
QListView#shell\\.quickOpen\\.results::item:selected {{
    background: {tokens.tree_selected_bg};
}}
QLabel#shell\\.quickOpen\\.empty {{
    color: {tokens.text_muted};
    font-size: 13px;
    padding: 24px;
}}
QLabel#shell\\.quickOpen\\.count {{
    color: {tokens.text_muted};
    font-size: 11px;
}}
QListView#shell\\.quickOpen\\.results QScrollBar:vertical {{
    width: 6px;
    background: transparent;
    margin: 2px 1px;
}}
QListView#shell\\.quickOpen\\.results QScrollBar::handle:vertical {{
    background: {tokens.text_muted};
    border-radius: 3px;
    min-height: 20px;
}}
QListView#shell\\.quickOpen\\.results QScrollBar::add-line:vertical,
QListView#shell\\.quickOpen\\.results QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QListView#shell\\.quickOpen\\.results QScrollBar::add-page:vertical,
QListView#shell\\.quickOpen\\.results QScrollBar::sub-page:vertical {{
    background: transparent;
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

def shell_section_search_sidebar(tokens: ShellThemeTokens) -> str:
    return f"""/* -- Search sidebar ------------------------------------------------------ */
QWidget#shell\\.searchSidebar {{
    background: {tokens.panel_bg};
}}
QLabel#shell\\.searchSidebar\\.header {{
    color: {tokens.text_muted};
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 0.5px;
}}
QLineEdit#shell\\.searchSidebar\\.searchInput,
QLineEdit#shell\\.searchSidebar\\.replaceInput,
QLineEdit#shell\\.searchSidebar\\.includeInput,
QLineEdit#shell\\.searchSidebar\\.excludeInput {{
    background: {tokens.input_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}}
QLineEdit#shell\\.searchSidebar\\.searchInput:focus,
QLineEdit#shell\\.searchSidebar\\.replaceInput:focus,
QLineEdit#shell\\.searchSidebar\\.includeInput:focus,
QLineEdit#shell\\.searchSidebar\\.excludeInput:focus {{
    border-color: {tokens.accent};
}}
QToolButton#shell\\.searchSidebar\\.caseBtn,
QToolButton#shell\\.searchSidebar\\.wordBtn,
QToolButton#shell\\.searchSidebar\\.regexBtn {{
    background: transparent;
    color: {tokens.text_muted};
    border: 1px solid transparent;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 600;
}}
QToolButton#shell\\.searchSidebar\\.caseBtn:hover,
QToolButton#shell\\.searchSidebar\\.wordBtn:hover,
QToolButton#shell\\.searchSidebar\\.regexBtn:hover {{
    background: {tokens.tree_hover_bg};
    color: {tokens.text_primary};
}}
QToolButton#shell\\.searchSidebar\\.caseBtn:pressed,
QToolButton#shell\\.searchSidebar\\.wordBtn:pressed,
QToolButton#shell\\.searchSidebar\\.regexBtn:pressed {{
    background: {tokens.tree_selected_bg};
}}
QToolButton#shell\\.searchSidebar\\.caseBtn:checked,
QToolButton#shell\\.searchSidebar\\.wordBtn:checked,
QToolButton#shell\\.searchSidebar\\.regexBtn:checked {{
    background: {tokens.tree_selected_bg};
    color: {tokens.accent};
    border-bottom: 2px solid {tokens.accent};
}}
QToolButton#shell\\.searchSidebar\\.replaceToggle {{
    background: transparent;
    color: {tokens.text_muted};
    border: none;
    border-radius: 4px;
    font-size: 9px;
}}
QToolButton#shell\\.searchSidebar\\.replaceToggle:hover {{
    background: {tokens.tree_hover_bg};
    color: {tokens.text_primary};
}}
QToolButton#shell\\.searchSidebar\\.replaceToggle:checked {{
    color: {tokens.text_primary};
}}
QToolButton#shell\\.searchSidebar\\.filterToggle {{
    background: transparent;
    color: {tokens.text_muted};
    border: 1px solid transparent;
    border-radius: 4px;
    font-size: 13px;
    font-weight: bold;
}}
QToolButton#shell\\.searchSidebar\\.filterToggle:hover {{
    background: {tokens.tree_hover_bg};
    color: {tokens.text_primary};
}}
QToolButton#shell\\.searchSidebar\\.filterToggle:checked {{
    background: {tokens.tree_selected_bg};
    color: {tokens.accent};
}}
QToolButton#shell\\.searchSidebar\\.filterToggle[hasActiveFilters="true"] {{
    color: {tokens.accent};
}}
QWidget#shell\\.searchSidebar\\.filtersContainer {{
    border-top: 1px solid {tokens.border};
}}
QPushButton#shell\\.searchSidebar\\.replaceAllBtn {{
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 4px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
}}
QPushButton#shell\\.searchSidebar\\.replaceAllBtn:hover {{
    background: {tokens.tree_hover_bg};
    color: {tokens.accent};
    border-color: {tokens.accent};
}}
QPushButton#shell\\.searchSidebar\\.replaceAllBtn:pressed {{
    background: {tokens.tree_selected_bg};
}}
QLabel#shell\\.searchSidebar\\.summary {{
    color: {tokens.text_muted};
    font-size: 11px;
    padding: 2px 0;
    font-weight: 600;
}}
QToolButton#shell\\.searchSidebar\\.clearBtn {{
    background: transparent;
    color: {tokens.text_muted};
    border: none;
    border-radius: 4px;
    font-size: 10px;
}}
QToolButton#shell\\.searchSidebar\\.clearBtn:hover {{
    background: {tokens.tree_hover_bg};
    color: {tokens.text_primary};
}}
QLabel#shell\\.searchSidebar\\.noResults {{
    color: {tokens.text_muted};
    font-size: 12px;
    padding: 24px 16px;
}}
QTreeWidget#shell\\.searchSidebar\\.results {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: none;
    border-top: 1px solid {tokens.border};
    outline: none;
    font-size: 12px;
    alternate-background-color: {tokens.row_alt_bg};
}}
QTreeWidget#shell\\.searchSidebar\\.results::item {{
    padding: 2px 4px;
}}
QTreeWidget#shell\\.searchSidebar\\.results::item:hover {{
    background: {tokens.tree_hover_bg};
}}
QTreeWidget#shell\\.searchSidebar\\.results::item:selected {{
    background: {tokens.tree_selected_bg};
    color: {tokens.text_primary};
}}
QTreeWidget#shell\\.searchSidebar\\.results::branch {{
    border-image: none;
    image: none;
}}
"""

def shell_section_help_dialog(tokens: ShellThemeTokens) -> str:
    return f"""/* -- Help dialog --------------------------------------------------------- */
QDialog#shell\\.helpDialog {{
    background: {tokens.panel_bg};
}}
QWidget#shell\\.helpDialog\\.header {{
    background: {tokens.panel_bg};
    border-bottom: 1px solid {tokens.border};
}}
QLabel#shell\\.helpDialog\\.icon {{
    font-size: 20px;
}}
QLabel#shell\\.helpDialog\\.title {{
    font-size: 17px;
    font-weight: 700;
    color: {tokens.text_primary};
}}
QTextBrowser#shell\\.helpDialog\\.browser {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: none;
    padding: 16px 24px;
    font-size: 13px;
}}
QWidget#shell\\.helpDialog\\.footer {{
    background: {tokens.panel_bg};
    border-top: 1px solid {tokens.border};
}}
QPushButton#shell\\.helpDialog\\.closeBtn {{
    background: {tokens.accent};
    color: #FFFFFF;
    border: none;
    border-radius: 5px;
    padding: 7px 16px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#shell\\.helpDialog\\.closeBtn:hover {{
    background: {"#4D7AFF" if tokens.is_dark else "#2952CC"};
}}
QPushButton#shell\\.helpDialog\\.closeBtn:pressed {{
    background: {"#3D6AEE" if tokens.is_dark else "#1F3FA6"};
}}
"""


def shell_section_runtime_center_dialog(tokens: ShellThemeTokens) -> str:
    return f"""/* -- Runtime Center dialog ----------------------------------------------- */
QDialog#shell\\.runtimeCenterDialog {{
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
}}
QWidget#shell\\.runtimeCenterDialog\\.header {{
    background: {tokens.panel_bg};
    border-bottom: 1px solid {tokens.border};
}}
QLabel#shell\\.runtimeCenterDialog\\.title {{
    font-size: 18px;
    font-weight: 700;
    color: {tokens.text_primary};
}}
QLabel#shell\\.runtimeCenterDialog\\.summary {{
    color: {tokens.text_muted};
    font-size: 12px;
}}
QListWidget#shell\\.runtimeCenterDialog\\.issueList {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 6px;
    outline: none;
    alternate-background-color: {tokens.row_alt_bg};
    font-size: 12px;
}}
QListWidget#shell\\.runtimeCenterDialog\\.issueList::item {{
    padding: 8px 10px;
    border-bottom: 1px solid {tokens.border};
}}
QListWidget#shell\\.runtimeCenterDialog\\.issueList::item:last {{
    border-bottom: none;
}}
QListWidget#shell\\.runtimeCenterDialog\\.issueList::item:hover {{
    background: {tokens.tree_hover_bg};
}}
QListWidget#shell\\.runtimeCenterDialog\\.issueList::item:selected {{
    background: {tokens.tree_selected_bg};
    color: {tokens.text_primary};
}}
QTextBrowser#shell\\.runtimeCenterDialog\\.detailBrowser {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 6px;
    padding: 8px 10px;
    font-size: 13px;
}}
QWidget#shell\\.runtimeCenterDialog\\.footer {{
    background: {tokens.panel_bg};
    border-top: 1px solid {tokens.border};
}}
QPushButton#shell\\.runtimeCenterDialog\\.helpButton,
QPushButton#shell\\.runtimeCenterDialog\\.closeButton {{
    background: {tokens.input_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 5px;
    padding: 7px 14px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#shell\\.runtimeCenterDialog\\.helpButton:hover,
QPushButton#shell\\.runtimeCenterDialog\\.closeButton:hover {{
    background: {tokens.tree_hover_bg};
    border-color: {tokens.accent};
}}
QPushButton#shell\\.runtimeCenterDialog\\.helpButton:pressed,
QPushButton#shell\\.runtimeCenterDialog\\.closeButton:pressed {{
    background: {tokens.tree_selected_bg};
}}
QPushButton#shell\\.runtimeCenterDialog\\.helpButton:disabled {{
    color: {tokens.text_muted};
    border-color: {tokens.border};
}}
QPushButton#shell\\.runtimeCenterDialog\\.closeButton {{
    background: {tokens.accent};
    color: #FFFFFF;
    border: none;
}}
QPushButton#shell\\.runtimeCenterDialog\\.closeButton:hover {{
    background: {"#4D7AFF" if tokens.is_dark else "#2952CC"};
}}
QPushButton#shell\\.runtimeCenterDialog\\.closeButton:pressed {{
    background: {"#3D6AEE" if tokens.is_dark else "#1F3FA6"};
}}
"""


def shell_section_package_wizard(tokens: ShellThemeTokens) -> str:
    return f"""/* -- Package wizard ------------------------------------------------------ */
QWizard#shell\\.packageWizard {{
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
}}
QWizard#shell\\.packageWizard QLabel {{
    color: {tokens.text_primary};
}}
QWizard#shell\\.packageWizard QGroupBox {{
    border: 1px solid {tokens.border};
    border-radius: 6px;
    margin-top: 12px;
    padding: 12px 10px 10px 10px;
    background: {tokens.panel_bg};
}}
QWizard#shell\\.packageWizard QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {tokens.text_muted};
}}
QWizard#shell\\.packageWizard QLineEdit,
QWizard#shell\\.packageWizard QTextEdit,
QWizard#shell\\.packageWizard QComboBox {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 5px;
    padding: 6px 8px;
}}
QWizard#shell\\.packageWizard QLineEdit:focus,
QWizard#shell\\.packageWizard QTextEdit:focus,
QWizard#shell\\.packageWizard QComboBox:focus {{
    border-color: {tokens.accent};
}}
QWizard#shell\\.packageWizard QPushButton {{
    background: {tokens.input_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 5px;
    padding: 7px 14px;
    font-size: 12px;
    font-weight: 600;
}}
QWizard#shell\\.packageWizard QPushButton:hover {{
    background: {tokens.tree_hover_bg};
    border-color: {tokens.accent};
}}
QWizard#shell\\.packageWizard QPushButton:pressed {{
    background: {tokens.tree_selected_bg};
}}
QWizard#shell\\.packageWizard QCheckBox {{
    color: {tokens.text_primary};
}}
"""


def settings_section_dialog_and_tabs(tokens: ShellThemeTokens) -> str:
    return f"""/* -- Dialog -------------------------------------------------------------- */
QDialog#shell\\.settingsDialog {{
    background: {tokens.window_bg};
    color: {tokens.text_primary};
}}
/* -- Tab widget ---------------------------------------------------------- */
QDialog#shell\\.settingsDialog QTabWidget::pane {{
    border: 1px solid {tokens.border};
    border-top: none;
    background: {tokens.panel_bg};
}}
QDialog#shell\\.settingsDialog QTabBar::tab {{
    background: {tokens.panel_bg};
    color: {tokens.text_muted};
    padding: 8px 16px;
    min-height: 16px;
    border: 1px solid {tokens.border};
    border-bottom: none;
    font-size: 12px;
    font-weight: 600;
}}
QDialog#shell\\.settingsDialog QTabBar::tab:selected {{
    color: {tokens.text_primary};
    border-top: 2px solid {tokens.accent};
    background: {tokens.panel_bg};
}}
QDialog#shell\\.settingsDialog QTabBar::tab:hover:!selected {{
    background: {tokens.tree_hover_bg};
    color: {tokens.text_primary};
}}
"""

def settings_section_scope_controls(tokens: ShellThemeTokens) -> str:
    return f"""/* -- Scope header -------------------------------------------------------- */
QFrame#shell\\.settingsDialog\\.scopeHeader {{
    background: transparent;
    border-bottom: 1px solid {tokens.border};
    padding-bottom: 8px;
}}
/* -- Segmented control --------------------------------------------------- */
QWidget#shell\\.settingsDialog\\.scopeSegmented {{
    background: {tokens.input_bg};
    border: 1px solid {tokens.border};
    border-radius: 6px;
    padding: 2px;
    max-width: 220px;
}}
QWidget#shell\\.settingsDialog\\.scopeSegmented QPushButton {{
    background: transparent;
    color: {tokens.text_muted};
    border: none;
    border-radius: 4px;
    padding: 5px 20px;
    font-size: 12px;
    font-weight: 600;
    min-width: 80px;
}}
QWidget#shell\\.settingsDialog\\.scopeSegmented QPushButton[segmentActive="true"] {{
    background: {tokens.accent};
    color: #FFFFFF;
}}
QWidget#shell\\.settingsDialog\\.scopeSegmented QPushButton:hover {{
    background: {tokens.tree_hover_bg};
    color: {tokens.text_primary};
}}
QWidget#shell\\.settingsDialog\\.scopeSegmented QPushButton[segmentActive="true"]:hover {{
    background: {"#4D7AFF" if tokens.is_dark else "#2952CC"};
    color: #FFFFFF;
}}
QWidget#shell\\.settingsDialog\\.scopeSegmented QPushButton:disabled {{
    color: {tokens.border};
    background: transparent;
}}
/* -- Scope banner -------------------------------------------------------- */
QLabel#shell\\.settingsDialog\\.scopeBanner {{
    background: transparent;
    color: {tokens.text_muted};
    padding: 2px 0px;
    font-size: 11px;
}}
"""

def settings_section_group_boxes_and_labels(tokens: ShellThemeTokens) -> str:
    return f"""/* -- Group boxes --------------------------------------------------------- */
QDialog#shell\\.settingsDialog QGroupBox {{
    background: transparent;
    border: none;
    border-bottom: 1px solid {tokens.border};
    margin-top: 16px;
    padding-top: 24px;
    padding-bottom: 12px;
    font-size: 11px;
    font-weight: 700;
    color: {tokens.text_muted};
}}
QDialog#shell\\.settingsDialog QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 4px 0px;
    color: {tokens.text_muted};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
/* -- Labels -------------------------------------------------------------- */
QDialog#shell\\.settingsDialog QLabel {{
    color: {tokens.text_primary};
    font-size: 12px;
    background: transparent;
}}
QLabel#shell\\.settingsDialog\\.fileExcludesHelp {{
    color: {tokens.text_muted};
    font-size: 11px;
    padding: 4px 0px;
}}
"""

def settings_section_combo_spin_font(tokens: ShellThemeTokens) -> str:
    return f"""/* -- Combo boxes --------------------------------------------------------- */
QDialog#shell\\.settingsDialog QComboBox {{
    background: {tokens.input_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 4px;
    padding: 4px 24px 4px 8px;
    font-size: 12px;
    min-height: 20px;
}}
QDialog#shell\\.settingsDialog QComboBox:hover {{
    border-color: {tokens.accent};
}}
QDialog#shell\\.settingsDialog QComboBox:focus {{
    border-color: {tokens.accent};
}}
QDialog#shell\\.settingsDialog QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QDialog#shell\\.settingsDialog QComboBox QAbstractItemView {{
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    selection-background-color: {tokens.tree_selected_bg};
    selection-color: {tokens.text_primary};
    outline: none;
}}
/* -- Spin boxes ---------------------------------------------------------- */
QDialog#shell\\.settingsDialog QSpinBox {{
    background: {tokens.input_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
    min-height: 20px;
}}
QDialog#shell\\.settingsDialog QSpinBox:hover {{
    border-color: {tokens.accent};
}}
QDialog#shell\\.settingsDialog QSpinBox:focus {{
    border-color: {tokens.accent};
}}
/* -- Font combo ---------------------------------------------------------- */
QDialog#shell\\.settingsDialog QFontComboBox {{
    background: {tokens.input_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 4px;
    padding: 4px 24px 4px 8px;
    font-size: 12px;
    min-height: 20px;
}}
QDialog#shell\\.settingsDialog QFontComboBox:hover {{
    border-color: {tokens.accent};
}}
QDialog#shell\\.settingsDialog QFontComboBox:focus {{
    border-color: {tokens.accent};
}}
QDialog#shell\\.settingsDialog QFontComboBox QAbstractItemView {{
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    selection-background-color: {tokens.tree_selected_bg};
    selection-color: {tokens.text_primary};
}}
"""

def settings_section_checkbox_and_line_edit(tokens: ShellThemeTokens) -> str:
    return f"""/* -- Check boxes --------------------------------------------------------- */
QDialog#shell\\.settingsDialog QCheckBox {{
    color: {tokens.text_primary};
    font-size: 12px;
    spacing: 6px;
}}
/* -- Line edits ---------------------------------------------------------- */
QDialog#shell\\.settingsDialog QLineEdit {{
    background: {tokens.input_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
    min-height: 20px;
}}
QDialog#shell\\.settingsDialog QLineEdit:focus {{
    border-color: {tokens.accent};
}}
"""

def settings_section_push_buttons(tokens: ShellThemeTokens) -> str:
    return f"""/* -- Push buttons (default) ---------------------------------------------- */
QDialog#shell\\.settingsDialog QPushButton {{
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 5px;
    padding: 5px 14px;
    font-size: 12px;
    font-weight: 600;
}}
QDialog#shell\\.settingsDialog QPushButton:hover {{
    background: {tokens.tree_hover_bg};
    border-color: {tokens.accent};
    color: {tokens.accent};
}}
QDialog#shell\\.settingsDialog QPushButton:pressed {{
    background: {tokens.tree_selected_bg};
}}
/* -- Ok button (primary) ------------------------------------------------- */
QPushButton#shell\\.settingsDialog\\.okBtn {{
    background: {tokens.accent};
    color: #FFFFFF;
    border: none;
    border-radius: 5px;
    padding: 7px 20px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#shell\\.settingsDialog\\.okBtn:hover {{
    background: {"#4D7AFF" if tokens.is_dark else "#2952CC"};
}}
QPushButton#shell\\.settingsDialog\\.okBtn:pressed {{
    background: {"#3D6AEE" if tokens.is_dark else "#1F3FA6"};
}}
QPushButton#shell\\.settingsDialog\\.okBtn:disabled {{
    background: {tokens.text_muted};
    color: {tokens.panel_bg};
}}
/* -- Cancel button (secondary) ------------------------------------------- */
QPushButton#shell\\.settingsDialog\\.cancelBtn {{
    background: transparent;
    color: {tokens.text_muted};
    border: 1px solid {tokens.border};
}}
QPushButton#shell\\.settingsDialog\\.cancelBtn:hover {{
    background: {tokens.tree_hover_bg};
    color: {tokens.text_primary};
    border-color: {tokens.text_muted};
}}
"""

def settings_section_tables_lists_scroll_area(tokens: ShellThemeTokens) -> str:
    return f"""/* -- Table widgets ------------------------------------------------------- */
QDialog#shell\\.settingsDialog QTableWidget {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 4px;
    gridline-color: {tokens.border};
    alternate-background-color: {tokens.row_alt_bg};
    outline: none;
    font-size: 12px;
}}
QDialog#shell\\.settingsDialog QTableWidget::item {{
    padding: 4px 8px;
}}
QDialog#shell\\.settingsDialog QTableWidget::item:hover {{
    background: {tokens.tree_hover_bg};
}}
QDialog#shell\\.settingsDialog QHeaderView::section {{
    background: {tokens.panel_bg};
    color: {tokens.text_muted};
    border: none;
    border-bottom: 1px solid {tokens.border};
    border-right: 1px solid {tokens.border};
    padding: 6px 8px;
    font-size: 11px;
    font-weight: 600;
}}
/* -- List widget --------------------------------------------------------- */
QDialog#shell\\.settingsDialog QListWidget {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 4px;
    outline: none;
    font-size: 12px;
}}
QDialog#shell\\.settingsDialog QListWidget::item {{
    padding: 6px 8px;
    border-bottom: 1px solid {tokens.border};
}}
QDialog#shell\\.settingsDialog QListWidget::item:last {{
    border-bottom: none;
}}
QDialog#shell\\.settingsDialog QListWidget::item:hover {{
    background: {tokens.tree_hover_bg};
}}
QDialog#shell\\.settingsDialog QListWidget::item:selected {{
    background: {tokens.tree_selected_bg};
    color: {tokens.text_primary};
}}
/* -- Scroll area --------------------------------------------------------- */
QDialog#shell\\.settingsDialog QScrollArea {{
    background: transparent;
    border: none;
}}
"""

def settings_section_scrollbars_shortcuts_validation(tokens: ShellThemeTokens) -> str:
    return f"""/* -- Scroll bars --------------------------------------------------------- */
QDialog#shell\\.settingsDialog QScrollBar:vertical {{
    width: 6px;
    background: transparent;
    margin: 2px 1px;
}}
QDialog#shell\\.settingsDialog QScrollBar::handle:vertical {{
    background: {tokens.text_muted};
    border-radius: 3px;
    min-height: 20px;
}}
QDialog#shell\\.settingsDialog QScrollBar::add-line:vertical,
QDialog#shell\\.settingsDialog QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QDialog#shell\\.settingsDialog QScrollBar::add-page:vertical,
QDialog#shell\\.settingsDialog QScrollBar::sub-page:vertical {{
    background: transparent;
}}
/* -- Key sequence editor ------------------------------------------------- */
QDialog#shell\\.settingsDialog QKeySequenceEdit {{
    background: {tokens.input_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 12px;
}}
QDialog#shell\\.settingsDialog QKeySequenceEdit:focus {{
    border-color: {tokens.accent};
}}
/* -- Validation labels --------------------------------------------------- */
QLabel#shell\\.settingsDialog\\.shortcutConflict,
QLabel#shell\\.settingsDialog\\.syntaxValidation {{
    color: {tokens.diag_error_color};
    background: {"#3D1B1B" if tokens.is_dark else "#FEE2E2"};
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
}}
"""


def shell_section_test_explorer(tokens: ShellThemeTokens) -> str:
    passed_color = tokens.test_passed_color or tokens.debug_running_color
    return f"""/* -- Test Explorer panel ------------------------------------------------ */
QWidget#shell\\.testExplorer {{
    background: {tokens.editor_bg};
}}
QWidget#shell\\.testExplorer\\.toolbar {{
    background: {tokens.panel_bg};
    border-bottom: 1px solid {tokens.border};
}}
QLabel#shell\\.testExplorer\\.title {{
    color: {tokens.text_primary};
    font-size: 12px;
    font-weight: bold;
    padding: 0 2px;
}}
QToolButton#shell\\.testExplorer\\.runAllBtn,
QToolButton#shell\\.testExplorer\\.runFailedBtn,
QToolButton#shell\\.testExplorer\\.refreshBtn {{
    background: transparent;
    color: {tokens.text_muted};
    border: none;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11px;
}}
QToolButton#shell\\.testExplorer\\.runAllBtn:hover,
QToolButton#shell\\.testExplorer\\.runFailedBtn:hover,
QToolButton#shell\\.testExplorer\\.refreshBtn:hover {{
    background: {tokens.tree_hover_bg};
    color: {tokens.text_primary};
}}
QToolButton#shell\\.testExplorer\\.runAllBtn:pressed,
QToolButton#shell\\.testExplorer\\.runFailedBtn:pressed,
QToolButton#shell\\.testExplorer\\.refreshBtn:pressed {{
    background: {tokens.tree_selected_bg};
}}
QToolButton#shell\\.testExplorer\\.runAllBtn:disabled,
QToolButton#shell\\.testExplorer\\.runFailedBtn:disabled,
QToolButton#shell\\.testExplorer\\.refreshBtn:disabled {{
    color: {tokens.border};
}}
/* -- filter bar -- */
QWidget#shell\\.testExplorer\\.filterBar {{
    background: {tokens.panel_bg};
    border-bottom: 1px solid {tokens.border};
}}
QToolButton#shell\\.testExplorer\\.filterPassed,
QToolButton#shell\\.testExplorer\\.filterFailed,
QToolButton#shell\\.testExplorer\\.filterSkipped,
QToolButton#shell\\.testExplorer\\.filterErrors {{
    color: {tokens.text_muted};
    background: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 1px 7px;
    font-size: 11px;
}}
QToolButton#shell\\.testExplorer\\.filterPassed:checked {{
    color: {passed_color};
    border-color: {passed_color};
    background: {tokens.row_alt_bg};
}}
QToolButton#shell\\.testExplorer\\.filterFailed:checked {{
    color: {tokens.diag_error_color};
    border-color: {tokens.diag_error_color};
    background: {tokens.row_alt_bg};
}}
QToolButton#shell\\.testExplorer\\.filterSkipped:checked {{
    color: {tokens.text_muted};
    border-color: {tokens.text_muted};
    background: {tokens.row_alt_bg};
}}
QToolButton#shell\\.testExplorer\\.filterErrors:checked {{
    color: {tokens.diag_warning_color};
    border-color: {tokens.diag_warning_color};
    background: {tokens.row_alt_bg};
}}
QToolButton#shell\\.testExplorer\\.filterPassed:hover,
QToolButton#shell\\.testExplorer\\.filterFailed:hover,
QToolButton#shell\\.testExplorer\\.filterSkipped:hover,
QToolButton#shell\\.testExplorer\\.filterErrors:hover {{
    background: {tokens.tree_hover_bg};
}}
/* -- tree -- */
QTreeWidget#shell\\.testExplorer\\.tree {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: none;
    outline: none;
}}
QTreeWidget#shell\\.testExplorer\\.tree::item {{
    padding: 2px 4px;
}}
QTreeWidget#shell\\.testExplorer\\.tree::item:hover {{
    background: {tokens.tree_hover_bg};
}}
QTreeWidget#shell\\.testExplorer\\.tree::item:selected {{
    background: {tokens.tree_selected_bg};
}}
QTreeWidget#shell\\.testExplorer\\.tree::branch {{
    background: transparent;
}}
QTreeWidget#shell\\.testExplorer\\.tree QHeaderView::section {{
    background: {tokens.panel_bg};
    color: {tokens.text_muted};
    border: none;
    border-bottom: 1px solid {tokens.border};
    padding: 2px 6px;
    font-size: 11px;
}}
/* -- status bar -- */
QWidget#shell\\.testExplorer\\.statusBar {{
    background: {tokens.panel_bg};
    border-top: 1px solid {tokens.border};
}}
QLabel#shell\\.testExplorer\\.statusText {{
    color: {tokens.text_muted};
    font-size: 11px;
}}
QLabel#shell\\.testExplorer\\.emptyLabel {{
    color: {tokens.text_muted};
    font-size: 12px;
}}
QLabel#shell\\.testExplorer\\.statusDot {{
    border-radius: 4px;
}}
QLabel#shell\\.testExplorer\\.statusDot[testState="idle"] {{
    background: {tokens.text_muted};
}}
QLabel#shell\\.testExplorer\\.statusDot[testState="pass"] {{
    background: {passed_color};
}}
QLabel#shell\\.testExplorer\\.statusDot[testState="fail"] {{
    background: {tokens.diag_error_color};
}}
QLabel#shell\\.testExplorer\\.statusDot[testState="running"] {{
    background: {tokens.accent};
}}
QLabel#shell\\.testExplorer\\.statusDot[testState="error"] {{
    background: {tokens.diag_warning_color};
}}
QLabel#shell\\.testExplorer\\.countPassed {{
    color: {passed_color};
    font-size: 11px;
    font-weight: bold;
}}
QLabel#shell\\.testExplorer\\.countFailed {{
    color: {tokens.diag_error_color};
    font-size: 11px;
    font-weight: bold;
}}
QLabel#shell\\.testExplorer\\.countSkipped {{
    color: {tokens.text_muted};
    font-size: 11px;
}}
"""

