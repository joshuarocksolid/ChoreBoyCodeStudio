"""Stylesheet section builders for a focused shell UI area."""

from __future__ import annotations

from app.shell.theme_tokens import ShellThemeTokens


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
QWidget#shell\\.markdownEditorPane {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
}}
QWidget#shell\\.markdownEditorPane\\.toolbar {{
    background: {tokens.panel_bg};
    border-left: 1px solid {tokens.border};
    border-right: 1px solid {tokens.border};
    border-bottom: 1px solid {tokens.border};
}}
QLabel#shell\\.markdownEditorPane\\.title {{
    color: {tokens.text_muted};
    font-size: 11px;
    font-weight: 700;
    padding-right: 8px;
}}
QLabel#shell\\.markdownEditorPane\\.status {{
    color: {tokens.text_muted};
    font-size: 11px;
    padding-left: 6px;
}}
QToolButton#shell\\.markdownEditorPane\\.modeButton,
QToolButton#shell\\.markdownEditorPane\\.refreshButton {{
    background: transparent;
    color: {tokens.text_muted};
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 11px;
}}
QToolButton#shell\\.markdownEditorPane\\.modeButton:hover,
QToolButton#shell\\.markdownEditorPane\\.refreshButton:hover {{
    background: {tokens.tree_hover_bg};
    color: {tokens.text_primary};
    border-color: {tokens.border};
}}
QToolButton#shell\\.markdownEditorPane\\.modeButton:checked {{
    background: {tokens.tree_selected_bg};
    color: {tokens.text_primary};
    border-color: {tokens.accent};
}}
QSplitter#shell\\.markdownEditorPane\\.splitter::handle {{
    background: {tokens.border};
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
