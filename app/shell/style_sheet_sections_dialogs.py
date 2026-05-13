"""Stylesheet section builders for a focused shell UI area."""

from __future__ import annotations

from app.shell.theme_tokens import ShellThemeTokens


def _accent_hover(tokens: ShellThemeTokens) -> str:
    return "#4D7AFF" if tokens.is_dark else "#2952CC"


def _accent_pressed(tokens: ShellThemeTokens) -> str:
    return "#3D6AEE" if tokens.is_dark else "#1F3FA6"


def _destructive_color(tokens: ShellThemeTokens) -> str:
    return tokens.diag_error_color or ("#FF6B6B" if tokens.is_dark else "#E03131")


def shell_section_dialog_chrome(tokens: ShellThemeTokens) -> str:
    """Generic chrome (header / body / footer / buttons) for shell dialogs."""
    accent_hover = _accent_hover(tokens)
    accent_pressed = _accent_pressed(tokens)
    destructive = _destructive_color(tokens)
    return f"""/* -- Dialog chrome (shared header/body/footer) --------------------------- */
QWidget#shell\\.dialogChrome\\.header {{
    background: {tokens.panel_bg};
    border-bottom: 1px solid {tokens.border};
}}
QLabel#shell\\.dialogChrome\\.title {{
    color: {tokens.text_primary};
    font-size: 17px;
    font-weight: 700;
}}
QLabel#shell\\.dialogChrome\\.subtitle {{
    color: {tokens.text_muted};
    font-size: 12px;
}}
QWidget#shell\\.dialogChrome\\.metaRow QLabel[metaChip="true"] {{
    background: {tokens.badge_bg};
    color: {tokens.text_muted};
    padding: 3px 9px;
    border-radius: 9px;
    font-size: 11px;
    font-weight: 600;
}}
QWidget#shell\\.dialogChrome\\.body {{
    background: {tokens.window_bg};
}}
QWidget#shell\\.dialogChrome\\.footer {{
    background: {tokens.panel_bg};
    border-top: 1px solid {tokens.border};
}}
QPushButton#shell\\.dialogChrome\\.button\\.primary {{
    background: {tokens.accent};
    color: #FFFFFF;
    border: none;
    border-radius: 5px;
    padding: 7px 16px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#shell\\.dialogChrome\\.button\\.primary:hover {{
    background: {accent_hover};
}}
QPushButton#shell\\.dialogChrome\\.button\\.primary:pressed {{
    background: {accent_pressed};
}}
QPushButton#shell\\.dialogChrome\\.button\\.primary:disabled {{
    background: {tokens.badge_bg};
    color: {tokens.text_muted};
}}
QPushButton#shell\\.dialogChrome\\.button\\.secondary {{
    background: {tokens.input_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 5px;
    padding: 7px 14px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#shell\\.dialogChrome\\.button\\.secondary:hover {{
    background: {tokens.tree_hover_bg};
    border-color: {tokens.accent};
}}
QPushButton#shell\\.dialogChrome\\.button\\.secondary:pressed {{
    background: {tokens.tree_selected_bg};
}}
QPushButton#shell\\.dialogChrome\\.button\\.destructiveSecondary {{
    background: {tokens.input_bg};
    color: {destructive};
    border: 1px solid {tokens.border};
    border-radius: 5px;
    padding: 7px 14px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#shell\\.dialogChrome\\.button\\.destructiveSecondary:hover {{
    background: {tokens.tree_hover_bg};
    border-color: {destructive};
}}
QPushButton#shell\\.dialogChrome\\.button\\.destructiveSecondary:pressed {{
    background: {tokens.tree_selected_bg};
}}
QPushButton#shell\\.dialogChrome\\.button\\.link {{
    background: transparent;
    color: {tokens.accent};
    border: none;
    padding: 6px 4px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#shell\\.dialogChrome\\.button\\.link:hover {{
    color: {accent_hover};
    text-decoration: underline;
}}

/* -- Diff view (shared) -------------------------------------------------- */
QWidget#shell\\.diffView {{
    background: {tokens.window_bg};
}}
QLabel#shell\\.diffView\\.paneLabel {{
    color: {tokens.text_muted};
}}
QLabel#shell\\.diffView\\.message {{
    color: {tokens.text_muted};
    font-size: 13px;
    background: {tokens.panel_bg};
    border: 1px dashed {tokens.border};
    border-radius: 6px;
}}
QSplitter#shell\\.diffView\\.splitter::handle {{
    background: {tokens.border};
    width: 1px;
}}

/* -- Segmented mode toolbar (Inline / Side-by-side) ---------------------- */
QToolButton[modeButton="true"] {{
    background: {tokens.input_bg};
    color: {tokens.text_muted};
    border: 1px solid {tokens.border};
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 600;
    border-radius: 0;
}}
QToolButton[modeButton="true"]:first-child {{
    border-top-left-radius: 5px;
    border-bottom-left-radius: 5px;
}}
QToolButton[modeButton="true"]:last-child {{
    border-top-right-radius: 5px;
    border-bottom-right-radius: 5px;
    border-left: none;
}}
QToolButton[modeButton="true"]:hover {{
    background: {tokens.tree_hover_bg};
    color: {tokens.text_primary};
}}
QToolButton[modeButton="true"]:checked {{
    background: {tokens.tree_selected_bg};
    color: {tokens.text_primary};
    border-color: {tokens.accent};
}}
QToolButton[modeButton="true"]:disabled {{
    color: {tokens.text_muted};
    background: {tokens.input_bg};
}}
"""


