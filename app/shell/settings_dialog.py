"""Qt settings dialog for editor/intelligence preferences."""

from __future__ import annotations

from PySide2.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from PySide2.QtGui import QColor, QFont, QIcon
from PySide2.QtCore import Qt
from PySide2.QtGui import QKeySequence

from app.project.file_excludes import DEFAULT_EXCLUDE_PATTERNS
from app.shell.settings_dialog_general import (
    apply_general_tab_state_to_controls,
    build_general_tab,
    general_tab_state_from_controls,
)
from app.shell.settings_dialog_handlers import SettingsDialogHandlersMixin
from app.shell.settings_dialog_state import GeneralTabState
from app.shell.settings_dialog_tables import (
    finalize_keybindings_columns,
    finalize_linter_columns,
    finalize_syntax_columns,
)
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
    THEME_HC_DARK,
    THEME_HC_LIGHT,
    THEME_LIGHT,
    normalize_hex_color,
)
from app.editors.syntax_engine import (
    DEFAULT_DARK_PALETTE,
    DEFAULT_HC_DARK_PALETTE,
    DEFAULT_HC_LIGHT_PALETTE,
    DEFAULT_LIGHT_PALETTE,
)


_VALID_SYNTAX_THEME_KEYS: frozenset[str] = frozenset(
    {THEME_LIGHT, THEME_DARK, THEME_HC_LIGHT, THEME_HC_DARK}
)
from app.intelligence.lint_profile import (
    LINT_RULE_DEFINITIONS,
    LINT_SEVERITY_ERROR,
    LINT_SEVERITY_INFO,
    LINT_SEVERITY_WARNING,
)
from app.core import constants
from app.shell.settings_dialog_sections import (
    apply_initial_scope,
    build_buttons_row,
    build_files_tab,
    build_keybindings_tab,
    build_linter_tab,
    build_syntax_tab,
)
from app.shell.style_sheet import build_settings_style_sheet
from app.shell.python_tooling_status_copy import UNKNOWN_SETTINGS_COPY
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette
from app.ui.segmented_control import SegmentedControl


