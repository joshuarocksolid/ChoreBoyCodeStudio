"""Runtime loading and application of shell preferences, theme, and shortcuts."""

from __future__ import annotations

from typing import Any, Protocol

from PySide2.QtGui import QKeySequence
from PySide2.QtWidgets import QShortcut

from app.core import constants
from app.intelligence.cache_controls import IntelligenceRuntimeSettings
from app.persistence.history_retention import LocalHistoryRetentionPolicy
from app.plugins.security_policy import merge_plugin_safe_mode, plugin_safe_mode_enabled
from app.project.file_operation_models import ImportUpdatePolicy
from app.shell.settings_models import (
    EditorSettingsSnapshot,
    MainWindowSettingsSnapshot,
    merge_import_update_policy,
    merge_theme_mode,
)
from app.shell.shell_preferences import ShellPreferencesBundle, load_shell_preferences_bundle
from app.shell.shortcut_preferences import (
    build_effective_shortcut_map,
    close_tab_shortcut_id,
    keep_preview_open_shortcut_id,
)


class ShellPreferencesRuntimeHost(Protocol):
    def settings_service(self) -> Any:
        ...

    def current_project_root(self) -> str | None:
        ...

    def dialog_parent(self) -> Any:
        ...

    def menu_registry(self) -> Any | None:
        ...

    def shortcut_overrides(self) -> dict[str, str]:
        ...

    def set_shortcut_overrides(self, overrides: dict[str, str]) -> None:
        ...

    def effective_shortcuts(self) -> dict[str, str]:
        ...

    def set_effective_shortcuts(self, shortcuts: dict[str, str]) -> None:
        ...

    def close_tab_shortcut(self) -> QShortcut | None:
        ...

    def set_close_tab_shortcut(self, shortcut: QShortcut | None) -> None:
        ...

    def keep_preview_open_shortcut(self) -> QShortcut | None:
        ...

    def set_keep_preview_open_shortcut(self, shortcut: QShortcut | None) -> None:
        ...

    def close_active_tab(self) -> None:
        ...

    def handle_keep_preview_open_shortcut(self) -> None:
        ...

    def theme_mode(self) -> str:
        ...

    def set_theme_mode(self, mode: str) -> None:
        ...

    def shell_theme_workflow(self) -> Any:
        ...

    def quick_open_dialog(self) -> Any | None:
        ...

    def set_quick_open_dialog(self, dialog: Any | None) -> None:
        ...

    def logger(self) -> Any:
        ...

    def set_import_update_policy(self, policy: ImportUpdatePolicy) -> None:
        ...

    def set_plugin_safe_mode(self, enabled: bool) -> None:
        ...

    def plugin_safe_mode(self) -> bool:
        ...

    def apply_editor_preferences_tuple(self, editor_preferences: tuple[Any, ...]) -> None:
        ...

    def apply_completion_preferences_tuple(self, completion_preferences: tuple[Any, ...]) -> None:
        ...

    def apply_diagnostics_preferences_tuple(self, diagnostics_preferences: tuple[Any, ...]) -> None:
        ...

    def apply_output_preferences_tuple(self, output_preferences: tuple[Any, ...]) -> None:
        ...

    def set_local_history_retention_policy(self, policy: LocalHistoryRetentionPolicy) -> None:
        ...

    def local_history_workflow(self) -> Any:
        ...

    def set_syntax_color_overrides(self, overrides: dict[str, dict[str, str]]) -> None:
        ...

    def set_lint_rule_overrides(self, overrides: dict[str, dict[str, object]]) -> None:
        ...

    def set_selected_linter(self, linter: str) -> None:
        ...

    def set_intelligence_runtime_settings(self, settings: IntelligenceRuntimeSettings) -> None:
        ...


