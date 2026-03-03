"""Shell stylesheet generation."""

from __future__ import annotations

from app.shell.theme_tokens import ShellThemeTokens


def build_shell_style_sheet(tokens: ShellThemeTokens) -> str:
    """Return stylesheet string for shell components."""
    return f"""
QMainWindow#shell\\.mainWindow {{
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
QWidget#shell\\.leftRegion,
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
/* -- Run Log panel ------------------------------------------------------ */
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
/* -- Problems panel (VS Code-style) ------------------------------------ */
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
/* -- Debug panel -------------------------------------------------------- */
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
QLabel#shell\\.leftRegion\\.title {{
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
/* -- Default toolbar button style --------------------------------------- */
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
QToolButton#shell\\.explorerAction,
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
/* -- Welcome screen ------------------------------------------------------ */
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
/* -- Find/Replace bar ---------------------------------------------------- */
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
/* -- Quick Open dialog --------------------------------------------------- */
QDialog#shell\\.quickOpen {{
    background: {tokens.panel_bg};
    border: 1px solid {tokens.border};
    border-radius: 6px;
}}
QLineEdit#shell\\.quickOpen\\.input {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: none;
    border-bottom: 1px solid {tokens.border};
    padding: 8px 12px;
    font-size: 13px;
}}
QListWidget#shell\\.quickOpen\\.results {{
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
    border: none;
    outline: none;
    font-size: 12px;
}}
QListWidget#shell\\.quickOpen\\.results::item {{
    padding: 4px 12px;
}}
QListWidget#shell\\.quickOpen\\.results::item:hover {{
    background: {tokens.tree_hover_bg};
}}
QListWidget#shell\\.quickOpen\\.results::item:selected {{
    background: {tokens.tree_selected_bg};
    color: {tokens.text_primary};
}}
/* -- Activity bar -------------------------------------------------------- */
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
/* -- Search sidebar ------------------------------------------------------ */
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
/* -- Help dialog --------------------------------------------------------- */
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