def shell_section_unsaved_changes_dialog(tokens: ShellThemeTokens) -> str:
    """Targeted overrides for the unsaved-changes prompt surface."""
    warning_color = tokens.diag_warning_color or ("#F59F00" if tokens.is_dark else "#E08E00")
    return f"""/* -- Unsaved changes dialog --------------------------------------------- */
QDialog#shell\\.unsavedChangesDialog {{
    background: {tokens.window_bg};
    color: {tokens.text_primary};
}}
QDialog#shell\\.unsavedChangesDialog QLabel#shell\\.dialogChrome\\.icon {{
    background: transparent;
}}
QDialog#shell\\.unsavedChangesDialog QWidget#shell\\.dialogChrome\\.metaRow QLabel[metaChip="true"] {{
    background: {tokens.badge_bg};
    color: {warning_color};
}}
QListWidget#shell\\.unsavedChangesDialog\\.fileList {{
    background: {tokens.editor_bg};
    border: 1px solid {tokens.border};
    border-radius: 6px;
    padding: 4px;
    outline: none;
}}
QListWidget#shell\\.unsavedChangesDialog\\.fileList::item {{
    border: none;
    padding: 0;
    margin: 1px 0;
}}
QWidget#shell\\.unsavedChangesDialog\\.row {{
    background: transparent;
    border-radius: 4px;
}}
QListWidget#shell\\.unsavedChangesDialog\\.fileList::item:hover QWidget#shell\\.unsavedChangesDialog\\.row {{
    background: {tokens.tree_hover_bg};
}}
QLabel#shell\\.unsavedChangesDialog\\.row\\.name {{
    color: {tokens.text_primary};
    font-size: 13px;
    font-weight: 600;
}}
QLabel#shell\\.unsavedChangesDialog\\.row\\.path {{
    color: {tokens.text_muted};
    font-size: 11px;
}}
QListWidget#shell\\.unsavedChangesDialog\\.fileList QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px 0;
}}
QListWidget#shell\\.unsavedChangesDialog\\.fileList QScrollBar::handle:vertical {{
    background: {tokens.border};
    border-radius: 4px;
    min-height: 24px;
}}
QListWidget#shell\\.unsavedChangesDialog\\.fileList QScrollBar::handle:vertical:hover {{
    background: {tokens.text_muted};
}}
QListWidget#shell\\.unsavedChangesDialog\\.fileList QScrollBar::add-line:vertical,
QListWidget#shell\\.unsavedChangesDialog\\.fileList QScrollBar::sub-line:vertical {{
    height: 0;
    background: transparent;
    border: none;
}}
QListWidget#shell\\.unsavedChangesDialog\\.fileList QScrollBar::add-page:vertical,
QListWidget#shell\\.unsavedChangesDialog\\.fileList QScrollBar::sub-page:vertical {{
    background: transparent;
}}
"""


def shell_section_draft_recovery_dialog(tokens: ShellThemeTokens) -> str:
    """Targeted overrides for the recovery-draft dialog surface."""
    return f"""/* -- Draft recovery dialog ---------------------------------------------- */
QDialog#shell\\.draftRecoveryDialog {{
    background: {tokens.window_bg};
    color: {tokens.text_primary};
}}
QDialog#shell\\.localHistoryDialog {{
    background: {tokens.window_bg};
    color: {tokens.text_primary};
}}
QTreeWidget#shell\\.localHistoryDialog\\.revisionTree {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 6px;
    alternate-background-color: {tokens.row_alt_bg};
}}
QTreeWidget#shell\\.localHistoryDialog\\.revisionTree::item {{
    padding: 4px 6px;
}}
QTreeWidget#shell\\.localHistoryDialog\\.revisionTree::item:hover {{
    background: {tokens.tree_hover_bg};
}}
QTreeWidget#shell\\.localHistoryDialog\\.revisionTree::item:selected {{
    background: {tokens.tree_selected_bg};
    color: {tokens.text_primary};
}}
QLabel#shell\\.localHistoryDialog\\.compareLabel {{
    color: {tokens.text_muted};
    font-size: 12px;
    font-weight: 600;
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
    border-width: {tokens.focus_border_width}px;
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
