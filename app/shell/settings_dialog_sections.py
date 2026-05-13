"""Builder helpers for SettingsDialog tab sections."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide2.QtCore import Qt
from PySide2.QtGui import QKeySequence
from PySide2.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app.core import constants
from app.shell.settings_models import EditorSettingsSnapshot, SETTINGS_SCOPE_GLOBAL, SETTINGS_SCOPE_PROJECT
from app.shell.syntax_color_preferences import (
    THEME_DARK,
    THEME_HC_DARK,
    THEME_HC_LIGHT,
    THEME_LIGHT,
)

if TYPE_CHECKING:
    from app.shell.settings_dialog import SettingsDialog


def build_keybindings_tab(dialog: "SettingsDialog", tabs: QTabWidget, snapshot: EditorSettingsSnapshot) -> None:
    keybindings_tab = QWidget(tabs)
    keybindings_layout = QVBoxLayout(keybindings_tab)
    dialog._keybindings_tab_index = tabs.addTab(keybindings_tab, "Keybindings")

    dialog._shortcut_search_input = QLineEdit(keybindings_tab)
    dialog._shortcut_search_input.setObjectName("shell.settingsDialog.shortcutSearch")
    dialog._shortcut_search_input.setPlaceholderText("Search commands...")
    dialog._shortcut_search_input.textChanged.connect(dialog._filter_shortcut_rows)
    keybindings_layout.addWidget(dialog._shortcut_search_input)

    dialog._shortcut_reset_all_btn = QPushButton("Reset All Keybindings", keybindings_tab)
    dialog._shortcut_reset_all_btn.setObjectName("shell.settingsDialog.resetAllShortcuts")
    dialog._shortcut_reset_all_btn.clicked.connect(dialog._handle_reset_all_shortcuts)
    keybindings_layout.addWidget(dialog._shortcut_reset_all_btn)

    dialog._shortcut_conflict_label = QLabel(keybindings_tab)
    dialog._shortcut_conflict_label.setObjectName("shell.settingsDialog.shortcutConflict")
    dialog._shortcut_conflict_label.setWordWrap(True)
    dialog._shortcut_conflict_label.setVisible(False)
    keybindings_layout.addWidget(dialog._shortcut_conflict_label)

    dialog._shortcut_table = QTableWidget(0, 4, keybindings_tab)
    dialog._shortcut_table.setObjectName("shell.settingsDialog.shortcutTable")
    dialog._shortcut_table.setHorizontalHeaderLabels(["Command", "Shortcut", "Default", "Reset"])
    dialog._shortcut_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    dialog._shortcut_table.setSelectionMode(QAbstractItemView.NoSelection)
    dialog._shortcut_table.setFocusPolicy(Qt.NoFocus)
    dialog._shortcut_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
    dialog._shortcut_table.verticalHeader().setVisible(False)
    header = dialog._shortcut_table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.Stretch)
    keybindings_layout.addWidget(dialog._shortcut_table, 1)
    dialog._populate_shortcut_table(snapshot)


def build_syntax_tab(dialog: "SettingsDialog", tabs: QTabWidget) -> None:
    syntax_tab = QWidget(tabs)
    syntax_layout = QVBoxLayout(syntax_tab)
    dialog._syntax_tab_index = tabs.addTab(syntax_tab, "Syntax Colors")

    dialog._syntax_theme_input = QComboBox(syntax_tab)
    dialog._syntax_theme_input.setObjectName("shell.settingsDialog.syntaxThemeInput")
    dialog._syntax_theme_input.addItem("Light Theme", THEME_LIGHT)
    dialog._syntax_theme_input.addItem("Dark Theme", THEME_DARK)
    dialog._syntax_theme_input.addItem("High Contrast Light", THEME_HC_LIGHT)
    dialog._syntax_theme_input.addItem("High Contrast Dark", THEME_HC_DARK)
    dialog._syntax_theme_input.currentIndexChanged.connect(dialog._handle_syntax_theme_changed)
    syntax_layout.addWidget(dialog._syntax_theme_input)

    dialog._syntax_validation_label = QLabel(syntax_tab)
    dialog._syntax_validation_label.setObjectName("shell.settingsDialog.syntaxValidation")
    dialog._syntax_validation_label.setWordWrap(True)
    dialog._syntax_validation_label.setVisible(False)
    syntax_layout.addWidget(dialog._syntax_validation_label)

    dialog._syntax_color_table = QTableWidget(0, 4, syntax_tab)
    dialog._syntax_color_table.setObjectName("shell.settingsDialog.syntaxColorTable")
    dialog._syntax_color_table.setHorizontalHeaderLabels(["Token", "Color", "Pick", "Reset"])
    dialog._syntax_color_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    dialog._syntax_color_table.setSelectionMode(QAbstractItemView.NoSelection)
    dialog._syntax_color_table.setFocusPolicy(Qt.NoFocus)
    dialog._syntax_color_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
    dialog._syntax_color_table.verticalHeader().setVisible(False)
    syntax_header = dialog._syntax_color_table.horizontalHeader()
    syntax_header.setSectionResizeMode(0, QHeaderView.Stretch)
    syntax_layout.addWidget(dialog._syntax_color_table, 1)
    dialog._populate_syntax_color_table(dialog._active_syntax_theme_key)


def build_linter_tab(
    dialog: "SettingsDialog",
    tabs: QTabWidget,
    snapshot: EditorSettingsSnapshot,
    project_snapshot: EditorSettingsSnapshot | None,
) -> None:
    linter_tab = QWidget(tabs)
    linter_layout = QVBoxLayout(linter_tab)
    tabs.addTab(linter_tab, "Linter")

    if dialog._project_scope_available and project_snapshot is not None:
        if snapshot.selected_linter != project_snapshot.selected_linter:
            scope_hint = QLabel(
                "The effective linter for this project differs from global. "
                "Switch to Project scope to edit the provider used for this project."
            )
            scope_hint.setObjectName("shell.settingsDialog.linterProviderScopeHint")
            scope_hint.setWordWrap(True)
            dialog._linter_provider_scope_hint = scope_hint
            linter_layout.addWidget(scope_hint)

    linter_controls = QGroupBox("Provider")
    linter_controls.setObjectName("shell.settingsDialog.linterProviderGroup")
    linter_controls_form = QFormLayout(linter_controls)
    linter_controls_form.setVerticalSpacing(10)
    linter_controls_form.setHorizontalSpacing(16)
    dialog._linter_enabled_input = QCheckBox(linter_controls)
    dialog._linter_enabled_input.setChecked(snapshot.diagnostics_enabled)
    dialog._linter_enabled_input.toggled.connect(dialog._handle_linter_enabled_toggled)
    linter_controls_form.addRow("Enable Python linting", dialog._linter_enabled_input)
    dialog._linter_provider_input = QComboBox(linter_controls)
    dialog._linter_provider_input.addItem("Default (built-in)", constants.LINTER_PROVIDER_DEFAULT)
    dialog._linter_provider_input.addItem("Pyflakes", constants.LINTER_PROVIDER_PYFLAKES)
    provider_index = dialog._linter_provider_input.findData(snapshot.selected_linter)
    dialog._linter_provider_input.setCurrentIndex(provider_index if provider_index >= 0 else 0)
    linter_controls_form.addRow("Linter provider", dialog._linter_provider_input)
    linter_layout.addWidget(linter_controls)

    dialog._linter_table = QTableWidget(0, 5, linter_tab)
    dialog._linter_table.setObjectName("shell.settingsDialog.linterTable")
    dialog._linter_table.setHorizontalHeaderLabels(["Code", "Rule", "Enabled", "Severity", "Reset"])
    dialog._linter_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    dialog._linter_table.setSelectionMode(QAbstractItemView.NoSelection)
    dialog._linter_table.setFocusPolicy(Qt.NoFocus)
    dialog._linter_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
    dialog._linter_table.verticalHeader().setVisible(False)
    linter_header = dialog._linter_table.horizontalHeader()
    linter_header.setSectionResizeMode(1, QHeaderView.Stretch)
    linter_layout.addWidget(dialog._linter_table, 1)
    dialog._populate_linter_table()
    linter_reset_to_global_btn = QPushButton("Reset Linter Overrides to Global", linter_tab)
    linter_reset_to_global_btn.setObjectName("shell.settingsDialog.linterResetGlobal")
    linter_reset_to_global_btn.clicked.connect(dialog._handle_reset_linter_overrides_to_global)
    dialog._linter_reset_to_global_btn = linter_reset_to_global_btn
    linter_layout.addWidget(linter_reset_to_global_btn)
    dialog._sync_linter_control_states()


def build_files_tab(dialog: "SettingsDialog", tabs: QTabWidget, snapshot: EditorSettingsSnapshot) -> None:
    files_tab = QWidget(tabs)
    files_layout = QVBoxLayout(files_tab)
    tabs.addTab(files_tab, "Files")

    excludes_group = QGroupBox("File Exclusions")
    excludes_group.setObjectName("shell.settingsDialog.fileExcludesGroup")
    excludes_vbox = QVBoxLayout(excludes_group)

    excludes_help = QLabel(
        "Glob patterns for files and folders to hide from the explorer, "
        "Quick Open, and search results. Patterns are matched against "
        "names and relative paths."
    )
    excludes_help.setObjectName("shell.settingsDialog.fileExcludesHelp")
    excludes_help.setWordWrap(True)
    excludes_vbox.addWidget(excludes_help)

    dialog._file_excludes_list = QListWidget(excludes_group)
    dialog._file_excludes_list.setObjectName("shell.settingsDialog.fileExcludesList")
    for pattern in snapshot.file_exclude_patterns:
        dialog._file_excludes_list.addItem(pattern)
    excludes_vbox.addWidget(dialog._file_excludes_list, 1)

    add_row = QHBoxLayout()
    dialog._file_exclude_input = QLineEdit(excludes_group)
    dialog._file_exclude_input.setObjectName("shell.settingsDialog.fileExcludeInput")
    dialog._file_exclude_input.setPlaceholderText("e.g. *.pyc, build, .mypy_cache")
    dialog._file_exclude_input.returnPressed.connect(dialog._handle_add_file_exclude)
    add_row.addWidget(dialog._file_exclude_input, 1)
    add_btn = QPushButton("Add", excludes_group)
    add_btn.setObjectName("shell.settingsDialog.addExcludeBtn")
    add_btn.clicked.connect(dialog._handle_add_file_exclude)
    add_row.addWidget(add_btn)
    excludes_vbox.addLayout(add_row)

    btn_row = QHBoxLayout()
    remove_btn = QPushButton("Remove Selected", excludes_group)
    remove_btn.setObjectName("shell.settingsDialog.removeExcludeBtn")
    remove_btn.clicked.connect(dialog._handle_remove_file_exclude)
    btn_row.addWidget(remove_btn)
    reset_btn = QPushButton("Reset to Defaults", excludes_group)
    reset_btn.setObjectName("shell.settingsDialog.resetExcludesBtn")
    dialog._file_excludes_reset_btn = reset_btn
    reset_btn.clicked.connect(dialog._handle_reset_file_excludes)
    btn_row.addWidget(reset_btn)
    btn_row.addStretch(1)
    excludes_vbox.addLayout(btn_row)
    files_layout.addWidget(excludes_group)

    local_history_group = QGroupBox("Local History")
    local_history_group.setObjectName("shell.settingsDialog.localHistoryGroup")
    local_history_layout = QVBoxLayout(local_history_group)

    local_history_help = QLabel(
        "Bound local history storage per project. Excluded patterns skip durable history checkpoints while keeping normal editing and save behavior."
    )
    local_history_help.setObjectName("shell.settingsDialog.localHistoryHelp")
    local_history_help.setWordWrap(True)
    local_history_layout.addWidget(local_history_help)

    local_history_form = QFormLayout()
    local_history_form.setVerticalSpacing(10)
    local_history_form.setHorizontalSpacing(16)
    dialog._local_history_max_checkpoints_input = QSpinBox(local_history_group)
    dialog._local_history_max_checkpoints_input.setRange(1, 500)
    dialog._local_history_max_checkpoints_input.setValue(snapshot.local_history_max_checkpoints_per_file)
    local_history_form.addRow("Max revisions per file", dialog._local_history_max_checkpoints_input)

    dialog._local_history_retention_days_input = QSpinBox(local_history_group)
    dialog._local_history_retention_days_input.setRange(1, 3650)
    dialog._local_history_retention_days_input.setValue(snapshot.local_history_retention_days)
    local_history_form.addRow("Retention days", dialog._local_history_retention_days_input)

    dialog._local_history_max_tracked_file_kb_input = QSpinBox(local_history_group)
    dialog._local_history_max_tracked_file_kb_input.setRange(1, 1024 * 100)
    dialog._local_history_max_tracked_file_kb_input.setValue(
        max(1, int((snapshot.local_history_max_tracked_file_bytes + 1023) / 1024))
    )
    local_history_form.addRow("Max tracked file size (KB)", dialog._local_history_max_tracked_file_kb_input)
    local_history_layout.addLayout(local_history_form)

    local_history_excludes_help = QLabel(
        "Skip durable local-history checkpoints for files matching these glob patterns."
    )
    local_history_excludes_help.setObjectName("shell.settingsDialog.localHistoryExcludesHelp")
    local_history_excludes_help.setWordWrap(True)
    local_history_layout.addWidget(local_history_excludes_help)

    dialog._local_history_excludes_list = QListWidget(local_history_group)
    dialog._local_history_excludes_list.setObjectName("shell.settingsDialog.localHistoryExcludesList")
    for pattern in snapshot.local_history_exclude_patterns:
        dialog._local_history_excludes_list.addItem(pattern)
    local_history_layout.addWidget(dialog._local_history_excludes_list, 1)

    local_history_add_row = QHBoxLayout()
    dialog._local_history_exclude_input = QLineEdit(local_history_group)
    dialog._local_history_exclude_input.setObjectName("shell.settingsDialog.localHistoryExcludeInput")
    dialog._local_history_exclude_input.setPlaceholderText("e.g. *.bin, export/*.json")
    dialog._local_history_exclude_input.returnPressed.connect(dialog._handle_add_local_history_exclude)
    local_history_add_row.addWidget(dialog._local_history_exclude_input, 1)
    local_history_add_btn = QPushButton("Add", local_history_group)
    local_history_add_btn.setObjectName("shell.settingsDialog.addLocalHistoryExcludeBtn")
    local_history_add_btn.clicked.connect(dialog._handle_add_local_history_exclude)
    local_history_add_row.addWidget(local_history_add_btn)
    local_history_layout.addLayout(local_history_add_row)

    local_history_button_row = QHBoxLayout()
    local_history_remove_btn = QPushButton("Remove Selected", local_history_group)
    local_history_remove_btn.setObjectName("shell.settingsDialog.removeLocalHistoryExcludeBtn")
    local_history_remove_btn.clicked.connect(dialog._handle_remove_local_history_exclude)
    local_history_button_row.addWidget(local_history_remove_btn)
    local_history_reset_btn = QPushButton("Reset to Defaults", local_history_group)
    local_history_reset_btn.setObjectName("shell.settingsDialog.resetLocalHistoryBtn")
    local_history_reset_btn.clicked.connect(dialog._handle_reset_local_history_settings)
    dialog._local_history_reset_btn = local_history_reset_btn
    local_history_button_row.addWidget(local_history_reset_btn)
    local_history_button_row.addStretch(1)
    local_history_layout.addLayout(local_history_button_row)

    files_layout.addWidget(local_history_group)
    files_layout.addStretch(1)


def build_buttons_row(dialog: "SettingsDialog", layout: QVBoxLayout) -> None:
    from PySide2.QtGui import QIcon
    from PySide2.QtWidgets import QDialogButtonBox

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=dialog)
    buttons.setObjectName("shell.settingsDialog.buttonBox")
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    dialog._ok_button = buttons.button(QDialogButtonBox.Ok)
    if dialog._ok_button is not None:
        dialog._ok_button.setObjectName("shell.settingsDialog.okBtn")
        dialog._ok_button.setIcon(QIcon())
    cancel_button = buttons.button(QDialogButtonBox.Cancel)
    if cancel_button is not None:
        cancel_button.setObjectName("shell.settingsDialog.cancelBtn")
        cancel_button.setIcon(QIcon())


def apply_initial_scope(dialog: "SettingsDialog", initial_scope: str) -> None:
    normalized_initial_scope = initial_scope
    if normalized_initial_scope not in {SETTINGS_SCOPE_GLOBAL, SETTINGS_SCOPE_PROJECT}:
        normalized_initial_scope = SETTINGS_SCOPE_GLOBAL
    if normalized_initial_scope == SETTINGS_SCOPE_PROJECT and not dialog._project_scope_available:
        normalized_initial_scope = SETTINGS_SCOPE_GLOBAL
    dialog._set_scope(normalized_initial_scope, apply_snapshot=True)
