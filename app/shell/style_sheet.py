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
QTreeWidget#shell\\.projectTree,
QPlainTextEdit#shell\\.editorTabs\\.textEditor,
QPlainTextEdit#shell\\.bottom\\.console,
QPlainTextEdit#shell\\.bottom\\.runLog,
QPlainTextEdit#shell\\.bottom\\.pythonConsole\\.output,
QPlainTextEdit#shell\\.bottom\\.debug\\.output {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
}}
QLineEdit#shell\\.bottom\\.pythonConsole\\.input {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    padding: 4px;
}}
QListWidget#shell\\.bottom\\.problems {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
}}
QListWidget#shell\\.bottom\\.debug\\.watchList {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
}}
QStatusBar#shell\\.statusBar {{
    border-top: 1px solid {tokens.border};
}}
QToolBar#shell\\.toolbar\\.runDebug {{
    spacing: 6px;
    border-bottom: 1px solid {tokens.border};
    background: {tokens.panel_bg};
}}
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
