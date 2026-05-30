"""Post-settings-OK runtime apply orchestration for the shell."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.shell.settings_models import EditorSettingsSnapshot
from app.shell.shell_preferences import SettingsReader, ShellPreferencesBundle, load_shell_preferences_bundle


@dataclass(frozen=True)
class SettingsApplyBaseline:
    """Runtime values captured before applying an accepted settings dialog."""

    theme_mode: str
    lint_rule_overrides: dict[str, dict[str, object]]
    diagnostics_enabled: bool
    selected_linter: str
    enable_preview: bool
    effective_excludes: list[str]


class SettingsApplyHostPorts(Protocol):
    """Typed host surface for settings runtime apply (not ``window: Any``)."""

    def lint_rule_overrides(self) -> dict[str, dict[str, object]]:
        ...

    def diagnostics_enabled(self) -> bool:
        ...

    def selected_linter(self) -> str:
        ...

    def editor_enable_preview(self) -> bool:
        ...

    def editor_auto_save(self) -> bool:
        ...

    def diagnostics_realtime(self) -> bool:
        ...

    def intelligence_cache_enabled(self) -> bool:
        ...

    def loaded_project_root(self) -> str | None:
        ...

    def loaded_project_name(self) -> str | None:
        ...

    def set_ui_font_weight(self, ui_font_weight: str) -> None:
        ...

    def set_dark_chrome_palette(self, dark_chrome_palette: str) -> None:
        ...

    def apply_theme_mode(self, theme_mode: str) -> None:
        ...

    def apply_preferences_bundle(self, bundle: ShellPreferencesBundle) -> None:
        ...

    def sync_auto_save_menu_state(self) -> None:
        ...

    def stop_auto_save_timer(self) -> None:
        ...

    def stop_realtime_lint_timer(self) -> None:
        ...

    def clear_pending_realtime_lint_path(self) -> None:
        ...

    def cancel_symbol_index_worker_if_running(self) -> None:
        ...

    def start_symbol_indexing(self, project_root: str) -> None:
        ...

    def apply_editor_preferences_to_open_editors(self) -> None:
        ...

    def apply_runtime_intelligence_preferences_to_open_editors(self) -> None:
        ...

    def apply_shortcut_overrides_runtime(self) -> None:
        ...

    def apply_theme_styles(self) -> None:
        ...

    def cancel_pending_project_tree_preview(self) -> None:
        ...

    def promote_existing_preview_tab(self) -> None:
        ...

    def relint_open_python_files(self) -> None:
        ...

    def clear_stored_lint_diagnostics(self) -> None:
        ...

    def render_merged_problems_panel(self) -> None:
        ...

    def load_effective_exclude_patterns(self, project_root: str | None) -> list[str]:
        ...

    def reload_current_project(self) -> None:
        ...

    def refresh_search_sidebar_excludes(self) -> None:
        ...

    def set_project_placeholder(self, project_name: str) -> None:
        ...

    def log_settings_updated(self) -> None:
        ...


class SettingsApplyWorkflow:
    """Owns runtime mutation after the settings dialog is accepted and persisted."""

    def __init__(
        self,
        *,
        settings_service: SettingsReader,
        host: SettingsApplyHostPorts,
    ) -> None:
        self._settings_service = settings_service
        self._host = host

    def apply_after_settings_saved(
        self,
        *,
        updated_snapshot: EditorSettingsSnapshot,
        baseline: SettingsApplyBaseline,
        project_root: str | None,
    ) -> None:
        """Apply preferences bundle, theme, timers, and lint refresh side effects."""

        if updated_snapshot.theme_mode != baseline.theme_mode:
            self._host.apply_theme_mode(updated_snapshot.theme_mode)
        self._host.set_ui_font_weight(updated_snapshot.ui_font_weight)
        self._host.set_dark_chrome_palette(updated_snapshot.dark_chrome_palette)

        preferences_bundle = load_shell_preferences_bundle(
            self._settings_service,
            project_root=project_root,
        )
        self._host.apply_preferences_bundle(preferences_bundle)
        self._host.sync_auto_save_menu_state()

        if not self._host.editor_auto_save():
            self._host.stop_auto_save_timer()
        if not self._host.diagnostics_enabled() or not self._host.diagnostics_realtime():
            self._host.stop_realtime_lint_timer()
            self._host.clear_pending_realtime_lint_path()

        if not self._host.intelligence_cache_enabled():
            self._host.cancel_symbol_index_worker_if_running()
        else:
            loaded_project_root = self._host.loaded_project_root()
            if loaded_project_root is not None:
                self._host.start_symbol_indexing(loaded_project_root)

        self._host.apply_editor_preferences_to_open_editors()
        self._host.apply_runtime_intelligence_preferences_to_open_editors()
        self._host.apply_shortcut_overrides_runtime()
        self._host.apply_theme_styles()

        if baseline.enable_preview and not self._host.editor_enable_preview():
            self._host.cancel_pending_project_tree_preview()
            self._host.promote_existing_preview_tab()

        lint_profile_changed = self._host.lint_rule_overrides() != baseline.lint_rule_overrides
        diagnostics_enabled_changed = self._host.diagnostics_enabled() != baseline.diagnostics_enabled
        selected_linter_changed = self._host.selected_linter() != baseline.selected_linter
        if self._host.diagnostics_enabled() and (
            lint_profile_changed or diagnostics_enabled_changed or selected_linter_changed
        ):
            self._host.relint_open_python_files()

        if not self._host.diagnostics_enabled():
            self._host.clear_stored_lint_diagnostics()
            self._host.render_merged_problems_panel()

        effective_excludes = self._host.load_effective_exclude_patterns(project_root)
        if effective_excludes != baseline.effective_excludes:
            self._host.reload_current_project()
            if self._host.loaded_project_root() is not None:
                self._host.refresh_search_sidebar_excludes()

        loaded_project_name = self._host.loaded_project_name()
        if loaded_project_name is not None:
            self._host.set_project_placeholder(loaded_project_name)

        self._host.log_settings_updated()


def capture_settings_apply_baseline(
    *,
    theme_mode: str,
    lint_rule_overrides: dict[str, dict[str, object]],
    diagnostics_enabled: bool,
    selected_linter: str,
    enable_preview: bool,
    effective_excludes: list[str],
) -> SettingsApplyBaseline:
    """Build a baseline snapshot for settings apply diffing."""

    return SettingsApplyBaseline(
        theme_mode=theme_mode,
        lint_rule_overrides={code: dict(value) for code, value in lint_rule_overrides.items()},
        diagnostics_enabled=diagnostics_enabled,
        selected_linter=selected_linter,
        enable_preview=enable_preview,
        effective_excludes=list(effective_excludes),
    )