class ShellPreferencesRuntime:
    """Loads and applies persisted shell preferences at runtime."""

    def __init__(self, host: ShellPreferencesRuntimeHost) -> None:
        self._host = host

    def _load_bundle(self) -> ShellPreferencesBundle:
        return load_shell_preferences_bundle(
            self._host.settings_service(),
            project_root=self._host.current_project_root(),
        )

    def load_import_update_policy(self) -> ImportUpdatePolicy:
        settings_payload = self._host.settings_service().load_global()
        raw_value = settings_payload.get(
            constants.UI_IMPORT_UPDATE_POLICY_KEY,
            constants.UI_IMPORT_UPDATE_POLICY_DEFAULT,
        )
        try:
            return ImportUpdatePolicy(str(raw_value))
        except ValueError:
            return ImportUpdatePolicy.ASK

    def load_shortcut_overrides(self) -> dict[str, str]:
        return dict(self._load_bundle().shortcut_overrides)

    def load_lint_rule_overrides(self) -> dict[str, dict[str, object]]:
        return dict(self._load_bundle().lint_rule_overrides)

    def load_selected_linter(self) -> str:
        return self._load_bundle().selected_linter

    def configure_close_tab_shortcut(self) -> None:
        parent = self._host.dialog_parent()
        close_tab_shortcut = self._host.close_tab_shortcut()
        if close_tab_shortcut is None:
            close_tab_shortcut = QShortcut(QKeySequence(), parent)
            close_tab_shortcut.activated.connect(self._host.close_active_tab)
            self._host.set_close_tab_shortcut(close_tab_shortcut)
        close_tab_sequence = self._host.effective_shortcuts().get(close_tab_shortcut_id(), "")
        close_tab_shortcut.setKey(QKeySequence(close_tab_sequence))

    def configure_keep_preview_open_shortcut(self) -> None:
        parent = self._host.dialog_parent()
        keep_preview_shortcut = self._host.keep_preview_open_shortcut()
        if keep_preview_shortcut is None:
            keep_preview_shortcut = QShortcut(QKeySequence(), parent)
            keep_preview_shortcut.activated.connect(self._host.handle_keep_preview_open_shortcut)
            self._host.set_keep_preview_open_shortcut(keep_preview_shortcut)
        keep_open_sequence = self._host.effective_shortcuts().get(keep_preview_open_shortcut_id(), "")
        keep_preview_shortcut.setKey(QKeySequence(keep_open_sequence))

    def apply_shortcut_overrides_runtime(self) -> None:
        self._host.set_effective_shortcuts(build_effective_shortcut_map(self._host.shortcut_overrides()))
        menu_registry = self._host.menu_registry()
        if menu_registry is not None:
            for action_id, action in menu_registry.actions.items():
                if action is None:
                    continue
                action.setShortcut(QKeySequence(self._host.effective_shortcuts().get(action_id, "")))
        self.configure_close_tab_shortcut()
        self.configure_keep_preview_open_shortcut()

    def persist_theme_mode(self, mode: str) -> None:
        self._host.settings_service().update_global(
            lambda settings_payload: merge_theme_mode(settings_payload, mode)
        )

    def handle_set_theme(self, mode: str) -> None:
        if mode == self._host.theme_mode():
            return
        self._host.set_theme_mode(mode)
        self._host.shell_theme_workflow().invalidate_system_dark_theme_preference()
        self.persist_theme_mode(mode)
        quick_open_dialog = self._host.quick_open_dialog()
        if quick_open_dialog is not None:
            quick_open_dialog.deleteLater()
            self._host.set_quick_open_dialog(None)
        self._host.shell_theme_workflow().apply_theme_styles()
        self.sync_theme_menu_check_state()
        self._host.logger().info("Theme mode changed to %s.", mode)

    def sync_theme_menu_check_state(self) -> None:
        menu_registry = self._host.menu_registry()
        if menu_registry is None:
            return
        mode_to_action_id = {
            constants.UI_THEME_MODE_SYSTEM: "shell.action.view.theme.system",
            constants.UI_THEME_MODE_LIGHT: "shell.action.view.theme.light",
            constants.UI_THEME_MODE_DARK: "shell.action.view.theme.dark",
            constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT: "shell.action.view.theme.high_contrast_light",
            constants.UI_THEME_MODE_HIGH_CONTRAST_DARK: "shell.action.view.theme.high_contrast_dark",
        }
        active_id = mode_to_action_id.get(
            self._host.theme_mode(),
            mode_to_action_id[constants.UI_THEME_MODE_SYSTEM],
        )
        for action_id in mode_to_action_id.values():
            action = menu_registry.action(action_id)
            if action is not None:
                action.setChecked(action_id == active_id)

    def load_effective_editor_settings_snapshot(self) -> EditorSettingsSnapshot:
        return self._load_bundle().effective_editor

    def load_main_window_settings(self) -> MainWindowSettingsSnapshot:
        return self._load_bundle().main_window

    def load_editor_preferences(self) -> tuple[Any, ...]:
        return self.load_main_window_settings().editor_preferences

    def load_completion_preferences(self) -> tuple[Any, ...]:
        return self.load_main_window_settings().completion_preferences

    def load_diagnostics_preferences(self) -> tuple[Any, ...]:
        return self.load_main_window_settings().diagnostics_preferences

    def load_output_preferences(self) -> tuple[Any, ...]:
        return self.load_main_window_settings().output_preferences

    def load_local_history_retention_policy(self) -> LocalHistoryRetentionPolicy:
        return self.load_main_window_settings().local_history_retention_policy

    def load_intelligence_runtime_settings(self) -> IntelligenceRuntimeSettings:
        return self.load_main_window_settings().intelligence_runtime_settings

    def apply_preferences_bundle(self, bundle: ShellPreferencesBundle) -> None:
        main = bundle.main_window
        self._host.apply_editor_preferences_tuple(main.editor_preferences)
        self._host.apply_completion_preferences_tuple(main.completion_preferences)
        self._host.apply_diagnostics_preferences_tuple(main.diagnostics_preferences)
        self._host.apply_output_preferences_tuple(main.output_preferences)
        self._host.set_local_history_retention_policy(bundle.local_history_retention_policy)
        self._host.local_history_workflow().set_retention_policy(
            bundle.local_history_retention_policy,
            apply_now=True,
        )
        self._host.set_shortcut_overrides(dict(bundle.shortcut_overrides))
        self._host.set_syntax_color_overrides(
            {theme: dict(overrides) for theme, overrides in bundle.syntax_color_overrides.items()}
        )
        self._host.set_lint_rule_overrides(bundle.lint_rule_overrides)
        self._host.set_selected_linter(bundle.selected_linter)
        self._host.set_intelligence_runtime_settings(bundle.intelligence_runtime_settings)

    def load_plugin_safe_mode(self) -> bool:
        settings_payload = self._host.settings_service().load_global()
        return plugin_safe_mode_enabled(settings_payload)

    def set_plugin_safe_mode(self, enabled: bool) -> None:
        self._host.settings_service().update_global(
            lambda payload: merge_plugin_safe_mode(payload, enabled=enabled)
        )
        self._host.set_plugin_safe_mode(enabled)

    def save_import_update_policy(self, policy: ImportUpdatePolicy) -> None:
        self._host.settings_service().update_global(
            lambda settings_payload: merge_import_update_policy(settings_payload, policy.value)
        )
        self._host.set_import_update_policy(policy)


