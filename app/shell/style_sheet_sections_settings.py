"""Stylesheet section builders for a focused shell UI area."""

from __future__ import annotations

from app.shell.theme_tokens import ShellThemeTokens


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
/* Qt's internal viewport child of the General-tab scroll area */
QScrollArea#shell\\.settingsDialog\\.generalScroll > QWidget {{
    background: {tokens.panel_bg};
}}
/* The user-supplied content widget set via QScrollArea.setWidget(...) */
QWidget#shell\\.settingsDialog\\.generalScrollContent {{
    background: {tokens.panel_bg};
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
