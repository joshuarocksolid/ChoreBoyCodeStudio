"""Stylesheet section builders for run-related shell dialogs."""

from __future__ import annotations

from app.shell.run_dialog_object_names import (
    RUN_CONFIGURATIONS_DIALOG,
    RUN_DIALOG_OBJECT_NAMES,
    RUN_ENV_OVERRIDES_DIALOG,
    RUN_WITH_ARGUMENTS_DIALOG,
    qss_dialog_scope,
    qss_escape_object_name,
)
from app.shell.theme_tokens import ShellThemeTokens


def _dialog_scope(object_names: tuple[str, ...], widget_suffix: str) -> str:
    """Build comma-joined QDialog#id widget selectors."""
    escaped_suffix = widget_suffix.replace(".", "\\.")
    return ",\n".join(
        f"QDialog#{qss_escape_object_name(name)} {escaped_suffix}"
        for name in object_names
    )


def shell_section_run_dialog(tokens: ShellThemeTokens) -> str:
    """Run With Arguments, Run Configurations, and env-overrides table dialogs."""
    muted = tokens.text_muted or tokens.text_primary
    error_color = tokens.diag_error_color or ("#FF6B6B" if tokens.is_dark else "#E03131")
    dialog_selectors = qss_dialog_scope(RUN_DIALOG_OBJECT_NAMES)
    dialog_table_scope = _dialog_scope(RUN_DIALOG_OBJECT_NAMES, "QTableWidget")
    dialog_table_item_scope = _dialog_scope(RUN_DIALOG_OBJECT_NAMES, "QTableWidget::item")
    dialog_table_item_hover_scope = _dialog_scope(
        RUN_DIALOG_OBJECT_NAMES, "QTableWidget::item:hover"
    )
    dialog_header_scope = _dialog_scope(RUN_DIALOG_OBJECT_NAMES, "QHeaderView::section")
    dialog_push_scope = _dialog_scope(RUN_DIALOG_OBJECT_NAMES, "QPushButton")
    dialog_push_hover_scope = _dialog_scope(RUN_DIALOG_OBJECT_NAMES, "QPushButton:hover")
    dialog_push_pressed_scope = _dialog_scope(RUN_DIALOG_OBJECT_NAMES, "QPushButton:pressed")
    dialog_push_disabled_scope = _dialog_scope(RUN_DIALOG_OBJECT_NAMES, "QPushButton:disabled")
    dialog_label_scope = _dialog_scope(RUN_DIALOG_OBJECT_NAMES, "QLabel")
    dialog_combo_scope = _dialog_scope(RUN_DIALOG_OBJECT_NAMES, "QComboBox")
    dialog_combo_hover_scope = _dialog_scope(RUN_DIALOG_OBJECT_NAMES, "QComboBox:hover")
    dialog_combo_dropdown_scope = _dialog_scope(RUN_DIALOG_OBJECT_NAMES, "QComboBox::drop-down")
    dialog_combo_view_scope = _dialog_scope(RUN_DIALOG_OBJECT_NAMES, "QComboBox QAbstractItemView")
    dialog_disabled_input_scope = ",\n".join(
        _dialog_scope(RUN_DIALOG_OBJECT_NAMES, widget)
        for widget in ("QLineEdit:disabled", "QComboBox:disabled", "QPlainTextEdit:disabled")
    )
    run_args = qss_escape_object_name(RUN_WITH_ARGUMENTS_DIALOG)
    run_configs = qss_escape_object_name(RUN_CONFIGURATIONS_DIALOG)
    run_env = qss_escape_object_name(RUN_ENV_OVERRIDES_DIALOG)
    return f"""/* -- Run dialogs (arguments / configurations / env) -------------------- */
{dialog_selectors} {{
    background: {tokens.window_bg};
    color: {tokens.text_primary};
}}
QLabel#shell\\.runWithArgumentsDialog\\.commandPreview,
QLabel#shell\\.runConfigurationsDialog\\.commandPreview {{
    background: {tokens.input_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 12px;
}}
QLabel#shell\\.runWithArgumentsDialog\\.commandPreview[commandPreviewState="incomplete"],
QLabel#shell\\.runWithArgumentsDialog\\.commandPreview[commandPreviewState="error"] {{
    color: {muted};
}}
QLabel#shell\\.runWithArgumentsDialog\\.commandPreview[commandPreviewState="error"] {{
    border-left: 3px solid {error_color};
    padding-left: 10px;
}}
QLabel#shell\\.runWithArgumentsDialog\\.commandPreview[commandPreviewState="ready"] {{
    font-family: monospace;
}}
QLabel#shell\\.runWithArgumentsDialog\\.error,
QLabel#shell\\.runConfigurationsDialog\\.error {{
    color: {error_color};
    font-size: 12px;
}}
QLabel[previewLabel="true"] {{
    color: {muted};
    font-size: 11px;
}}
QLabel[previewLabel="true"][previewState="error"] {{
    color: {error_color};
}}
QLabel[quotingHint="true"] {{
    color: {tokens.accent};
    font-size: 11px;
    font-weight: 600;
}}
QLabel[formSectionTitle="true"] {{
    color: {muted};
    font-size: 12px;
    font-weight: 600;
}}
QLabel[overridesSummary="true"] {{
    color: {muted};
    font-size: 11px;
}}
QLabel[envCountChip="true"] {{
    background: {tokens.badge_bg};
    color: {muted};
    padding: 3px 8px;
    border-radius: 9px;
    font-size: 10px;
    font-weight: 600;
}}
QToolButton[overridesToggle="true"] {{
    background: transparent;
    border: none;
    color: {tokens.text_primary};
    padding: 2px;
}}
QToolButton[overridesToggle="true"]:hover {{
    color: {tokens.accent};
}}
QWidget#shell\\.runWithArgumentsDialog\\.advancedGroup {{
    border: 1px solid {tokens.border};
    border-radius: 6px;
    padding: 12px 10px 10px 10px;
    background: {tokens.panel_bg};
}}
QFrame#shell\\.runWithArgumentsDialog\\.footerSeparator {{
    color: {tokens.border};
    max-width: 1px;
}}
QPushButton[fieldAction="true"] {{
    background: {tokens.input_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
}}
QPushButton[fieldAction="true"]:hover {{
    background: {tokens.tree_hover_bg};
    border-color: {tokens.accent};
    color: {tokens.accent};
}}
QPushButton[fieldAction="true"]:pressed {{
    background: {tokens.tree_selected_bg};
}}
QPushButton[fieldAction="true"]:disabled {{
    background: {tokens.panel_bg};
    color: {muted};
    border-color: {tokens.border};
}}
QDialog#{run_args} QFormLayout QLabel,
QDialog#{run_configs} QFormLayout QLabel {{
    color: {muted};
    font-size: 12px;
    font-weight: 600;
    background: transparent;
}}
QDialog#{run_args} QLineEdit[validationState="error"],
QDialog#{run_args} QComboBox[validationState="error"],
QDialog#{run_args} QPlainTextEdit[validationState="error"],
QDialog#{run_configs} QLineEdit[validationState="error"],
QDialog#{run_configs} QComboBox[validationState="error"],
QDialog#{run_configs} QPlainTextEdit[validationState="error"] {{
    border-color: {error_color};
}}
QGroupBox#shell\\.runWithArgumentsDialog\\.advancedGroup {{
    border: 1px solid {tokens.border};
    border-radius: 6px;
    margin-top: 12px;
    padding: 12px 10px 10px 10px;
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
}}
QGroupBox#shell\\.runConfigurationsDialog\\.defaultArgvGroup,
QGroupBox#shell\\.runConfigurationsDialog\\.configsGroup {{
    border: 1px solid {tokens.border};
    border-left: 3px solid {tokens.accent};
    border-radius: 6px;
    margin-top: 12px;
    padding: 12px 10px 10px 10px;
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
}}
QGroupBox#shell\\.runWithArgumentsDialog\\.advancedGroup::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {muted};
}}
QGroupBox#shell\\.runConfigurationsDialog\\.defaultArgvGroup::title,
QGroupBox#shell\\.runConfigurationsDialog\\.configsGroup::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {tokens.text_primary};
    font-weight: 600;
}}
QGroupBox#shell\\.runWithArgumentsDialog\\.advancedGroup::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {tokens.border};
    border-radius: 3px;
    background: {tokens.input_bg};
}}
QGroupBox#shell\\.runWithArgumentsDialog\\.advancedGroup::indicator:checked {{
    background: {tokens.accent};
    border-color: {tokens.accent};
}}
QGroupBox#shell\\.runWithArgumentsDialog\\.advancedGroup::indicator:disabled {{
    background: {tokens.panel_bg};
    border-color: {tokens.border};
}}
{dialog_label_scope} {{
    color: {tokens.text_primary};
    font-size: 12px;
    background: transparent;
}}
{dialog_push_scope} {{
    background: {tokens.input_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 5px;
    padding: 5px 14px;
    font-size: 12px;
    font-weight: 600;
}}
{dialog_push_hover_scope} {{
    background: {tokens.tree_hover_bg};
    border-color: {tokens.accent};
    color: {tokens.accent};
}}
{dialog_push_pressed_scope} {{
    background: {tokens.tree_selected_bg};
}}
{dialog_push_disabled_scope} {{
    background: {tokens.panel_bg};
    color: {muted};
    border-color: {tokens.border};
}}
{dialog_combo_scope} {{
    padding: 6px 24px 6px 8px;
    font-size: 12px;
    min-height: 20px;
}}
{dialog_combo_hover_scope} {{
    border-color: {tokens.accent};
}}
{dialog_combo_dropdown_scope} {{
    border: none;
    width: 20px;
}}
{dialog_combo_view_scope} {{
    background: {tokens.panel_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    selection-background-color: {tokens.tree_selected_bg};
    selection-color: {tokens.text_primary};
    outline: none;
}}
{dialog_disabled_input_scope} {{
    background: {tokens.panel_bg};
    color: {muted};
    border-color: {tokens.border};
}}
QDialog#{run_args} QLineEdit,
QDialog#{run_args} QComboBox,
QDialog#{run_args} QPlainTextEdit,
QDialog#{run_configs} QLineEdit,
QDialog#{run_configs} QComboBox,
QDialog#{run_configs} QPlainTextEdit {{
    background: {tokens.input_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 5px;
    padding: 6px 8px;
}}
QDialog#{run_args} QLineEdit:focus,
QDialog#{run_args} QComboBox:focus,
QDialog#{run_args} QPlainTextEdit:focus,
QDialog#{run_configs} QLineEdit:focus,
QDialog#{run_configs} QComboBox:focus,
QDialog#{run_configs} QPlainTextEdit:focus {{
    border-color: {tokens.accent};
    border-width: {tokens.focus_border_width}px;
}}
QScrollArea#shell\\.runWithArgumentsDialog\\.formScroll {{
    background: transparent;
    border: none;
}}
QScrollArea#shell\\.runWithArgumentsDialog\\.formScroll > QWidget {{
    background: transparent;
}}
QWidget#shell\\.runWithArgumentsDialog\\.formScrollContent {{
    background: transparent;
}}
QScrollArea#shell\\.runConfigurationsDialog\\.configsDetailScroll {{
    background: transparent;
    border: none;
}}
QScrollArea#shell\\.runConfigurationsDialog\\.configsDetailScroll > QWidget {{
    background: transparent;
}}
QWidget#shell\\.runConfigurationsDialog\\.configsDetailForm {{
    background: transparent;
}}
QDialog#{run_args} QScrollBar:vertical,
QDialog#{run_configs} QScrollBar:vertical {{
    width: 6px;
    background: transparent;
    margin: 2px 1px;
}}
QDialog#{run_args} QScrollBar::handle:vertical,
QDialog#{run_configs} QScrollBar::handle:vertical {{
    background: {muted};
    border-radius: 3px;
    min-height: 20px;
}}
QDialog#{run_args} QScrollBar::add-line:vertical,
QDialog#{run_args} QScrollBar::sub-line:vertical,
QDialog#{run_configs} QScrollBar::add-line:vertical,
QDialog#{run_configs} QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QDialog#{run_args} QScrollBar::add-page:vertical,
QDialog#{run_args} QScrollBar::sub-page:vertical,
QDialog#{run_configs} QScrollBar::add-page:vertical,
QDialog#{run_configs} QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QDialog#{run_env} QTableWidget QLineEdit {{
    background: {tokens.input_bg};
    color: {tokens.text_primary};
    padding: 0 4px;
    border: none;
    border-radius: 0;
}}
QDialog#{run_env} QTableWidget QLineEdit:focus {{
    border: none;
    outline: none;
}}
QLineEdit[envSummary="true"][readOnly="true"] {{
    background: {tokens.input_bg};
    color: {tokens.text_primary};
}}
QLabel#shell\\.runConfigurationsDialog\\.defaultEntryLabel,
QLabel#shell\\.runConfigurationsDialog\\.emptyState {{
    color: {muted};
}}
QDialog#{run_configs} QWidget#shell\\.dialogChrome\\.metaRow QLabel[metaChip="true"] {{
    background: {tokens.badge_bg};
    color: {tokens.accent};
    padding: 3px 9px;
    border-radius: 9px;
    font-size: 11px;
    font-weight: 600;
}}
QWidget#shell\\.runConfigurationsDialog\\.configsDetailPanel {{
    background: {tokens.line_highlight};
    border: 1px solid {tokens.border};
    border-radius: 6px;
}}
QListWidget#shell\\.runConfigurationsDialog\\.list {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 4px;
    outline: none;
    font-size: 12px;
}}
QListWidget#shell\\.runConfigurationsDialog\\.list::item {{
    padding: 6px 8px;
    border-bottom: 1px solid {tokens.border};
}}
QListWidget#shell\\.runConfigurationsDialog\\.list::item:last {{
    border-bottom: none;
}}
QListWidget#shell\\.runConfigurationsDialog\\.list::item:hover {{
    background: {tokens.tree_hover_bg};
}}
QListWidget#shell\\.runConfigurationsDialog\\.list::item:selected {{
    background: {tokens.tree_selected_bg};
    color: {tokens.text_primary};
    border-left: 3px solid {tokens.accent};
    padding-left: 5px;
}}
QPushButton#shell\\.runConfigurationsDialog\\.addButton {{
    background: {tokens.input_bg};
    color: {tokens.accent};
    border: 1px solid {tokens.accent};
    border-radius: 5px;
    padding: 5px 10px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#shell\\.runConfigurationsDialog\\.addButton:hover {{
    background: {tokens.tree_selected_bg};
    border-color: {tokens.accent};
    color: {tokens.accent};
}}
QPushButton#shell\\.runConfigurationsDialog\\.duplicateButton,
QPushButton#shell\\.runConfigurationsDialog\\.deleteButton {{
    background: {tokens.input_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 5px;
    padding: 5px 10px;
    font-size: 12px;
}}
QPushButton#shell\\.runConfigurationsDialog\\.duplicateButton:hover,
QPushButton#shell\\.runConfigurationsDialog\\.deleteButton:hover {{
    background: {tokens.tree_hover_bg};
    border-color: {tokens.accent};
}}
{dialog_table_scope} {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: 1px solid {tokens.border};
    border-radius: 4px;
    gridline-color: {tokens.border};
    alternate-background-color: {tokens.row_alt_bg};
    outline: none;
    font-size: 12px;
}}
{dialog_table_item_scope} {{
    padding: 4px 8px;
}}
{dialog_table_item_hover_scope} {{
    background: {tokens.tree_hover_bg};
}}
{dialog_header_scope} {{
    background: {tokens.panel_bg};
    color: {muted};
    border: none;
    border-bottom: 1px solid {tokens.border};
    border-right: 1px solid {tokens.border};
    padding: 6px 8px;
    font-size: 11px;
    font-weight: 600;
}}
"""