class MainWindowShellPreferencesRuntimeHost:
    """Host ports for ``ShellPreferencesRuntime`` backed by a MainWindow instance."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def settings_service(self) -> Any:
        return self._window._settings_service

    def current_project_root(self) -> str | None:
        if self._window._loaded_project is None:
            return None
        return self._window._loaded_project.project_root

    def dialog_parent(self) -> Any:
        return self._window

    def menu_registry(self) -> Any | None:
        return self._window._menu_registry

    def shortcut_overrides(self) -> dict[str, str]:
        return self._window._shortcut_overrides

    def set_shortcut_overrides(self, overrides: dict[str, str]) -> None:
        self._window._shortcut_overrides = overrides

    def effective_shortcuts(self) -> dict[str, str]:
        return self._window._effective_shortcuts

    def set_effective_shortcuts(self, shortcuts: dict[str, str]) -> None:
        self._window._effective_shortcuts = shortcuts

    def close_tab_shortcut(self) -> QShortcut | None:
        return self._window._close_tab_shortcut

    def set_close_tab_shortcut(self, shortcut: QShortcut | None) -> None:
        self._window._close_tab_shortcut = shortcut

    def keep_preview_open_shortcut(self) -> QShortcut | None:
        return self._window._keep_preview_open_shortcut

    def set_keep_preview_open_shortcut(self, shortcut: QShortcut | None) -> None:
        self._window._keep_preview_open_shortcut = shortcut

    def close_active_tab(self) -> None:
        self._window._close_active_tab()

    def handle_keep_preview_open_shortcut(self) -> None:
        self._window._handle_keep_preview_open_shortcut()

    def theme_mode(self) -> str:
        return self._window._theme_mode

    def set_theme_mode(self, mode: str) -> None:
        self._window._theme_mode = mode

    def shell_theme_workflow(self) -> Any:
        return self._window._shell_theme_workflow

    def quick_open_dialog(self) -> Any | None:
        return self._window._quick_open_dialog

    def set_quick_open_dialog(self, dialog: Any | None) -> None:
        self._window._quick_open_dialog = dialog

    def logger(self) -> Any:
        return self._window._logger

    def set_import_update_policy(self, policy: ImportUpdatePolicy) -> None:
        self._window._import_update_policy = policy

    def set_plugin_safe_mode(self, enabled: bool) -> None:
        self._window._plugin_safe_mode = bool(enabled)

    def plugin_safe_mode(self) -> bool:
        return self._window._plugin_safe_mode

    def apply_editor_preferences_tuple(self, editor_preferences: tuple[Any, ...]) -> None:
        (
            self._window._editor_tab_width,
            self._window._editor_font_size,
            self._window._editor_font_family,
            self._window._editor_indent_style,
            self._window._editor_indent_size,
            self._window._editor_detect_indentation_from_file,
            self._window._editor_format_on_save,
            self._window._editor_organize_imports_on_save,
            self._window._editor_trim_trailing_whitespace_on_save,
            self._window._editor_insert_final_newline_on_save,
            self._window._editor_enable_preview,
            self._window._editor_auto_save,
            self._window._editor_exit_behavior,
            self._window._editor_hover_tooltip_enabled,
            self._window._editor_auto_reindent_flat_python_paste,
        ) = editor_preferences

    def apply_completion_preferences_tuple(self, completion_preferences: tuple[Any, ...]) -> None:
        (
            self._window._completion_enabled,
            self._window._completion_auto_trigger,
            self._window._completion_min_chars,
        ) = completion_preferences

    def apply_diagnostics_preferences_tuple(self, diagnostics_preferences: tuple[Any, ...]) -> None:
        (
            self._window._diagnostics_enabled,
            self._window._diagnostics_realtime,
            self._window._quick_fixes_enabled,
            self._window._quick_fix_require_preview_for_multifile,
        ) = diagnostics_preferences

    def apply_output_preferences_tuple(self, output_preferences: tuple[Any, ...]) -> None:
        (
            self._window._auto_open_console_on_run_output,
            self._window._auto_open_problems_on_run_failure,
        ) = output_preferences

    def set_local_history_retention_policy(self, policy: LocalHistoryRetentionPolicy) -> None:
        self._window._local_history_retention_policy = policy

    def local_history_workflow(self) -> Any:
        return self._window._local_history_workflow

    def set_syntax_color_overrides(self, overrides: dict[str, dict[str, str]]) -> None:
        self._window._syntax_color_overrides = overrides

    def set_lint_rule_overrides(self, overrides: dict[str, dict[str, object]]) -> None:
        self._window._lint_rule_overrides = overrides

    def set_selected_linter(self, linter: str) -> None:
        self._window._selected_linter = linter

    def set_intelligence_runtime_settings(self, settings: IntelligenceRuntimeSettings) -> None:
        self._window._intelligence_runtime_settings = settings


def build_shell_preferences_runtime(window: Any) -> ShellPreferencesRuntime:
    return ShellPreferencesRuntime(MainWindowShellPreferencesRuntimeHost(window))
