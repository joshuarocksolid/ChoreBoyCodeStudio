"""General tab builder and state helpers for SettingsDialog."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide2.QtGui import QFont
from PySide2.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QFontComboBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core import constants
from app.shell.settings_dialog_state import GeneralTabState
from app.shell.settings_models import EditorSettingsSnapshot

if TYPE_CHECKING:
    from app.shell.settings_dialog import SettingsDialog


def build_general_tab(
    dialog: "SettingsDialog",
    tabs: QTabWidget,
    snapshot: EditorSettingsSnapshot,
    *,
    python_tooling_runtime_text: str,
    python_tooling_runtime_details: str,
    python_tooling_config_text: str,
    python_tooling_config_details: str,
) -> None:
    general_tab = QWidget(tabs)
    general_tab_layout = QVBoxLayout(general_tab)
    general_tab_layout.setContentsMargins(0, 0, 0, 0)
    tabs.addTab(general_tab, "General")
    scroll_area = QScrollArea(general_tab)
    scroll_area.setWidgetResizable(True)
    scroll_area.setObjectName("shell.settingsDialog.generalScroll")
    scroll_content = QWidget()
    scroll_content.setObjectName("shell.settingsDialog.generalScrollContent")
    general_layout = QVBoxLayout(scroll_content)
    general_layout.setContentsMargins(16, 12, 16, 12)
    general_layout.setSpacing(4)

    appearance_group = QGroupBox("Appearance")
    appearance_group.setObjectName("shell.settingsDialog.appearanceGroup")
    dialog._appearance_group = appearance_group
    appearance_form = QFormLayout(appearance_group)
    appearance_form.setVerticalSpacing(10)
    appearance_form.setHorizontalSpacing(16)
    dialog._theme_mode_input = QComboBox(appearance_group)
    for label, value in (
        ("System", constants.UI_THEME_MODE_SYSTEM),
        ("Light", constants.UI_THEME_MODE_LIGHT),
        ("Dark", constants.UI_THEME_MODE_DARK),
        ("High Contrast Light", constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT),
        ("High Contrast Dark", constants.UI_THEME_MODE_HIGH_CONTRAST_DARK),
    ):
        dialog._theme_mode_input.addItem(label, value)
    theme_index = dialog._theme_mode_input.findData(snapshot.theme_mode)
    dialog._theme_mode_input.setCurrentIndex(theme_index if theme_index >= 0 else 0)
    dialog._theme_mode_input.setToolTip(
        "High Contrast variants target WCAG AAA contrast for accessibility."
    )
    appearance_form.addRow("Theme", dialog._theme_mode_input)

    dialog._ui_font_weight_input = QComboBox(appearance_group)
    for label, value in (
        ("Normal", constants.UI_THEME_FONT_WEIGHT_NORMAL),
        ("Medium", constants.UI_THEME_FONT_WEIGHT_MEDIUM),
        ("Bold", constants.UI_THEME_FONT_WEIGHT_BOLD),
    ):
        dialog._ui_font_weight_input.addItem(label, value)
    weight_index = dialog._ui_font_weight_input.findData(snapshot.ui_font_weight)
    dialog._ui_font_weight_input.setCurrentIndex(weight_index if weight_index >= 0 else 0)
    dialog._ui_font_weight_input.setToolTip(
        "Adjust the weight of menus, panels, and dialogs. The code editor font is unaffected."
    )
    appearance_form.addRow("UI font weight", dialog._ui_font_weight_input)

    dialog._dark_chrome_palette_input = QComboBox(appearance_group)
    for label, value in (
        ("Standard (blue-tinted dark)", constants.UI_THEME_DARK_CHROME_PALETTE_STANDARD),
        ("Neutral gray dark", constants.UI_THEME_DARK_CHROME_PALETTE_NEUTRAL_GRAY),
    ):
        dialog._dark_chrome_palette_input.addItem(label, value)
    palette_index = dialog._dark_chrome_palette_input.findData(snapshot.dark_chrome_palette)
    dialog._dark_chrome_palette_input.setCurrentIndex(palette_index if palette_index >= 0 else 0)
    dialog._dark_chrome_palette_input.setToolTip(
        "Chrome surface colors when Theme is Dark or System resolves to dark. "
        "No effect in Light or High Contrast modes."
    )
    appearance_form.addRow("Dark chrome palette", dialog._dark_chrome_palette_input)
    general_layout.addWidget(appearance_group)

    output_group = QGroupBox("Output")
    output_group.setObjectName("shell.settingsDialog.outputGroup")
    output_form = QFormLayout(output_group)
    output_form.setVerticalSpacing(10)
    output_form.setHorizontalSpacing(16)
    dialog._auto_open_console_on_run_output_input = QCheckBox(output_group)
    dialog._auto_open_console_on_run_output_input.setChecked(snapshot.auto_open_console_on_run_output)
    output_form.addRow("Auto-open Run Log on run output", dialog._auto_open_console_on_run_output_input)
    dialog._auto_open_problems_on_run_failure_input = QCheckBox(output_group)
    dialog._auto_open_problems_on_run_failure_input.setChecked(snapshot.auto_open_problems_on_run_failure)
    output_form.addRow("Auto-open Problems on run failure", dialog._auto_open_problems_on_run_failure_input)
    dialog._output_reset_to_global_btn = QPushButton("Reset Output Overrides to Global", output_group)
    dialog._output_reset_to_global_btn.setObjectName("shell.settingsDialog.outputResetGlobal")
    dialog._output_reset_to_global_btn.clicked.connect(dialog._handle_reset_output_group_to_global)
    output_form.addRow("", dialog._output_reset_to_global_btn)
    general_layout.addWidget(output_group)

    editor_group = QGroupBox("Editor")
    editor_group.setObjectName("shell.settingsDialog.editorGroup")
    editor_form = QFormLayout(editor_group)
    editor_form.setVerticalSpacing(10)
    editor_form.setHorizontalSpacing(16)
    dialog._tab_width_input = QSpinBox(editor_group)
    dialog._tab_width_input.setRange(2, 16)
    dialog._tab_width_input.setValue(snapshot.tab_width)
    editor_form.addRow("Tab width", dialog._tab_width_input)

    dialog._font_family_input = QFontComboBox(editor_group)
    dialog._font_family_input.setCurrentFont(QFont(snapshot.font_family))
    editor_form.addRow("Font family", dialog._font_family_input)

    dialog._font_size_input = QSpinBox(editor_group)
    dialog._font_size_input.setRange(8, 28)
    dialog._font_size_input.setValue(snapshot.font_size)
    editor_form.addRow("Font size", dialog._font_size_input)

    dialog._indent_style_input = QComboBox(editor_group)
    dialog._indent_style_input.addItems(["spaces", "tabs"])
    dialog._indent_style_input.setCurrentText(snapshot.indent_style)
    editor_form.addRow("Indent style", dialog._indent_style_input)

    dialog._indent_size_input = QSpinBox(editor_group)
    dialog._indent_size_input.setRange(1, 16)
    dialog._indent_size_input.setValue(snapshot.indent_size)
    editor_form.addRow("Indent size", dialog._indent_size_input)

    dialog._detect_indentation_input = QCheckBox(editor_group)
    dialog._detect_indentation_input.setChecked(snapshot.detect_indentation_from_file)
    editor_form.addRow("Detect indentation from file", dialog._detect_indentation_input)

    dialog._format_on_save_input = QCheckBox(editor_group)
    dialog._format_on_save_input.setChecked(snapshot.format_on_save)
    editor_form.addRow("Format on save", dialog._format_on_save_input)

    dialog._organize_imports_on_save_input = QCheckBox(editor_group)
    dialog._organize_imports_on_save_input.setChecked(snapshot.organize_imports_on_save)
    editor_form.addRow("Organize imports on save", dialog._organize_imports_on_save_input)

    dialog._python_tooling_runtime_status_label = QLabel(python_tooling_runtime_text, editor_group)
    dialog._python_tooling_runtime_status_label.setWordWrap(True)
    dialog._python_tooling_runtime_status_label.setToolTip(python_tooling_runtime_details)
    editor_form.addRow("Python tooling runtime", dialog._python_tooling_runtime_status_label)

    dialog._python_tooling_config_status_label = QLabel(python_tooling_config_text, editor_group)
    dialog._python_tooling_config_status_label.setWordWrap(True)
    dialog._python_tooling_config_status_label.setToolTip(python_tooling_config_details)
    editor_form.addRow("Project Python config", dialog._python_tooling_config_status_label)

    dialog._trim_trailing_whitespace_on_save_input = QCheckBox(editor_group)
    dialog._trim_trailing_whitespace_on_save_input.setChecked(snapshot.trim_trailing_whitespace_on_save)
    editor_form.addRow("Trim trailing whitespace on save", dialog._trim_trailing_whitespace_on_save_input)

    dialog._insert_final_newline_on_save_input = QCheckBox(editor_group)
    dialog._insert_final_newline_on_save_input.setChecked(snapshot.insert_final_newline_on_save)
    editor_form.addRow("Insert final newline on save", dialog._insert_final_newline_on_save_input)
    dialog._enable_preview_input = QCheckBox(editor_group)
    dialog._enable_preview_input.setChecked(snapshot.enable_preview)
    editor_form.addRow("Enable preview tabs", dialog._enable_preview_input)
    dialog._auto_save_input = QCheckBox(editor_group)
    dialog._auto_save_input.setChecked(snapshot.auto_save)
    editor_form.addRow("Auto save", dialog._auto_save_input)
    dialog._exit_behavior_input = QComboBox(editor_group)
    dialog._exit_behavior_input.addItem("Ask before closing dirty files", "ask")
    dialog._exit_behavior_input.addItem("Keep unsaved changes for next launch", "keep_unsaved")
    exit_behavior_index = dialog._exit_behavior_input.findData(snapshot.exit_behavior)
    dialog._exit_behavior_input.setCurrentIndex(exit_behavior_index if exit_behavior_index >= 0 else 0)
    editor_form.addRow("Exit behavior", dialog._exit_behavior_input)
    dialog._hover_tooltip_enabled_input = QCheckBox(editor_group)
    dialog._hover_tooltip_enabled_input.setChecked(snapshot.hover_tooltip_enabled)
    editor_form.addRow("Show hover tooltips in code editor", dialog._hover_tooltip_enabled_input)
    dialog._auto_reindent_flat_python_paste_input = QCheckBox(editor_group)
    dialog._auto_reindent_flat_python_paste_input.setChecked(snapshot.auto_reindent_flat_python_paste)
    editor_form.addRow(
        "Automatically repair flat Python indentation on paste (experimental)",
        dialog._auto_reindent_flat_python_paste_input,
    )
    dialog._editor_reset_to_global_btn = QPushButton("Reset Editor Overrides to Global", editor_group)
    dialog._editor_reset_to_global_btn.setObjectName("shell.settingsDialog.editorResetGlobal")
    dialog._editor_reset_to_global_btn.clicked.connect(dialog._handle_reset_editor_group_to_global)
    editor_form.addRow("", dialog._editor_reset_to_global_btn)
    general_layout.addWidget(editor_group)

    intelligence_group = QGroupBox("Intelligence")
    intelligence_group.setObjectName("shell.settingsDialog.intelligenceGroup")
    intelligence_form = QFormLayout(intelligence_group)
    intelligence_form.setVerticalSpacing(10)
    intelligence_form.setHorizontalSpacing(16)
    dialog._completion_enabled_input = QCheckBox(intelligence_group)
    dialog._completion_enabled_input.setChecked(snapshot.completion_enabled)
    intelligence_form.addRow("Enable completion", dialog._completion_enabled_input)

    dialog._completion_auto_trigger_input = QCheckBox(intelligence_group)
    dialog._completion_auto_trigger_input.setChecked(snapshot.completion_auto_trigger)
    intelligence_form.addRow("Auto-trigger completion", dialog._completion_auto_trigger_input)

    dialog._completion_min_chars_input = QSpinBox(intelligence_group)
    dialog._completion_min_chars_input.setRange(1, 8)
    dialog._completion_min_chars_input.setValue(snapshot.completion_min_chars)
    intelligence_form.addRow("Completion min chars", dialog._completion_min_chars_input)

    dialog._diagnostics_realtime_input = QCheckBox(intelligence_group)
    dialog._diagnostics_realtime_input.setChecked(snapshot.diagnostics_realtime)
    intelligence_form.addRow("Realtime diagnostics", dialog._diagnostics_realtime_input)

    dialog._quick_fixes_enabled_input = QCheckBox(intelligence_group)
    dialog._quick_fixes_enabled_input.setChecked(snapshot.quick_fixes_enabled)
    intelligence_form.addRow("Enable quick fixes", dialog._quick_fixes_enabled_input)

    dialog._quick_fix_multifile_preview_input = QCheckBox(intelligence_group)
    dialog._quick_fix_multifile_preview_input.setChecked(snapshot.quick_fix_require_preview_for_multifile)
    intelligence_form.addRow("Preview required for multi-file fixes", dialog._quick_fix_multifile_preview_input)

    dialog._cache_enabled_input = QCheckBox(intelligence_group)
    dialog._cache_enabled_input.setChecked(snapshot.cache_enabled)
    intelligence_form.addRow("Enable intelligence cache", dialog._cache_enabled_input)

    dialog._incremental_indexing_input = QCheckBox(intelligence_group)
    dialog._incremental_indexing_input.setChecked(snapshot.incremental_indexing)
    intelligence_form.addRow("Incremental indexing", dialog._incremental_indexing_input)

    dialog._metrics_logging_input = QCheckBox(intelligence_group)
    dialog._metrics_logging_input.setChecked(snapshot.metrics_logging_enabled)
    intelligence_form.addRow("Metrics logging", dialog._metrics_logging_input)

    dialog._force_reindex_on_open_input = QCheckBox(intelligence_group)
    dialog._force_reindex_on_open_input.setChecked(snapshot.force_full_reindex_on_open)
    intelligence_form.addRow("Force full reindex on open", dialog._force_reindex_on_open_input)
    dialog._intelligence_reset_to_global_btn = QPushButton(
        "Reset Intelligence Overrides to Global", intelligence_group
    )
    dialog._intelligence_reset_to_global_btn.setObjectName("shell.settingsDialog.intelligenceResetGlobal")
    dialog._intelligence_reset_to_global_btn.clicked.connect(dialog._handle_reset_intelligence_group_to_global)
    intelligence_form.addRow("", dialog._intelligence_reset_to_global_btn)
    general_layout.addWidget(intelligence_group)
    general_layout.addStretch(1)
    scroll_area.setWidget(scroll_content)
    general_tab_layout.addWidget(scroll_area)


def general_tab_state_from_controls(dialog: "SettingsDialog") -> GeneralTabState:
    return GeneralTabState(
        tab_width=int(dialog._tab_width_input.value()),
        font_size=int(dialog._font_size_input.value()),
        font_family=dialog._font_family_input.currentFont().family(),
        indent_style=str(dialog._indent_style_input.currentText()),
        indent_size=int(dialog._indent_size_input.value()),
        detect_indentation_from_file=dialog._detect_indentation_input.isChecked(),
        format_on_save=dialog._format_on_save_input.isChecked(),
        organize_imports_on_save=dialog._organize_imports_on_save_input.isChecked(),
        trim_trailing_whitespace_on_save=dialog._trim_trailing_whitespace_on_save_input.isChecked(),
        insert_final_newline_on_save=dialog._insert_final_newline_on_save_input.isChecked(),
        enable_preview=dialog._enable_preview_input.isChecked(),
        auto_save=dialog._auto_save_input.isChecked(),
        exit_behavior=str(dialog._exit_behavior_input.currentData()),
        hover_tooltip_enabled=dialog._hover_tooltip_enabled_input.isChecked(),
        auto_reindent_flat_python_paste=dialog._auto_reindent_flat_python_paste_input.isChecked(),
        completion_enabled=dialog._completion_enabled_input.isChecked(),
        completion_auto_trigger=dialog._completion_auto_trigger_input.isChecked(),
        completion_min_chars=int(dialog._completion_min_chars_input.value()),
        diagnostics_realtime=dialog._diagnostics_realtime_input.isChecked(),
        quick_fixes_enabled=dialog._quick_fixes_enabled_input.isChecked(),
        quick_fix_require_preview_for_multifile=dialog._quick_fix_multifile_preview_input.isChecked(),
        cache_enabled=dialog._cache_enabled_input.isChecked(),
        incremental_indexing=dialog._incremental_indexing_input.isChecked(),
        metrics_logging_enabled=dialog._metrics_logging_input.isChecked(),
        force_full_reindex_on_open=dialog._force_reindex_on_open_input.isChecked(),
        theme_mode=dialog._normalized_theme_mode_value(),
        ui_font_weight=dialog._normalized_ui_font_weight_value(),
        dark_chrome_palette=dialog._normalized_dark_chrome_palette_value(),
        auto_open_console_on_run_output=dialog._auto_open_console_on_run_output_input.isChecked(),
        auto_open_problems_on_run_failure=dialog._auto_open_problems_on_run_failure_input.isChecked(),
        highlighting_adaptive_mode=dialog._baseline_highlighting_adaptive_mode,
        highlighting_reduced_threshold_chars=dialog._baseline_highlighting_reduced_threshold_chars,
        highlighting_lexical_only_threshold_chars=dialog._baseline_highlighting_lexical_only_threshold_chars,
    )


def apply_general_tab_state_to_controls(dialog: "SettingsDialog", state: GeneralTabState) -> None:
    dialog._tab_width_input.setValue(state.tab_width)
    dialog._font_size_input.setValue(state.font_size)
    dialog._font_family_input.setCurrentFont(QFont(state.font_family))
    dialog._indent_style_input.setCurrentText(state.indent_style)
    dialog._indent_size_input.setValue(state.indent_size)
    dialog._detect_indentation_input.setChecked(state.detect_indentation_from_file)
    dialog._format_on_save_input.setChecked(state.format_on_save)
    dialog._organize_imports_on_save_input.setChecked(state.organize_imports_on_save)
    dialog._trim_trailing_whitespace_on_save_input.setChecked(state.trim_trailing_whitespace_on_save)
    dialog._insert_final_newline_on_save_input.setChecked(state.insert_final_newline_on_save)
    dialog._enable_preview_input.setChecked(state.enable_preview)
    dialog._auto_save_input.setChecked(state.auto_save)
    exit_behavior_index = dialog._exit_behavior_input.findData(state.exit_behavior)
    dialog._exit_behavior_input.setCurrentIndex(exit_behavior_index if exit_behavior_index >= 0 else 0)
    dialog._hover_tooltip_enabled_input.setChecked(state.hover_tooltip_enabled)
    dialog._auto_reindent_flat_python_paste_input.setChecked(state.auto_reindent_flat_python_paste)

    dialog._completion_enabled_input.setChecked(state.completion_enabled)
    dialog._completion_auto_trigger_input.setChecked(state.completion_auto_trigger)
    dialog._completion_min_chars_input.setValue(state.completion_min_chars)
    dialog._diagnostics_realtime_input.setChecked(state.diagnostics_realtime)
    dialog._quick_fixes_enabled_input.setChecked(state.quick_fixes_enabled)
    dialog._quick_fix_multifile_preview_input.setChecked(state.quick_fix_require_preview_for_multifile)
    dialog._cache_enabled_input.setChecked(state.cache_enabled)
    dialog._incremental_indexing_input.setChecked(state.incremental_indexing)
    dialog._metrics_logging_input.setChecked(state.metrics_logging_enabled)
    dialog._force_reindex_on_open_input.setChecked(state.force_full_reindex_on_open)

    dialog._auto_open_console_on_run_output_input.setChecked(state.auto_open_console_on_run_output)
    dialog._auto_open_problems_on_run_failure_input.setChecked(state.auto_open_problems_on_run_failure)

    theme_index = dialog._theme_mode_input.findData(state.theme_mode)
    dialog._theme_mode_input.setCurrentIndex(theme_index if theme_index >= 0 else 0)
    weight_index = dialog._ui_font_weight_input.findData(state.ui_font_weight)
    dialog._ui_font_weight_input.setCurrentIndex(weight_index if weight_index >= 0 else 0)
    palette_index = dialog._dark_chrome_palette_input.findData(state.dark_chrome_palette)
    dialog._dark_chrome_palette_input.setCurrentIndex(palette_index if palette_index >= 0 else 0)

    dialog._baseline_highlighting_adaptive_mode = state.highlighting_adaptive_mode
    dialog._baseline_highlighting_reduced_threshold_chars = state.highlighting_reduced_threshold_chars
    dialog._baseline_highlighting_lexical_only_threshold_chars = state.highlighting_lexical_only_threshold_chars
