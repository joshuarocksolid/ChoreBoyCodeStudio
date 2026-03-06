"""Qt settings dialog for editor/intelligence preferences."""

from __future__ import annotations

from PySide2.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QFontComboBox,
    QFormLayout,
    QColorDialog,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from PySide2.QtGui import QColor, QFont
from PySide2.QtCore import Qt
from PySide2.QtGui import QKeySequence

from app.project.file_excludes import DEFAULT_EXCLUDE_PATTERNS
from app.shell.settings_models import (
    EditorSettingsSnapshot,
    SETTINGS_SCOPE_GLOBAL,
    SETTINGS_SCOPE_PROJECT,
)
from app.shell.shortcut_preferences import (
    SHORTCUT_COMMANDS,
    build_effective_shortcut_map,
    default_shortcut_map,
    find_shortcut_conflicts,
    normalize_shortcut,
)
from app.shell.syntax_color_preferences import (
    SYNTAX_COLOR_TOKENS,
    THEME_DARK,
    THEME_LIGHT,
    normalize_hex_color,
)
from app.editors.syntax_engine import DEFAULT_DARK_PALETTE, DEFAULT_LIGHT_PALETTE
from app.intelligence.lint_profile import (
    LINT_RULE_DEFINITIONS,
    LINT_SEVERITY_ERROR,
    LINT_SEVERITY_INFO,
    LINT_SEVERITY_WARNING,
)
from app.core import constants


