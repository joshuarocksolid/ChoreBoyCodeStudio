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
QPlainTextEdit#shell\\.bottom\\.console,
QPlainTextEdit#shell\\.bottom\\.runLog {{
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
QListWidget#shell\\.bottom\\.problems {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
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
QLabel#shell\\.projectStatusLabel,
QLabel#shell\\.editorStatusLabel {{
    color: {tokens.text_muted};
    background: transparent;
}}
QWidget#shell\\.toolbar\\.runDebug {{
    background: {tokens.panel_bg};
    border-bottom: 1px solid {tokens.border};
}}
QToolButton#shell\\.toolbar\\.btn {{
    background: transparent;
    color: {tokens.text_primary};
    border: none;
    border-radius: 5px;
    padding: 4px 10px;
    font-size: 12px;
}}
QToolButton#shell\\.toolbar\\.btn:hover {{
    background: {tokens.tree_hover_bg};
}}
QToolButton#shell\\.toolbar\\.btn:pressed {{
    background: {tokens.tree_selected_bg};
}}
QFrame#shell\\.toolbar\\.separator {{
    color: {tokens.border};
}}
QToolButton#shell\\.explorerAction,
QToolButton {{
    color: {tokens.text_primary};
}}
QLabel#shell\\.editor\\.breadcrumbs {{
    color: {tokens.text_muted};
    padding: 2px 4px;
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
    border-bottom: 1px solid {tokens.border};
}}
QLineEdit#shell\\.findBar\\.findInput,
QLineEdit#shell\\.findBar\\.replaceInput {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 3px;
    padding: 3px 6px;
    font-size: 12px;
}}
QLineEdit#shell\\.findBar\\.findInput:focus,
QLineEdit#shell\\.findBar\\.replaceInput:focus {{
    border-color: {tokens.accent};
}}
QLabel#shell\\.findBar\\.matchCount {{
    color: {tokens.text_muted};
    font-size: 11px;
}}
QToolButton#shell\\.findBar\\.prevBtn,
QToolButton#shell\\.findBar\\.nextBtn,
QToolButton#shell\\.findBar\\.caseBtn,
QToolButton#shell\\.findBar\\.wordBtn,
QToolButton#shell\\.findBar\\.regexBtn,
QToolButton#shell\\.findBar\\.closeBtn {{
    background: transparent;
    color: {tokens.text_primary};
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 2px 5px;
    font-size: 11px;
    min-width: 22px;
    min-height: 22px;
}}
QToolButton#shell\\.findBar\\.prevBtn:hover,
QToolButton#shell\\.findBar\\.nextBtn:hover,
QToolButton#shell\\.findBar\\.caseBtn:hover,
QToolButton#shell\\.findBar\\.wordBtn:hover,
QToolButton#shell\\.findBar\\.regexBtn:hover,
QToolButton#shell\\.findBar\\.closeBtn:hover {{
    background: {tokens.tree_hover_bg};
}}
QToolButton#shell\\.findBar\\.caseBtn:checked,
QToolButton#shell\\.findBar\\.wordBtn:checked,
QToolButton#shell\\.findBar\\.regexBtn:checked {{
    background: {tokens.tree_selected_bg};
    border-color: {tokens.accent};
}}
QPushButton#shell\\.findBar\\.replaceBtn,
QPushButton#shell\\.findBar\\.replaceAllBtn {{
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 3px;
    padding: 3px 10px;
    font-size: 11px;
}}
QPushButton#shell\\.findBar\\.replaceBtn:hover,
QPushButton#shell\\.findBar\\.replaceAllBtn:hover {{
    background: {tokens.tree_hover_bg};
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
}}
QLineEdit#shell\\.searchSidebar\\.searchInput,
QLineEdit#shell\\.searchSidebar\\.replaceInput,
QLineEdit#shell\\.searchSidebar\\.includeInput,
QLineEdit#shell\\.searchSidebar\\.excludeInput {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 3px;
    padding: 4px 6px;
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
    color: {tokens.text_primary};
    border: 1px solid transparent;
    border-radius: 3px;
    font-size: 11px;
}}
QToolButton#shell\\.searchSidebar\\.caseBtn:hover,
QToolButton#shell\\.searchSidebar\\.wordBtn:hover,
QToolButton#shell\\.searchSidebar\\.regexBtn:hover {{
    background: {tokens.tree_hover_bg};
}}
QToolButton#shell\\.searchSidebar\\.caseBtn:checked,
QToolButton#shell\\.searchSidebar\\.wordBtn:checked,
QToolButton#shell\\.searchSidebar\\.regexBtn:checked {{
    background: {tokens.tree_selected_bg};
    border-color: {tokens.accent};
}}
QToolButton#shell\\.searchSidebar\\.replaceToggle {{
    background: transparent;
    color: {tokens.text_muted};
    border: none;
    font-size: 11px;
    text-align: left;
    padding: 2px 4px;
}}
QToolButton#shell\\.searchSidebar\\.replaceToggle:hover {{
    color: {tokens.text_primary};
}}
QPushButton#shell\\.searchSidebar\\.replaceAllBtn {{
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 3px;
    padding: 3px 10px;
    font-size: 11px;
}}
QPushButton#shell\\.searchSidebar\\.replaceAllBtn:hover {{
    background: {tokens.tree_hover_bg};
}}
QLabel#shell\\.searchSidebar\\.summary {{
    color: {tokens.text_muted};
    font-size: 11px;
    padding: 2px 0;
}}
QTreeWidget#shell\\.searchSidebar\\.results {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: none;
    border-top: 1px solid {tokens.border};
    outline: none;
    font-size: 12px;
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
"""
