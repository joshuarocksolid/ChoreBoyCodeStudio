"""Stylesheet section builders for a focused shell UI area."""

from __future__ import annotations

from app.shell.theme_tokens import ShellThemeTokens


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
def shell_section_outline_panel(tokens: ShellThemeTokens) -> str:
    return f"""/* -- Outline panel (VS Code-style) ------------------------------------- */
QWidget#shell\\.outlinePanel {{
    background: {tokens.panel_bg};
}}
QWidget#shell\\.outlinePanel\\.header {{
    background: {tokens.panel_bg};
    border-top: 1px solid {tokens.border};
    border-bottom: 1px solid {tokens.border};
    min-height: 28px;
    padding: 2px 4px;
}}
QWidget#shell\\.outlinePanel\\.header[collapsed="true"] {{
    background: {tokens.tree_hover_bg};
    border-top: 1px solid {tokens.accent};
    border-bottom: 1px solid {tokens.border};
}}
QWidget#shell\\.outlinePanel\\.header:hover {{
    background: {tokens.tree_hover_bg};
}}
QLabel#shell\\.outlinePanel\\.title {{
    color: {tokens.text_muted};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.6px;
    padding-left: 2px;
}}
QLabel#shell\\.outlinePanel\\.fileLabel {{
    color: {tokens.text_muted};
    font-size: 11px;
    padding-left: 4px;
}}
QToolButton#shell\\.outlinePanel\\.chevron {{
    background: transparent;
    border: none;
    padding: 1px;
    margin: 0px;
}}
QToolButton#shell\\.outlinePanel\\.chevron:hover {{
    background: transparent;
}}
QToolButton#shell\\.outlinePanel\\.action\\.filter,
QToolButton#shell\\.outlinePanel\\.action\\.follow,
QToolButton#shell\\.outlinePanel\\.action\\.sort,
QToolButton#shell\\.outlinePanel\\.action\\.collapseAll,
QToolButton#shell\\.outlinePanel\\.action\\.more {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 2px;
    margin: 0px 1px;
    color: {tokens.text_muted};
}}
QToolButton#shell\\.outlinePanel\\.action\\.filter:hover,
QToolButton#shell\\.outlinePanel\\.action\\.follow:hover,
QToolButton#shell\\.outlinePanel\\.action\\.sort:hover,
QToolButton#shell\\.outlinePanel\\.action\\.collapseAll:hover,
QToolButton#shell\\.outlinePanel\\.action\\.more:hover {{
    background: {tokens.tree_selected_bg};
    color: {tokens.text_primary};
}}
QToolButton#shell\\.outlinePanel\\.action\\.filter:checked,
QToolButton#shell\\.outlinePanel\\.action\\.follow:checked {{
    background: {tokens.tree_selected_bg};
    color: {tokens.accent};
    border-color: {tokens.accent};
}}
QToolButton#shell\\.outlinePanel\\.action\\.sort::menu-indicator,
QToolButton#shell\\.outlinePanel\\.action\\.more::menu-indicator {{
    image: none;
    width: 0px;
}}
QWidget#shell\\.outlinePanel\\.filterRow {{
    background: {tokens.panel_bg};
    border-bottom: 1px solid {tokens.border};
}}
QLineEdit#shell\\.outlinePanel\\.filter {{
    background: {tokens.input_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 3px;
    padding: 3px 6px;
    font-size: 11px;
    selection-background-color: {tokens.accent};
}}
QLineEdit#shell\\.outlinePanel\\.filter:focus {{
    border-color: {tokens.accent};
    border-width: {tokens.focus_border_width}px;
}}
QWidget#shell\\.outlinePanel\\.body {{
    background: {tokens.panel_bg};
}}
QTreeWidget#shell\\.outlinePanel\\.tree {{
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
    border: none;
    outline: none;
    show-decoration-selected: 1;
}}
QTreeWidget#shell\\.outlinePanel\\.tree::item {{
    padding: 2px 4px;
    border: 0px;
}}
QTreeWidget#shell\\.outlinePanel\\.tree::item:hover {{
    background: {tokens.tree_hover_bg};
}}
QTreeWidget#shell\\.outlinePanel\\.tree::item:selected {{
    background: {tokens.tree_selected_bg};
    color: {tokens.text_primary};
}}
QTreeWidget#shell\\.outlinePanel\\.tree::item:selected:!active {{
    background: {tokens.tree_selected_bg};
    color: {tokens.text_primary};
}}
QTreeWidget#shell\\.outlinePanel\\.tree::branch {{
    background: transparent;
}}
QTreeWidget#shell\\.outlinePanel\\.tree QHeaderView::section {{
    background: {tokens.panel_bg};
    color: {tokens.text_muted};
    border: none;
    border-bottom: 1px solid {tokens.border};
    padding: 2px 6px;
    font-size: 11px;
}}
QLabel#shell\\.outlinePanel\\.emptyLabel {{
    color: {tokens.text_muted};
    font-size: 12px;
    padding: 8px;
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
    border-width: {tokens.focus_border_width}px;
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
    border-width: {tokens.focus_border_width}px;
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
