"""Stylesheet section builders for a focused shell UI area."""

from __future__ import annotations

from app.shell.theme_tokens import ShellThemeTokens


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
