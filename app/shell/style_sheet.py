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
"""