class SettingsDialog(QDialog):
    """Simple settings editor for core editor/intelligence preferences."""

    def __init__(
        self,
        snapshot: EditorSettingsSnapshot,
        parent=None,
        *,
        project_snapshot: EditorSettingsSnapshot | None = None,
        project_scope_available: bool = False,
        initial_scope: str = SETTINGS_SCOPE_GLOBAL,
    ) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(860, 640)
        self._project_scope_available = bool(project_scope_available and project_snapshot is not None)
        self._active_scope = SETTINGS_SCOPE_GLOBAL
        self._scope_snapshots: dict[str, EditorSettingsSnapshot] = {
            SETTINGS_SCOPE_GLOBAL: snapshot,
        }
        if self._project_scope_available:
            self._scope_snapshots[SETTINGS_SCOPE_PROJECT] = project_snapshot or snapshot
        self._shortcut_editors: dict[str, QKeySequenceEdit] = {}
        self._shortcut_rows: dict[str, int] = {}
        self._syntax_color_inputs: dict[str, QLineEdit] = {}
        self._syntax_color_row_by_token: dict[str, int] = {}
        self._syntax_color_overrides_by_theme: dict[str, dict[str, str]] = {
            THEME_LIGHT: dict(snapshot.syntax_color_overrides_light),
            THEME_DARK: dict(snapshot.syntax_color_overrides_dark),
        }
        self._lint_rule_overrides: dict[str, dict[str, object]] = {
            code: dict(value) for code, value in snapshot.lint_rule_overrides.items()
        }
        self._lint_enabled_inputs: dict[str, QCheckBox] = {}
        self._lint_severity_inputs: dict[str, QComboBox] = {}
        self._active_syntax_theme_key = THEME_LIGHT
        self._has_shortcut_conflicts = False
        self._has_invalid_syntax_colors = False
        self._is_updating_shortcut_editors = False
        self._ok_button = None
        self._scope_input: QComboBox | None = None
        self._scope_banner_label: QLabel | None = None
        self._tabs_widget: QTabWidget | None = None
        self._keybindings_tab_index: int | None = None
        self._syntax_tab_index: int | None = None
        self._appearance_group: QGroupBox | None = None
        self._output_reset_to_global_btn: QPushButton | None = None
        self._editor_reset_to_global_btn: QPushButton | None = None
        self._intelligence_reset_to_global_btn: QPushButton | None = None
        self._linter_reset_to_global_btn: QPushButton | None = None
        self._file_excludes_reset_btn: QPushButton | None = None

        layout = QVBoxLayout(self)
        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel("Settings Scope", self))
        self._scope_input = QComboBox(self)
        self._scope_input.addItem("Global", SETTINGS_SCOPE_GLOBAL)
        self._scope_input.addItem("Project", SETTINGS_SCOPE_PROJECT)
        if not self._project_scope_available:
            model = self._scope_input.model()
            item = model.item(1) if hasattr(model, "item") else None
            if item is not None:
                item.setEnabled(False)
                item.setToolTip("Open a project to edit project scope settings.")
        self._scope_input.currentIndexChanged.connect(self._handle_scope_changed)
        scope_row.addWidget(self._scope_input)
        scope_row.addStretch(1)
        layout.addLayout(scope_row)

        self._scope_banner_label = QLabel(self)
        self._scope_banner_label.setWordWrap(True)
        layout.addWidget(self._scope_banner_label)

        tabs = QTabWidget(self)
        self._tabs_widget = tabs
        layout.addWidget(tabs)

        general_tab = QWidget(tabs)
        general_layout = QVBoxLayout(general_tab)
        tabs.addTab(general_tab, "General")
        appearance_group = QGroupBox("Appearance")
        self._appearance_group = appearance_group
        appearance_form = QFormLayout(appearance_group)
        self._theme_mode_input = QComboBox(appearance_group)
        self._theme_mode_input.addItems(["System", "Light", "Dark"])
        _mode_to_index = {"system": 0, "light": 1, "dark": 2}
        self._theme_mode_input.setCurrentIndex(_mode_to_index.get(snapshot.theme_mode, 0))
        appearance_form.addRow("Theme", self._theme_mode_input)
        general_layout.addWidget(appearance_group)

        output_group = QGroupBox("Output")
        output_form = QFormLayout(output_group)
        self._auto_open_console_on_run_output_input = QCheckBox(output_group)
        self._auto_open_console_on_run_output_input.setChecked(snapshot.auto_open_console_on_run_output)
        output_form.addRow("Auto-open Run Log on run output", self._auto_open_console_on_run_output_input)
        self._auto_open_problems_on_run_failure_input = QCheckBox(output_group)
        self._auto_open_problems_on_run_failure_input.setChecked(snapshot.auto_open_problems_on_run_failure)
        output_form.addRow("Auto-open Problems on run failure", self._auto_open_problems_on_run_failure_input)
        self._output_reset_to_global_btn = QPushButton("Reset Output Overrides to Global", output_group)
        self._output_reset_to_global_btn.clicked.connect(self._handle_reset_output_group_to_global)
        output_form.addRow("", self._output_reset_to_global_btn)
        general_layout.addWidget(output_group)

        editor_group = QGroupBox("Editor")
        editor_form = QFormLayout(editor_group)
        self._tab_width_input = QSpinBox(editor_group)
        self._tab_width_input.setRange(2, 16)
        self._tab_width_input.setValue(snapshot.tab_width)
        editor_form.addRow("Tab width", self._tab_width_input)

        self._font_family_input = QFontComboBox(editor_group)
        self._font_family_input.setCurrentFont(QFont(snapshot.font_family))
        editor_form.addRow("Font family", self._font_family_input)

        self._font_size_input = QSpinBox(editor_group)
        self._font_size_input.setRange(8, 28)
        self._font_size_input.setValue(snapshot.font_size)
        editor_form.addRow("Font size", self._font_size_input)

        self._indent_style_input = QComboBox(editor_group)
        self._indent_style_input.addItems(["spaces", "tabs"])
        self._indent_style_input.setCurrentText(snapshot.indent_style)
        editor_form.addRow("Indent style", self._indent_style_input)

        self._indent_size_input = QSpinBox(editor_group)
        self._indent_size_input.setRange(1, 16)
        self._indent_size_input.setValue(snapshot.indent_size)
        editor_form.addRow("Indent size", self._indent_size_input)

        self._detect_indentation_input = QCheckBox(editor_group)
        self._detect_indentation_input.setChecked(snapshot.detect_indentation_from_file)
        editor_form.addRow("Detect indentation from file", self._detect_indentation_input)

        self._format_on_save_input = QCheckBox(editor_group)
        self._format_on_save_input.setChecked(snapshot.format_on_save)
        editor_form.addRow("Format on save", self._format_on_save_input)

        self._trim_trailing_whitespace_on_save_input = QCheckBox(editor_group)
        self._trim_trailing_whitespace_on_save_input.setChecked(snapshot.trim_trailing_whitespace_on_save)
        editor_form.addRow("Trim trailing whitespace on save", self._trim_trailing_whitespace_on_save_input)

        self._insert_final_newline_on_save_input = QCheckBox(editor_group)
        self._insert_final_newline_on_save_input.setChecked(snapshot.insert_final_newline_on_save)
        editor_form.addRow("Insert final newline on save", self._insert_final_newline_on_save_input)
        self._editor_reset_to_global_btn = QPushButton("Reset Editor Overrides to Global", editor_group)
        self._editor_reset_to_global_btn.clicked.connect(self._handle_reset_editor_group_to_global)
        editor_form.addRow("", self._editor_reset_to_global_btn)
        general_layout.addWidget(editor_group)

        intelligence_group = QGroupBox("Intelligence")
        intelligence_form = QFormLayout(intelligence_group)
        self._completion_enabled_input = QCheckBox(intelligence_group)
        self._completion_enabled_input.setChecked(snapshot.completion_enabled)
        intelligence_form.addRow("Enable completion", self._completion_enabled_input)

        self._completion_auto_trigger_input = QCheckBox(intelligence_group)
        self._completion_auto_trigger_input.setChecked(snapshot.completion_auto_trigger)
        intelligence_form.addRow("Auto-trigger completion", self._completion_auto_trigger_input)

        self._completion_min_chars_input = QSpinBox(intelligence_group)
        self._completion_min_chars_input.setRange(1, 8)
        self._completion_min_chars_input.setValue(snapshot.completion_min_chars)
        intelligence_form.addRow("Completion min chars", self._completion_min_chars_input)

        self._diagnostics_realtime_input = QCheckBox(intelligence_group)
        self._diagnostics_realtime_input.setChecked(snapshot.diagnostics_realtime)
        intelligence_form.addRow("Realtime diagnostics", self._diagnostics_realtime_input)

        self._quick_fixes_enabled_input = QCheckBox(intelligence_group)
        self._quick_fixes_enabled_input.setChecked(snapshot.quick_fixes_enabled)
        intelligence_form.addRow("Enable quick fixes", self._quick_fixes_enabled_input)

        self._quick_fix_multifile_preview_input = QCheckBox(intelligence_group)
        self._quick_fix_multifile_preview_input.setChecked(snapshot.quick_fix_require_preview_for_multifile)
        intelligence_form.addRow("Preview required for multi-file fixes", self._quick_fix_multifile_preview_input)

        self._cache_enabled_input = QCheckBox(intelligence_group)
        self._cache_enabled_input.setChecked(snapshot.cache_enabled)
        intelligence_form.addRow("Enable intelligence cache", self._cache_enabled_input)

        self._incremental_indexing_input = QCheckBox(intelligence_group)
        self._incremental_indexing_input.setChecked(snapshot.incremental_indexing)
        intelligence_form.addRow("Incremental indexing", self._incremental_indexing_input)

        self._metrics_logging_input = QCheckBox(intelligence_group)
        self._metrics_logging_input.setChecked(snapshot.metrics_logging_enabled)
        intelligence_form.addRow("Metrics logging", self._metrics_logging_input)

        self._force_reindex_on_open_input = QCheckBox(intelligence_group)
        self._force_reindex_on_open_input.setChecked(snapshot.force_full_reindex_on_open)
        intelligence_form.addRow("Force full reindex on open", self._force_reindex_on_open_input)
        self._intelligence_reset_to_global_btn = QPushButton(
            "Reset Intelligence Overrides to Global", intelligence_group
        )
        self._intelligence_reset_to_global_btn.clicked.connect(self._handle_reset_intelligence_group_to_global)
        intelligence_form.addRow("", self._intelligence_reset_to_global_btn)
        general_layout.addWidget(intelligence_group)
        general_layout.addStretch(1)

        keybindings_tab = QWidget(tabs)
        keybindings_layout = QVBoxLayout(keybindings_tab)
        self._keybindings_tab_index = tabs.addTab(keybindings_tab, "Keybindings")

        self._shortcut_search_input = QLineEdit(keybindings_tab)
        self._shortcut_search_input.setPlaceholderText("Search commands...")
        self._shortcut_search_input.textChanged.connect(self._filter_shortcut_rows)
        keybindings_layout.addWidget(self._shortcut_search_input)

        self._shortcut_reset_all_btn = QPushButton("Reset All Keybindings", keybindings_tab)
        self._shortcut_reset_all_btn.clicked.connect(self._handle_reset_all_shortcuts)
        keybindings_layout.addWidget(self._shortcut_reset_all_btn)

        self._shortcut_conflict_label = QLabel(keybindings_tab)
        self._shortcut_conflict_label.setStyleSheet("color: #C92A2A;")
        self._shortcut_conflict_label.setWordWrap(True)
        self._shortcut_conflict_label.setVisible(False)
        keybindings_layout.addWidget(self._shortcut_conflict_label)

        self._shortcut_table = QTableWidget(0, 4, keybindings_tab)
        self._shortcut_table.setHorizontalHeaderLabels(["Command", "Shortcut", "Default", "Reset"])
        self._shortcut_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._shortcut_table.setSelectionMode(QAbstractItemView.NoSelection)
        self._shortcut_table.setFocusPolicy(Qt.NoFocus)
        self._shortcut_table.verticalHeader().setVisible(False)
        header = self._shortcut_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        keybindings_layout.addWidget(self._shortcut_table, 1)
        self._populate_shortcut_table(snapshot)

        syntax_tab = QWidget(tabs)
        syntax_layout = QVBoxLayout(syntax_tab)
        self._syntax_tab_index = tabs.addTab(syntax_tab, "Syntax Colors")

        self._syntax_theme_input = QComboBox(syntax_tab)
        self._syntax_theme_input.addItem("Light Theme", THEME_LIGHT)
        self._syntax_theme_input.addItem("Dark Theme", THEME_DARK)
        self._syntax_theme_input.currentIndexChanged.connect(self._handle_syntax_theme_changed)
        syntax_layout.addWidget(self._syntax_theme_input)

        self._syntax_validation_label = QLabel(syntax_tab)
        self._syntax_validation_label.setStyleSheet("color: #C92A2A;")
        self._syntax_validation_label.setWordWrap(True)
        self._syntax_validation_label.setVisible(False)
        syntax_layout.addWidget(self._syntax_validation_label)

        self._syntax_color_table = QTableWidget(0, 4, syntax_tab)
        self._syntax_color_table.setHorizontalHeaderLabels(["Token", "Color", "Pick", "Reset"])
        self._syntax_color_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._syntax_color_table.setSelectionMode(QAbstractItemView.NoSelection)
        self._syntax_color_table.setFocusPolicy(Qt.NoFocus)
        self._syntax_color_table.verticalHeader().setVisible(False)
        syntax_header = self._syntax_color_table.horizontalHeader()
        syntax_header.setSectionResizeMode(0, QHeaderView.Stretch)
        syntax_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        syntax_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        syntax_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        syntax_layout.addWidget(self._syntax_color_table, 1)
        self._populate_syntax_color_table(self._active_syntax_theme_key)

        linter_tab = QWidget(tabs)
        linter_layout = QVBoxLayout(linter_tab)
        tabs.addTab(linter_tab, "Linter")

        linter_controls = QGroupBox("Provider")
        linter_controls_form = QFormLayout(linter_controls)
        self._linter_enabled_input = QCheckBox(linter_controls)
        self._linter_enabled_input.setChecked(snapshot.diagnostics_enabled)
        self._linter_enabled_input.toggled.connect(self._handle_linter_enabled_toggled)
        linter_controls_form.addRow("Enable Python linting", self._linter_enabled_input)
        self._linter_provider_input = QComboBox(linter_controls)
        self._linter_provider_input.addItem("Default (built-in)", constants.LINTER_PROVIDER_DEFAULT)
        self._linter_provider_input.addItem("Pyflakes", constants.LINTER_PROVIDER_PYFLAKES)
        provider_index = self._linter_provider_input.findData(snapshot.selected_linter)
        self._linter_provider_input.setCurrentIndex(provider_index if provider_index >= 0 else 0)
        linter_controls_form.addRow("Linter provider", self._linter_provider_input)
        linter_layout.addWidget(linter_controls)

        self._linter_table = QTableWidget(0, 5, linter_tab)
        self._linter_table.setHorizontalHeaderLabels(["Code", "Rule", "Enabled", "Severity", "Reset"])
        self._linter_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._linter_table.setSelectionMode(QAbstractItemView.NoSelection)
        self._linter_table.setFocusPolicy(Qt.NoFocus)
        self._linter_table.verticalHeader().setVisible(False)
        linter_header = self._linter_table.horizontalHeader()
        linter_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        linter_header.setSectionResizeMode(1, QHeaderView.Stretch)
        linter_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        linter_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        linter_header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        linter_layout.addWidget(self._linter_table, 1)
        self._populate_linter_table()
        self._linter_reset_to_global_btn = QPushButton("Reset Linter Overrides to Global", linter_tab)
        self._linter_reset_to_global_btn.clicked.connect(self._handle_reset_linter_overrides_to_global)
        linter_layout.addWidget(self._linter_reset_to_global_btn)
        self._sync_linter_control_states()

        files_tab = QWidget(tabs)
        files_layout = QVBoxLayout(files_tab)
        tabs.addTab(files_tab, "Files")

        excludes_group = QGroupBox("File Exclusions")
        excludes_vbox = QVBoxLayout(excludes_group)

        excludes_help = QLabel(
            "Glob patterns for files and folders to hide from the explorer, "
            "Quick Open, and search results. Patterns are matched against "
            "names and relative paths."
        )
        excludes_help.setWordWrap(True)
        excludes_vbox.addWidget(excludes_help)

        self._file_excludes_list = QListWidget(excludes_group)
        for pattern in snapshot.file_exclude_patterns:
            self._file_excludes_list.addItem(pattern)
        excludes_vbox.addWidget(self._file_excludes_list, 1)

        add_row = QHBoxLayout()
        self._file_exclude_input = QLineEdit(excludes_group)
        self._file_exclude_input.setPlaceholderText("e.g. *.pyc, build, .mypy_cache")
        self._file_exclude_input.returnPressed.connect(self._handle_add_file_exclude)
        add_row.addWidget(self._file_exclude_input, 1)
        add_btn = QPushButton("Add", excludes_group)
        add_btn.clicked.connect(self._handle_add_file_exclude)
        add_row.addWidget(add_btn)
        excludes_vbox.addLayout(add_row)

        btn_row = QHBoxLayout()
        remove_btn = QPushButton("Remove Selected", excludes_group)
        remove_btn.clicked.connect(self._handle_remove_file_exclude)
        btn_row.addWidget(remove_btn)
        reset_btn = QPushButton("Reset to Defaults", excludes_group)
        self._file_excludes_reset_btn = reset_btn
        reset_btn.clicked.connect(self._handle_reset_file_excludes)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch(1)
        excludes_vbox.addLayout(btn_row)

        files_layout.addWidget(excludes_group)
        files_layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._ok_button = buttons.button(QDialogButtonBox.Ok)
        normalized_initial_scope = initial_scope
        if normalized_initial_scope not in {SETTINGS_SCOPE_GLOBAL, SETTINGS_SCOPE_PROJECT}:
            normalized_initial_scope = SETTINGS_SCOPE_GLOBAL
        if normalized_initial_scope == SETTINGS_SCOPE_PROJECT and not self._project_scope_available:
            normalized_initial_scope = SETTINGS_SCOPE_GLOBAL
        self._set_scope(normalized_initial_scope, apply_snapshot=True)

    def snapshot(self) -> EditorSettingsSnapshot:
        """Return settings snapshot from current dialog values."""
        self._capture_active_scope_snapshot()
        return self._scope_snapshots[self._active_scope]

    @property
    def selected_scope(self) -> str:
        self._capture_active_scope_snapshot()
        return self._active_scope

    def global_scope_snapshot(self) -> EditorSettingsSnapshot:
        self._capture_active_scope_snapshot()
        return self._scope_snapshots[SETTINGS_SCOPE_GLOBAL]

    def project_scope_snapshot(self) -> EditorSettingsSnapshot | None:
        if not self._project_scope_available:
            return None
        self._capture_active_scope_snapshot()
        return self._scope_snapshots.get(SETTINGS_SCOPE_PROJECT)

    def _snapshot_from_controls(self) -> EditorSettingsSnapshot:
        """Build settings snapshot from current control values."""
        return EditorSettingsSnapshot(
            tab_width=int(self._tab_width_input.value()),
            font_size=int(self._font_size_input.value()),
            font_family=self._font_family_input.currentFont().family(),
            indent_style=str(self._indent_style_input.currentText()),
            indent_size=int(self._indent_size_input.value()),
            detect_indentation_from_file=self._detect_indentation_input.isChecked(),
            format_on_save=self._format_on_save_input.isChecked(),
            trim_trailing_whitespace_on_save=self._trim_trailing_whitespace_on_save_input.isChecked(),
            insert_final_newline_on_save=self._insert_final_newline_on_save_input.isChecked(),
            completion_enabled=self._completion_enabled_input.isChecked(),
            completion_auto_trigger=self._completion_auto_trigger_input.isChecked(),
            completion_min_chars=int(self._completion_min_chars_input.value()),
            diagnostics_enabled=self._linter_enabled_input.isChecked(),
            diagnostics_realtime=self._diagnostics_realtime_input.isChecked(),
            quick_fixes_enabled=self._quick_fixes_enabled_input.isChecked(),
            quick_fix_require_preview_for_multifile=self._quick_fix_multifile_preview_input.isChecked(),
            cache_enabled=self._cache_enabled_input.isChecked(),
            incremental_indexing=self._incremental_indexing_input.isChecked(),
            metrics_logging_enabled=self._metrics_logging_input.isChecked(),
            force_full_reindex_on_open=self._force_reindex_on_open_input.isChecked(),
            theme_mode=["system", "light", "dark"][self._theme_mode_input.currentIndex()],
            auto_open_console_on_run_output=self._auto_open_console_on_run_output_input.isChecked(),
            auto_open_problems_on_run_failure=self._auto_open_problems_on_run_failure_input.isChecked(),
            selected_linter=str(self._linter_provider_input.currentData()),
            shortcut_overrides=self._shortcut_overrides_snapshot(),
            syntax_color_overrides_light=dict(self._syntax_color_overrides_by_theme.get(THEME_LIGHT, {})),
            syntax_color_overrides_dark=dict(self._syntax_color_overrides_by_theme.get(THEME_DARK, {})),
            lint_rule_overrides=self._lint_rule_overrides_snapshot(),
            file_exclude_patterns=self._file_exclude_patterns_snapshot(),
        )

    def _capture_active_scope_snapshot(self) -> None:
        self._scope_snapshots[self._active_scope] = self._snapshot_from_controls()

    def _apply_snapshot_to_controls(self, snapshot: EditorSettingsSnapshot) -> None:
        self._tab_width_input.setValue(snapshot.tab_width)
        self._font_size_input.setValue(snapshot.font_size)
        self._font_family_input.setCurrentFont(QFont(snapshot.font_family))
        self._indent_style_input.setCurrentText(snapshot.indent_style)
        self._indent_size_input.setValue(snapshot.indent_size)
        self._detect_indentation_input.setChecked(snapshot.detect_indentation_from_file)
        self._format_on_save_input.setChecked(snapshot.format_on_save)
        self._trim_trailing_whitespace_on_save_input.setChecked(snapshot.trim_trailing_whitespace_on_save)
        self._insert_final_newline_on_save_input.setChecked(snapshot.insert_final_newline_on_save)

        self._completion_enabled_input.setChecked(snapshot.completion_enabled)
        self._completion_auto_trigger_input.setChecked(snapshot.completion_auto_trigger)
        self._completion_min_chars_input.setValue(snapshot.completion_min_chars)
        self._linter_enabled_input.setChecked(snapshot.diagnostics_enabled)
        self._diagnostics_realtime_input.setChecked(snapshot.diagnostics_realtime)
        self._quick_fixes_enabled_input.setChecked(snapshot.quick_fixes_enabled)
        self._quick_fix_multifile_preview_input.setChecked(snapshot.quick_fix_require_preview_for_multifile)
        self._cache_enabled_input.setChecked(snapshot.cache_enabled)
        self._incremental_indexing_input.setChecked(snapshot.incremental_indexing)
        self._metrics_logging_input.setChecked(snapshot.metrics_logging_enabled)
        self._force_reindex_on_open_input.setChecked(snapshot.force_full_reindex_on_open)
        provider_index = self._linter_provider_input.findData(snapshot.selected_linter)
        self._linter_provider_input.setCurrentIndex(provider_index if provider_index >= 0 else 0)
        self._sync_linter_control_states()

        self._auto_open_console_on_run_output_input.setChecked(snapshot.auto_open_console_on_run_output)
        self._auto_open_problems_on_run_failure_input.setChecked(snapshot.auto_open_problems_on_run_failure)

        self._theme_mode_input.setCurrentIndex(
            {"system": 0, "light": 1, "dark": 2}.get(snapshot.theme_mode, 0)
        )

        self._apply_shortcut_snapshot(snapshot)
        self._syntax_color_overrides_by_theme = {
            THEME_LIGHT: dict(snapshot.syntax_color_overrides_light),
            THEME_DARK: dict(snapshot.syntax_color_overrides_dark),
        }
        self._populate_syntax_color_table(self._active_syntax_theme_key)
        self._lint_rule_overrides = {
            code: dict(value)
            for code, value in snapshot.lint_rule_overrides.items()
        }
        self._populate_linter_table()
        self._file_excludes_list.clear()
        for pattern in snapshot.file_exclude_patterns:
            self._file_excludes_list.addItem(pattern)
        self._refresh_shortcut_conflicts()
        self._refresh_syntax_validation()
        self._refresh_validation_state()

    def _apply_shortcut_snapshot(self, snapshot: EditorSettingsSnapshot) -> None:
        effective = build_effective_shortcut_map(snapshot.shortcut_overrides)
        self._is_updating_shortcut_editors = True
        try:
            for action_id, editor in self._shortcut_editors.items():
                editor.setKeySequence(QKeySequence(effective.get(action_id, "")))
        finally:
            self._is_updating_shortcut_editors = False

    def _handle_scope_changed(self, _index: int) -> None:
        if self._scope_input is None:
            return
        selected_scope = str(self._scope_input.currentData())
        if selected_scope == SETTINGS_SCOPE_PROJECT and not self._project_scope_available:
            self._scope_input.blockSignals(True)
            self._scope_input.setCurrentIndex(self._scope_input.findData(self._active_scope))
            self._scope_input.blockSignals(False)
            return
        if selected_scope not in {SETTINGS_SCOPE_GLOBAL, SETTINGS_SCOPE_PROJECT}:
            return
        if selected_scope == self._active_scope:
            return
        self._set_scope(selected_scope, apply_snapshot=True)

    def _set_scope(self, scope: str, *, apply_snapshot: bool) -> None:
        normalized_scope = scope
        if normalized_scope == SETTINGS_SCOPE_PROJECT and not self._project_scope_available:
            normalized_scope = SETTINGS_SCOPE_GLOBAL
        if normalized_scope not in {SETTINGS_SCOPE_GLOBAL, SETTINGS_SCOPE_PROJECT}:
            normalized_scope = SETTINGS_SCOPE_GLOBAL

        if normalized_scope != self._active_scope:
            self._capture_active_scope_snapshot()
        self._active_scope = normalized_scope
        if self._scope_input is not None:
            self._scope_input.blockSignals(True)
            self._scope_input.setCurrentIndex(self._scope_input.findData(normalized_scope))
            self._scope_input.blockSignals(False)
        if apply_snapshot:
            snapshot = self._scope_snapshots.get(normalized_scope, self._scope_snapshots[SETTINGS_SCOPE_GLOBAL])
            self._apply_snapshot_to_controls(snapshot)
        self._apply_scope_visibility()

    def _apply_scope_visibility(self) -> None:
        is_project_scope = self._active_scope == SETTINGS_SCOPE_PROJECT and self._project_scope_available
        if self._scope_banner_label is not None:
            if is_project_scope:
                self._scope_banner_label.setText(
                    "Project settings override global settings for this project. "
                    "Values shown here are inherited from global unless you change them."
                )
            else:
                self._scope_banner_label.setText(
                    "Global settings apply by default across projects."
                )
        if self._appearance_group is not None:
            self._appearance_group.setVisible(not is_project_scope)
        if self._output_reset_to_global_btn is not None:
            self._output_reset_to_global_btn.setVisible(is_project_scope)
        if self._editor_reset_to_global_btn is not None:
            self._editor_reset_to_global_btn.setVisible(is_project_scope)
        if self._intelligence_reset_to_global_btn is not None:
            self._intelligence_reset_to_global_btn.setVisible(is_project_scope)
        if self._linter_reset_to_global_btn is not None:
            self._linter_reset_to_global_btn.setVisible(is_project_scope)
        if self._file_excludes_reset_btn is not None:
            self._file_excludes_reset_btn.setText(
                "Reset to Global" if is_project_scope else "Reset to Defaults"
            )

        if self._tabs_widget is not None:
            if self._keybindings_tab_index is not None:
                self._set_tab_visible(self._keybindings_tab_index, not is_project_scope)
            if self._syntax_tab_index is not None:
                self._set_tab_visible(self._syntax_tab_index, not is_project_scope)

    def _set_tab_visible(self, index: int, visible: bool) -> None:
        if self._tabs_widget is None:
            return
        if hasattr(self._tabs_widget, "setTabVisible"):
            self._tabs_widget.setTabVisible(index, visible)
            return
        if self._tabs_widget.widget(index) is not None:
            self._tabs_widget.widget(index).setVisible(visible)

    def _handle_reset_output_group_to_global(self) -> None:
        baseline = self._scope_snapshots[SETTINGS_SCOPE_GLOBAL]
        self._auto_open_console_on_run_output_input.setChecked(baseline.auto_open_console_on_run_output)
        self._auto_open_problems_on_run_failure_input.setChecked(baseline.auto_open_problems_on_run_failure)

    def _handle_reset_editor_group_to_global(self) -> None:
        baseline = self._scope_snapshots[SETTINGS_SCOPE_GLOBAL]
        self._tab_width_input.setValue(baseline.tab_width)
        self._font_size_input.setValue(baseline.font_size)
        self._font_family_input.setCurrentFont(QFont(baseline.font_family))
        self._indent_style_input.setCurrentText(baseline.indent_style)
        self._indent_size_input.setValue(baseline.indent_size)
        self._detect_indentation_input.setChecked(baseline.detect_indentation_from_file)
        self._format_on_save_input.setChecked(baseline.format_on_save)
        self._trim_trailing_whitespace_on_save_input.setChecked(baseline.trim_trailing_whitespace_on_save)
        self._insert_final_newline_on_save_input.setChecked(baseline.insert_final_newline_on_save)

    def _handle_reset_intelligence_group_to_global(self) -> None:
        baseline = self._scope_snapshots[SETTINGS_SCOPE_GLOBAL]
        self._completion_enabled_input.setChecked(baseline.completion_enabled)
        self._completion_auto_trigger_input.setChecked(baseline.completion_auto_trigger)
        self._completion_min_chars_input.setValue(baseline.completion_min_chars)
        self._linter_enabled_input.setChecked(baseline.diagnostics_enabled)
        self._diagnostics_realtime_input.setChecked(baseline.diagnostics_realtime)
        self._quick_fixes_enabled_input.setChecked(baseline.quick_fixes_enabled)
        self._quick_fix_multifile_preview_input.setChecked(baseline.quick_fix_require_preview_for_multifile)
        self._cache_enabled_input.setChecked(baseline.cache_enabled)
        self._incremental_indexing_input.setChecked(baseline.incremental_indexing)
        self._metrics_logging_input.setChecked(baseline.metrics_logging_enabled)
        self._force_reindex_on_open_input.setChecked(baseline.force_full_reindex_on_open)
        provider_index = self._linter_provider_input.findData(baseline.selected_linter)
        self._linter_provider_input.setCurrentIndex(provider_index if provider_index >= 0 else 0)
        self._sync_linter_control_states()

    def _populate_shortcut_table(self, snapshot: EditorSettingsSnapshot) -> None:
        defaults = default_shortcut_map()
        effective = build_effective_shortcut_map(snapshot.shortcut_overrides)
        self._shortcut_table.setRowCount(len(SHORTCUT_COMMANDS))
        for row_index, command in enumerate(SHORTCUT_COMMANDS):
            self._shortcut_rows[command.action_id] = row_index
            command_item = QTableWidgetItem(f"{command.category} / {command.label}")
            command_item.setData(Qt.UserRole, command.action_id)
            self._shortcut_table.setItem(row_index, 0, command_item)

            editor = QKeySequenceEdit(self._shortcut_table)
            current_shortcut = effective.get(command.action_id, "")
            if current_shortcut:
                editor.setKeySequence(QKeySequence(current_shortcut))
            editor.keySequenceChanged.connect(
                lambda _sequence, action_id=command.action_id: self._handle_shortcut_changed(action_id)
            )
            self._shortcut_editors[command.action_id] = editor
            self._shortcut_table.setCellWidget(row_index, 1, editor)

            default_item = QTableWidgetItem(defaults.get(command.action_id, ""))
            self._shortcut_table.setItem(row_index, 2, default_item)

            reset_button = QPushButton("Reset", self._shortcut_table)
            reset_button.clicked.connect(
                lambda _checked=False, action_id=command.action_id: self._handle_reset_shortcut(action_id)
            )
            self._shortcut_table.setCellWidget(row_index, 3, reset_button)

    def _handle_reset_shortcut(self, action_id: str) -> None:
        editor = self._shortcut_editors.get(action_id)
        if editor is None:
            return
        default_shortcuts = default_shortcut_map()
        self._is_updating_shortcut_editors = True
        editor.setKeySequence(QKeySequence(default_shortcuts.get(action_id, "")))
        self._is_updating_shortcut_editors = False
        self._refresh_shortcut_conflicts()

    def _handle_shortcut_changed(self, action_id: str) -> None:
        if self._is_updating_shortcut_editors:
            self._refresh_shortcut_conflicts()
            return
        editor = self._shortcut_editors.get(action_id)
        if editor is None:
            self._refresh_shortcut_conflicts()
            return
        assigned_shortcut = normalize_shortcut(editor.keySequence().toString())
        if not assigned_shortcut or not editor.hasFocus():
            self._refresh_shortcut_conflicts()
            return
        conflicting_action_ids = [
            conflict_action_id
            for conflict_action_id, shortcut in self._current_shortcut_map().items()
            if conflict_action_id != action_id and normalize_shortcut(shortcut) == assigned_shortcut
        ]
        if not conflicting_action_ids:
            self._refresh_shortcut_conflicts()
            return
        command_labels = {
            command.action_id: f"{command.category} / {command.label}"
            for command in SHORTCUT_COMMANDS
        }
        conflict_names = ", ".join(command_labels.get(item, item) for item in conflicting_action_ids)
        choice = QMessageBox.question(
            self,
            "Shortcut Conflict",
            (
                f"'{assigned_shortcut}' is already assigned to {conflict_names}.\n\n"
                "Do you want to reassign it to this command?"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        self._is_updating_shortcut_editors = True
        try:
            if choice == QMessageBox.Yes:
                for conflict_action_id in conflicting_action_ids:
                    conflict_editor = self._shortcut_editors.get(conflict_action_id)
                    if conflict_editor is not None:
                        conflict_editor.setKeySequence(QKeySequence())
            else:
                editor.setKeySequence(QKeySequence())
        finally:
            self._is_updating_shortcut_editors = False
        self._refresh_shortcut_conflicts()

    def _handle_reset_all_shortcuts(self) -> None:
        defaults = default_shortcut_map()
        self._is_updating_shortcut_editors = True
        try:
            for action_id, editor in self._shortcut_editors.items():
                editor.setKeySequence(QKeySequence(defaults.get(action_id, "")))
        finally:
            self._is_updating_shortcut_editors = False
        self._refresh_shortcut_conflicts()

    def _filter_shortcut_rows(self, query: str) -> None:
        lowered = query.strip().lower()
        for action_id, row_index in self._shortcut_rows.items():
            item = self._shortcut_table.item(row_index, 0)
            if item is None:
                continue
            text = item.text().lower()
            should_show = not lowered or lowered in text or lowered in action_id.lower()
            self._shortcut_table.setRowHidden(row_index, not should_show)

    def _current_shortcut_map(self) -> dict[str, str]:
        current: dict[str, str] = {}
        for action_id, editor in self._shortcut_editors.items():
            current[action_id] = normalize_shortcut(editor.keySequence().toString())
        return current

    def _refresh_shortcut_conflicts(self) -> None:
        conflicts = find_shortcut_conflicts(self._current_shortcut_map())
        if conflicts:
            details = [f"{shortcut}: {', '.join(action_ids)}" for shortcut, action_ids in sorted(conflicts.items())]
            self._shortcut_conflict_label.setText("Conflicting shortcuts:\n" + "\n".join(details[:4]))
            self._shortcut_conflict_label.setVisible(True)
            self._has_shortcut_conflicts = True
        else:
            self._shortcut_conflict_label.clear()
            self._shortcut_conflict_label.setVisible(False)
            self._has_shortcut_conflicts = False
        self._refresh_validation_state()

    def _shortcut_overrides_snapshot(self) -> dict[str, str]:
        overrides: dict[str, str] = {}
        defaults = default_shortcut_map()
        for action_id, current_shortcut in self._current_shortcut_map().items():
            default_shortcut = normalize_shortcut(defaults.get(action_id, ""))
            if current_shortcut == default_shortcut:
                continue
            overrides[action_id] = current_shortcut if current_shortcut else ""
        return overrides

    def _syntax_defaults_for_theme(self, theme_key: str) -> dict[str, str]:
        return dict(DEFAULT_DARK_PALETTE if theme_key == THEME_DARK else DEFAULT_LIGHT_PALETTE)

    def _populate_syntax_color_table(self, theme_key: str) -> None:
        self._active_syntax_theme_key = theme_key
        self._syntax_color_inputs.clear()
        self._syntax_color_row_by_token.clear()
        defaults = self._syntax_defaults_for_theme(theme_key)
        overrides = self._syntax_color_overrides_by_theme.setdefault(theme_key, {})
        self._syntax_color_table.setRowCount(len(SYNTAX_COLOR_TOKENS))
        for row_index, token in enumerate(SYNTAX_COLOR_TOKENS):
            self._syntax_color_row_by_token[token.key] = row_index
            label_item = QTableWidgetItem(f"{token.category} / {token.label}")
            self._syntax_color_table.setItem(row_index, 0, label_item)

            color_input = QLineEdit(self._syntax_color_table)
            color_input.setPlaceholderText(defaults.get(token.key, ""))
            effective_color = overrides.get(token.key, defaults.get(token.key, ""))
            color_input.setText(effective_color)
            color_input.textEdited.connect(
                lambda _text, key=token.key: self._handle_syntax_color_text_edited(key)
            )
            self._syntax_color_inputs[token.key] = color_input
            self._syntax_color_table.setCellWidget(row_index, 1, color_input)

            pick_button = QPushButton("Pick", self._syntax_color_table)
            pick_button.clicked.connect(
                lambda _checked=False, key=token.key: self._handle_pick_syntax_color(key)
            )
            self._syntax_color_table.setCellWidget(row_index, 2, pick_button)

            reset_button = QPushButton("Reset", self._syntax_color_table)
            reset_button.clicked.connect(
                lambda _checked=False, key=token.key: self._handle_reset_syntax_color(key)
            )
            self._syntax_color_table.setCellWidget(row_index, 3, reset_button)

        self._refresh_syntax_validation()

    def _handle_syntax_theme_changed(self, _index: int) -> None:
        theme_key = str(self._syntax_theme_input.currentData())
        if theme_key not in {THEME_LIGHT, THEME_DARK}:
            theme_key = THEME_LIGHT
        self._populate_syntax_color_table(theme_key)

    def _handle_pick_syntax_color(self, token_key: str) -> None:
        input_widget = self._syntax_color_inputs.get(token_key)
        if input_widget is None:
            return
        current = normalize_hex_color(input_widget.text()) or input_widget.placeholderText()
        chosen = QColorDialog.getColor(
            initial=QColor(current if current else "#FFFFFF"),
            parent=self,
            title="Choose syntax color",
        )
        if not chosen.isValid():
            return
        input_widget.setText(chosen.name().upper())
        self._handle_syntax_color_text_edited(token_key)

    def _handle_reset_syntax_color(self, token_key: str) -> None:
        defaults = self._syntax_defaults_for_theme(self._active_syntax_theme_key)
        overrides = self._syntax_color_overrides_by_theme.setdefault(self._active_syntax_theme_key, {})
        overrides.pop(token_key, None)
        input_widget = self._syntax_color_inputs.get(token_key)
        if input_widget is not None:
            input_widget.setText(defaults.get(token_key, ""))
        self._refresh_syntax_validation()

    def _handle_syntax_color_text_edited(self, token_key: str) -> None:
        input_widget = self._syntax_color_inputs.get(token_key)
        if input_widget is None:
            return
        overrides = self._syntax_color_overrides_by_theme.setdefault(self._active_syntax_theme_key, {})
        defaults = self._syntax_defaults_for_theme(self._active_syntax_theme_key)
        raw_text = input_widget.text().strip()
        if not raw_text:
            overrides.pop(token_key, None)
            input_widget.setText(defaults.get(token_key, ""))
            self._refresh_syntax_validation()
            return
        normalized = normalize_hex_color(input_widget.text())
        if normalized is None:
            self._refresh_syntax_validation()
            return
        if normalized == defaults.get(token_key):
            overrides.pop(token_key, None)
        else:
            overrides[token_key] = normalized
        input_widget.setText(normalized)
        self._refresh_syntax_validation()

    def _refresh_syntax_validation(self) -> None:
        invalid_entries: list[str] = []
        for token_key, input_widget in self._syntax_color_inputs.items():
            if not input_widget.text().strip():
                input_widget.setStyleSheet("")
                continue
            normalized = normalize_hex_color(input_widget.text())
            if normalized is None:
                input_widget.setStyleSheet("border: 1px solid #C92A2A;")
                invalid_entries.append(token_key)
            else:
                input_widget.setStyleSheet("")
        if invalid_entries:
            preview = ", ".join(invalid_entries[:5])
            self._syntax_validation_label.setText(
                f"Invalid syntax colors for: {preview}. Use #RRGGBB format."
            )
            self._syntax_validation_label.setVisible(True)
            self._has_invalid_syntax_colors = True
        else:
            self._syntax_validation_label.clear()
            self._syntax_validation_label.setVisible(False)
            self._has_invalid_syntax_colors = False
        self._refresh_validation_state()

    def _handle_linter_enabled_toggled(self, _checked: bool) -> None:
        self._sync_linter_control_states()

    def _sync_linter_control_states(self) -> None:
        enabled = self._linter_enabled_input.isChecked()
        self._linter_provider_input.setEnabled(enabled)
        self._linter_table.setEnabled(enabled)

    def _populate_linter_table(self) -> None:
        self._lint_enabled_inputs.clear()
        self._lint_severity_inputs.clear()
        self._linter_table.setRowCount(len(LINT_RULE_DEFINITIONS))
        severity_values = [LINT_SEVERITY_ERROR, LINT_SEVERITY_WARNING, LINT_SEVERITY_INFO]
        for row_index, definition in enumerate(LINT_RULE_DEFINITIONS):
            code_item = QTableWidgetItem(definition.code)
            self._linter_table.setItem(row_index, 0, code_item)
            rule_item = QTableWidgetItem(definition.title)
            self._linter_table.setItem(row_index, 1, rule_item)

            override_payload = self._lint_rule_overrides.get(definition.code, {})
            enabled_value = bool(override_payload.get("enabled", definition.default_enabled))
            enabled_input = QCheckBox(self._linter_table)
            enabled_input.setChecked(enabled_value)
            enabled_input.setEnabled(definition.allow_disable)
            enabled_input.stateChanged.connect(
                lambda _state, code=definition.code: self._handle_lint_enabled_changed(code)
            )
            self._linter_table.setCellWidget(row_index, 2, enabled_input)
            self._lint_enabled_inputs[definition.code] = enabled_input

            severity_input = QComboBox(self._linter_table)
            for severity in severity_values:
                severity_input.addItem(severity.upper(), severity)
            severity_value = str(override_payload.get("severity", definition.default_severity))
            selected_index = severity_input.findData(severity_value)
            severity_input.setCurrentIndex(selected_index if selected_index >= 0 else 0)
            severity_input.setEnabled(definition.allow_severity_override)
            severity_input.currentIndexChanged.connect(
                lambda _idx, code=definition.code: self._handle_lint_severity_changed(code)
            )
            self._linter_table.setCellWidget(row_index, 3, severity_input)
            self._lint_severity_inputs[definition.code] = severity_input

            reset_button = QPushButton("Reset", self._linter_table)
            reset_button.clicked.connect(
                lambda _checked=False, code=definition.code: self._handle_reset_lint_rule(code)
            )
            self._linter_table.setCellWidget(row_index, 4, reset_button)

    def _handle_lint_enabled_changed(self, code: str) -> None:
        definition = next((item for item in LINT_RULE_DEFINITIONS if item.code == code), None)
        if definition is None:
            return
        enabled_input = self._lint_enabled_inputs.get(code)
        if enabled_input is None:
            return
        override = self._lint_rule_overrides.setdefault(code, {})
        if definition.allow_disable:
            override["enabled"] = enabled_input.isChecked()
        self._normalize_lint_rule_override(code)

    def _handle_lint_severity_changed(self, code: str) -> None:
        definition = next((item for item in LINT_RULE_DEFINITIONS if item.code == code), None)
        if definition is None:
            return
        severity_input = self._lint_severity_inputs.get(code)
        if severity_input is None:
            return
        override = self._lint_rule_overrides.setdefault(code, {})
        if definition.allow_severity_override:
            override["severity"] = str(severity_input.currentData())
        self._normalize_lint_rule_override(code)

    def _handle_reset_lint_rule(self, code: str) -> None:
        definition = next((item for item in LINT_RULE_DEFINITIONS if item.code == code), None)
        if definition is None:
            return
        self._lint_rule_overrides.pop(code, None)
        baseline_snapshot = self._scope_snapshots.get(SETTINGS_SCOPE_GLOBAL)
        baseline_override = None
        if (
            self._active_scope == SETTINGS_SCOPE_PROJECT
            and baseline_snapshot is not None
            and code in baseline_snapshot.lint_rule_overrides
        ):
            baseline_override = baseline_snapshot.lint_rule_overrides.get(code, {})
        enabled_input = self._lint_enabled_inputs.get(code)
        if enabled_input is not None:
            if isinstance(baseline_override, dict) and "enabled" in baseline_override:
                enabled_input.setChecked(bool(baseline_override.get("enabled")))
            else:
                enabled_input.setChecked(definition.default_enabled)
        severity_input = self._lint_severity_inputs.get(code)
        if severity_input is not None:
            baseline_severity = None
            if isinstance(baseline_override, dict):
                severity_raw = baseline_override.get("severity")
                if isinstance(severity_raw, str):
                    baseline_severity = severity_raw
            index = severity_input.findData(baseline_severity or definition.default_severity)
            severity_input.setCurrentIndex(index if index >= 0 else 0)

    def _normalize_lint_rule_override(self, code: str) -> None:
        definition = next((item for item in LINT_RULE_DEFINITIONS if item.code == code), None)
        if definition is None:
            self._lint_rule_overrides.pop(code, None)
            return
        override = self._lint_rule_overrides.get(code, {})
        normalized: dict[str, object] = {}
        enabled = override.get("enabled")
        if definition.allow_disable and isinstance(enabled, bool) and enabled != definition.default_enabled:
            normalized["enabled"] = enabled
        severity = override.get("severity")
        if (
            definition.allow_severity_override
            and isinstance(severity, str)
            and severity in {LINT_SEVERITY_ERROR, LINT_SEVERITY_WARNING, LINT_SEVERITY_INFO}
            and severity != definition.default_severity
        ):
            normalized["severity"] = severity
        if normalized:
            self._lint_rule_overrides[code] = normalized
        else:
            self._lint_rule_overrides.pop(code, None)

    def _lint_rule_overrides_snapshot(self) -> dict[str, dict[str, object]]:
        return {code: dict(value) for code, value in self._lint_rule_overrides.items()}

    def _file_exclude_patterns_snapshot(self) -> list[str]:
        patterns: list[str] = []
        for i in range(self._file_excludes_list.count()):
            item = self._file_excludes_list.item(i)
            if item is not None:
                text = item.text().strip()
                if text:
                    patterns.append(text)
        return patterns

    def _handle_add_file_exclude(self) -> None:
        text = self._file_exclude_input.text().strip()
        if not text:
            return
        for part in text.split(","):
            pattern = part.strip()
            if not pattern:
                continue
            existing = [
                self._file_excludes_list.item(i).text()
                for i in range(self._file_excludes_list.count())
                if self._file_excludes_list.item(i) is not None
            ]
            if pattern not in existing:
                self._file_excludes_list.addItem(pattern)
        self._file_exclude_input.clear()

    def _handle_remove_file_exclude(self) -> None:
        selected = self._file_excludes_list.currentRow()
        if selected >= 0:
            self._file_excludes_list.takeItem(selected)

    def _handle_reset_file_excludes(self) -> None:
        self._file_excludes_list.clear()
        baseline_patterns = DEFAULT_EXCLUDE_PATTERNS
        if self._active_scope == SETTINGS_SCOPE_PROJECT:
            baseline_patterns = self._scope_snapshots[SETTINGS_SCOPE_GLOBAL].file_exclude_patterns
        for pattern in baseline_patterns:
            self._file_excludes_list.addItem(pattern)

    def _handle_reset_linter_overrides_to_global(self) -> None:
        self._lint_rule_overrides.clear()
        self._populate_linter_table()
        baseline_snapshot = self._scope_snapshots.get(SETTINGS_SCOPE_GLOBAL)
        if self._active_scope != SETTINGS_SCOPE_PROJECT or baseline_snapshot is None:
            return
        for definition in LINT_RULE_DEFINITIONS:
            baseline_override = baseline_snapshot.lint_rule_overrides.get(definition.code, {})
            enabled_input = self._lint_enabled_inputs.get(definition.code)
            if enabled_input is not None:
                if isinstance(baseline_override.get("enabled"), bool):
                    enabled_input.setChecked(bool(baseline_override["enabled"]))
                else:
                    enabled_input.setChecked(definition.default_enabled)
            severity_input = self._lint_severity_inputs.get(definition.code)
            if severity_input is not None:
                baseline_severity = baseline_override.get("severity")
                if not isinstance(baseline_severity, str):
                    baseline_severity = definition.default_severity
                index = severity_input.findData(baseline_severity)
                severity_input.setCurrentIndex(index if index >= 0 else 0)

    def _refresh_validation_state(self) -> None:
        if self._ok_button is None:
            return
        if self._active_scope == SETTINGS_SCOPE_PROJECT:
            self._ok_button.setEnabled(True)
            return
        self._ok_button.setEnabled(not (self._has_shortcut_conflicts or self._has_invalid_syntax_colors))