class SettingsDialog(SettingsDialogHandlersMixin, QDialog):
    """Simple settings editor for core editor/intelligence preferences."""

    def __init__(
        self,
        snapshot: EditorSettingsSnapshot,
        parent=None,
        *,
        tokens: ShellThemeTokens | None = None,
        project_snapshot: EditorSettingsSnapshot | None = None,
        project_scope_available: bool = False,
        initial_scope: str = SETTINGS_SCOPE_GLOBAL,
        python_tooling_runtime_text: str = UNKNOWN_SETTINGS_COPY.runtime_text,
        python_tooling_runtime_details: str = UNKNOWN_SETTINGS_COPY.runtime_details,
        python_tooling_config_text: str = UNKNOWN_SETTINGS_COPY.config_text,
        python_tooling_config_details: str = UNKNOWN_SETTINGS_COPY.config_details,
    ) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(860, 640)
        self.setObjectName("shell.settingsDialog")
        if tokens is None:
            tokens = tokens_from_palette(self.palette())
        self._tokens = tokens
        self.setStyleSheet(build_settings_style_sheet(tokens))
        self._project_scope_available = bool(project_scope_available and project_snapshot is not None)
        self._active_scope = SETTINGS_SCOPE_GLOBAL
        self._scope_snapshots: dict[str, EditorSettingsSnapshot] = {
            SETTINGS_SCOPE_GLOBAL: snapshot,
        }
        if self._project_scope_available:
            self._scope_snapshots[SETTINGS_SCOPE_PROJECT] = project_snapshot or snapshot
        self._baseline_highlighting_adaptive_mode = snapshot.highlighting_adaptive_mode
        self._baseline_highlighting_reduced_threshold_chars = snapshot.highlighting_reduced_threshold_chars
        self._baseline_highlighting_lexical_only_threshold_chars = (
            snapshot.highlighting_lexical_only_threshold_chars
        )
        self._shortcut_editors: dict[str, QKeySequenceEdit] = {}
        self._shortcut_rows: dict[str, int] = {}
        self._syntax_color_inputs: dict[str, QLineEdit] = {}
        self._syntax_color_swatches: dict[str, QLabel] = {}
        self._syntax_color_row_by_token: dict[str, int] = {}
        self._syntax_color_overrides_by_theme: dict[str, dict[str, str]] = {
            THEME_LIGHT: dict(snapshot.syntax_color_overrides_light),
            THEME_DARK: dict(snapshot.syntax_color_overrides_dark),
            THEME_HC_LIGHT: dict(snapshot.syntax_color_overrides_high_contrast_light),
            THEME_HC_DARK: dict(snapshot.syntax_color_overrides_high_contrast_dark),
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
        self._scope_input: SegmentedControl | None = None
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
        self._local_history_reset_btn: QPushButton | None = None
        self._linter_provider_scope_hint: QLabel | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        scope_header = QFrame(self)
        scope_header.setObjectName("shell.settingsDialog.scopeHeader")
        scope_header.setFrameShape(QFrame.NoFrame)
        scope_header_layout = QVBoxLayout(scope_header)
        scope_header_layout.setContentsMargins(0, 0, 0, 0)
        scope_header_layout.setSpacing(6)

        scope_row = QHBoxLayout()
        self._scope_input = SegmentedControl(scope_header)
        self._scope_input.setObjectName("shell.settingsDialog.scopeSegmented")
        self._scope_input.add_segment("Global", SETTINGS_SCOPE_GLOBAL)
        self._scope_input.add_segment("Project", SETTINGS_SCOPE_PROJECT)
        if not self._project_scope_available:
            self._scope_input.set_segment_enabled(SETTINGS_SCOPE_PROJECT, False)
            self._scope_input.set_segment_tooltip(
                SETTINGS_SCOPE_PROJECT,
                "Open a project to edit project scope settings.",
            )
        self._scope_input.selection_changed.connect(self._handle_scope_changed)
        scope_row.addWidget(self._scope_input)
        scope_row.addStretch(1)
        scope_header_layout.addLayout(scope_row)

        self._scope_banner_label = QLabel(scope_header)
        self._scope_banner_label.setObjectName("shell.settingsDialog.scopeBanner")
        self._scope_banner_label.setWordWrap(True)
        scope_header_layout.addWidget(self._scope_banner_label)
        layout.addWidget(scope_header)

        tabs = QTabWidget(self)
        tabs.setObjectName("shell.settingsDialog.tabs")
        self._tabs_widget = tabs
        tab_bar = tabs.tabBar()
        tab_font = QFont()
        tab_font.setPixelSize(12)
        tab_font.setWeight(QFont.DemiBold)
        tab_bar.setFont(tab_font)
        tab_bar.setElideMode(Qt.ElideNone)
        tab_bar.setExpanding(False)
        layout.addWidget(tabs)

        build_general_tab(
            self,
            tabs,
            snapshot,
            python_tooling_runtime_text=python_tooling_runtime_text,
            python_tooling_runtime_details=python_tooling_runtime_details,
            python_tooling_config_text=python_tooling_config_text,
            python_tooling_config_details=python_tooling_config_details,
        )
        build_keybindings_tab(self, tabs, snapshot)
        build_syntax_tab(self, tabs)
        build_linter_tab(self, tabs, snapshot, project_snapshot)
        build_files_tab(self, tabs, snapshot)
        build_buttons_row(self, layout)
        apply_initial_scope(self, initial_scope)

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

    def _finalize_keybindings_columns(self) -> None:
        finalize_keybindings_columns(self)

    def _finalize_linter_columns(self) -> None:
        finalize_linter_columns(self)

    def _finalize_syntax_columns(self) -> None:
        finalize_syntax_columns(self)

    def _general_tab_state_from_controls(self) -> GeneralTabState:
        return general_tab_state_from_controls(self)

    def _apply_general_tab_state_to_controls(self, state: GeneralTabState) -> None:
        apply_general_tab_state_to_controls(self, state)

    def _snapshot_from_controls(self) -> EditorSettingsSnapshot:
        """Build settings snapshot from current control values."""
        general = self._general_tab_state_from_controls()
        return EditorSettingsSnapshot(
            **general.to_snapshot_fields(),
            diagnostics_enabled=self._linter_enabled_input.isChecked(),
            selected_linter=str(self._linter_provider_input.currentData()),
            shortcut_overrides=self._shortcut_overrides_snapshot(),
            syntax_color_overrides_light=dict(self._syntax_color_overrides_by_theme.get(THEME_LIGHT, {})),
            syntax_color_overrides_dark=dict(self._syntax_color_overrides_by_theme.get(THEME_DARK, {})),
            syntax_color_overrides_high_contrast_light=dict(
                self._syntax_color_overrides_by_theme.get(THEME_HC_LIGHT, {})
            ),
            syntax_color_overrides_high_contrast_dark=dict(
                self._syntax_color_overrides_by_theme.get(THEME_HC_DARK, {})
            ),
            lint_rule_overrides=self._lint_rule_overrides_snapshot(),
            file_exclude_patterns=self._file_exclude_patterns_snapshot(),
            local_history_max_checkpoints_per_file=int(self._local_history_max_checkpoints_input.value()),
            local_history_retention_days=int(self._local_history_retention_days_input.value()),
            local_history_max_tracked_file_bytes=int(self._local_history_max_tracked_file_kb_input.value()) * 1024,
            local_history_exclude_patterns=self._local_history_exclude_patterns_snapshot(),
        )

    def _capture_active_scope_snapshot(self) -> None:
        self._scope_snapshots[self._active_scope] = self._snapshot_from_controls()

    def _normalized_ui_font_weight_value(self) -> str:
        raw = self._ui_font_weight_input.currentData()
        if isinstance(raw, str) and raw in constants.UI_THEME_FONT_WEIGHT_VALUES:
            return raw
        return constants.UI_THEME_FONT_WEIGHT_DEFAULT

    def _normalized_theme_mode_value(self) -> str:
        raw = self._theme_mode_input.currentData()
        if isinstance(raw, str) and raw in constants.UI_THEME_MODE_VALUES:
            return raw
        return constants.UI_THEME_MODE_DEFAULT

    def _apply_snapshot_to_controls(self, snapshot: EditorSettingsSnapshot) -> None:
        self._apply_general_tab_state_to_controls(GeneralTabState.from_snapshot(snapshot))

        self._linter_enabled_input.setChecked(snapshot.diagnostics_enabled)
        provider_index = self._linter_provider_input.findData(snapshot.selected_linter)
        self._linter_provider_input.setCurrentIndex(provider_index if provider_index >= 0 else 0)
        self._sync_linter_control_states()

        self._apply_shortcut_snapshot(snapshot)
        self._syntax_color_overrides_by_theme = {
            THEME_LIGHT: dict(snapshot.syntax_color_overrides_light),
            THEME_DARK: dict(snapshot.syntax_color_overrides_dark),
            THEME_HC_LIGHT: dict(snapshot.syntax_color_overrides_high_contrast_light),
            THEME_HC_DARK: dict(snapshot.syntax_color_overrides_high_contrast_dark),
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
        self._local_history_max_checkpoints_input.setValue(snapshot.local_history_max_checkpoints_per_file)
        self._local_history_retention_days_input.setValue(snapshot.local_history_retention_days)
        self._local_history_max_tracked_file_kb_input.setValue(
            max(1, int((snapshot.local_history_max_tracked_file_bytes + 1023) / 1024))
        )
        self._local_history_excludes_list.clear()
        for pattern in snapshot.local_history_exclude_patterns:
            self._local_history_excludes_list.addItem(pattern)
        self._refresh_shortcut_conflicts()
        self._refresh_syntax_validation()
        self._refresh_validation_state()


