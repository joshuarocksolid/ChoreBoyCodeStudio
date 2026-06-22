"""Post-settings-OK runtime apply orchestration for the shell."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, replace
from typing import Any, Protocol

from app.bootstrap.logging_setup import get_subsystem_logger
from app.shell.settings_models import EditorSettingsSnapshot
from app.shell.shell_preferences import SettingsReader, ShellPreferencesBundle, build_shell_preferences_bundle

_EDITOR_PREFERENCE_FIELDS: tuple[str, ...] = (
    "tab_width",
    "font_size",
    "font_family",
    "indent_style",
    "indent_size",
    "detect_indentation_from_file",
    "hover_tooltip_enabled",
    "auto_reindent_flat_python_paste",
    "completion_enabled",
    "completion_auto_trigger",
    "completion_min_chars",
)

_INTELLIGENCE_HIGHLIGHTING_FIELDS: tuple[str, ...] = (
    "highlighting_adaptive_mode",
    "highlighting_reduced_threshold_chars",
    "highlighting_lexical_only_threshold_chars",
)

_LINT_PROFILE_FIELDS: tuple[str, ...] = (
    "lint_rule_overrides",
    "diagnostics_enabled",
    "selected_linter",
)

_SYNTAX_OVERRIDE_FIELDS: tuple[str, ...] = (
    "syntax_color_overrides_light",
    "syntax_color_overrides_dark",
    "syntax_color_overrides_high_contrast_light",
    "syntax_color_overrides_high_contrast_dark",
)

_THEME_AFFECTING_FIELDS: tuple[str, ...] = (
    "theme_mode",
    "ui_font_weight",
    "dark_chrome_palette",
    *_SYNTAX_OVERRIDE_FIELDS,
)


@dataclass(frozen=True)
class SettingsApplyBaseline:
    """Runtime values captured before applying an accepted settings dialog."""

    snapshot: EditorSettingsSnapshot
    effective_excludes: list[str]


@dataclass(frozen=True)
class SettingsApplyDiff:
    """Flags indicating which expensive apply paths must run."""

    theme_mode_changed: bool
    theme_affecting_changed: bool
    editor_preferences_changed: bool
    intelligence_highlighting_changed: bool
    shortcut_overrides_changed: bool
    lint_profile_changed: bool
    cache_enabled_changed: bool
    cache_newly_enabled: bool


def _snapshot_field_value(snapshot: EditorSettingsSnapshot, field_name: str) -> object:
    return getattr(snapshot, field_name)


def _snapshot_field_changed(
    baseline: EditorSettingsSnapshot,
    updated: EditorSettingsSnapshot,
    field_name: str,
) -> bool:
    baseline_value = _snapshot_field_value(baseline, field_name)
    updated_value = _snapshot_field_value(updated, field_name)
    if isinstance(baseline_value, dict):
        return dict(updated_value) != dict(baseline_value)  # type: ignore[arg-type]
    if isinstance(baseline_value, tuple):
        return tuple(updated_value) != baseline_value  # type: ignore[arg-type]
    return updated_value != baseline_value


def _any_snapshot_field_changed(
    baseline: EditorSettingsSnapshot,
    updated: EditorSettingsSnapshot,
    field_names: tuple[str, ...],
) -> bool:
    return any(_snapshot_field_changed(baseline, updated, field_name) for field_name in field_names)


def build_settings_apply_diff(
    baseline: SettingsApplyBaseline,
    updated_snapshot: EditorSettingsSnapshot,
) -> SettingsApplyDiff:
    """Compare pre-dialog baseline to the accepted dialog snapshot."""

    baseline_snapshot = baseline.snapshot
    theme_mode_changed = _snapshot_field_changed(baseline_snapshot, updated_snapshot, "theme_mode")
    theme_affecting_changed = _any_snapshot_field_changed(
        baseline_snapshot,
        updated_snapshot,
        _THEME_AFFECTING_FIELDS,
    )
    editor_preferences_changed = _any_snapshot_field_changed(
        baseline_snapshot,
        updated_snapshot,
        _EDITOR_PREFERENCE_FIELDS,
    )
    intelligence_highlighting_changed = _any_snapshot_field_changed(
        baseline_snapshot,
        updated_snapshot,
        _INTELLIGENCE_HIGHLIGHTING_FIELDS,
    )
    shortcut_overrides_changed = _snapshot_field_changed(
        baseline_snapshot,
        updated_snapshot,
        "shortcut_overrides",
    )
    lint_profile_changed = _any_snapshot_field_changed(
        baseline_snapshot,
        updated_snapshot,
        _LINT_PROFILE_FIELDS,
    )
    cache_enabled_changed = _snapshot_field_changed(baseline_snapshot, updated_snapshot, "cache_enabled")
    cache_newly_enabled = not baseline_snapshot.cache_enabled and updated_snapshot.cache_enabled
    return SettingsApplyDiff(
        theme_mode_changed=theme_mode_changed,
        theme_affecting_changed=theme_affecting_changed,
        editor_preferences_changed=editor_preferences_changed,
        intelligence_highlighting_changed=intelligence_highlighting_changed,
        shortcut_overrides_changed=shortcut_overrides_changed,
        lint_profile_changed=lint_profile_changed,
        cache_enabled_changed=cache_enabled_changed,
        cache_newly_enabled=cache_newly_enabled,
    )


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

    def apply_theme_mode(self, theme_mode: str, *, skip_theme_styles: bool = False) -> None:
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


class MainWindowSettingsApplyHost:
    """Host ports for ``SettingsApplyWorkflow`` backed by a MainWindow instance."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def lint_rule_overrides(self) -> dict[str, dict[str, object]]:
        return self._window._lint_rule_overrides

    def diagnostics_enabled(self) -> bool:
        return self._window._diagnostics_enabled

    def selected_linter(self) -> str:
        return self._window._selected_linter

    def editor_enable_preview(self) -> bool:
        return self._window._editor_enable_preview

    def editor_auto_save(self) -> bool:
        return self._window._editor_auto_save

    def diagnostics_realtime(self) -> bool:
        return self._window._diagnostics_realtime

    def intelligence_cache_enabled(self) -> bool:
        return self._window._intelligence_runtime_settings.cache_enabled

    def loaded_project_root(self) -> str | None:
        loaded = self._window._loaded_project
        return None if loaded is None else loaded.project_root

    def loaded_project_name(self) -> str | None:
        loaded = self._window._loaded_project
        return None if loaded is None else loaded.metadata.name

    def set_ui_font_weight(self, ui_font_weight: str) -> None:
        self._window._ui_font_weight = ui_font_weight

    def set_dark_chrome_palette(self, dark_chrome_palette: str) -> None:
        from app.shell.settings_models import resolve_dark_chrome_palette

        self._window._dark_chrome_palette = resolve_dark_chrome_palette(dark_chrome_palette)

    def apply_theme_mode(self, theme_mode: str, *, skip_theme_styles: bool = False) -> None:
        self._window._shell_preferences_runtime.handle_set_theme(
            theme_mode,
            skip_theme_styles=skip_theme_styles,
        )

    def apply_preferences_bundle(self, bundle: ShellPreferencesBundle) -> None:
        self._window._shell_preferences_runtime.apply_preferences_bundle(bundle)

    def sync_auto_save_menu_state(self) -> None:
        self._window._sync_auto_save_menu_state()

    def stop_auto_save_timer(self) -> None:
        self._window._auto_save_to_file_timer.stop()

    def stop_realtime_lint_timer(self) -> None:
        self._window._realtime_lint_timer.stop()

    def clear_pending_realtime_lint_path(self) -> None:
        self._window._pending_realtime_lint_file_path = None

    def cancel_symbol_index_worker_if_running(self) -> None:
        self._window._intelligence_cache_workflow.cancel_symbol_indexing()

    def start_symbol_indexing(self, project_root: str) -> None:
        self._window._intelligence_cache_workflow.start_symbol_indexing(
            project_root,
            inventory_snapshot=self._window._project_inventory_orchestrator.snapshot,
        )

    def apply_editor_preferences_to_open_editors(self) -> None:
        self._window._editor_tab_workflow.apply_editor_preferences_to_open_editors()

    def apply_runtime_intelligence_preferences_to_open_editors(self) -> None:
        self._window._editor_tab_workflow.apply_runtime_intelligence_preferences_to_open_editors()

    def apply_shortcut_overrides_runtime(self) -> None:
        self._window._shell_preferences_runtime.apply_shortcut_overrides_runtime()

    def apply_theme_styles(self) -> None:
        self._window._shell_theme_workflow.apply_theme_styles()

    def cancel_pending_project_tree_preview(self) -> None:
        self._window._project_tree_ui_workflow.cancel_pending_project_tree_preview()

    def promote_existing_preview_tab(self) -> None:
        self._window._editor_tab_workflow.promote_existing_preview_tab()

    def relint_open_python_files(self) -> None:
        self._window._diagnostics_orchestrator.relint_open_python_files()

    def clear_stored_lint_diagnostics(self) -> None:
        self._window._stored_lint_diagnostics.clear()

    def render_merged_problems_panel(self) -> None:
        self._window._problems_controller.render_merged_problems_panel()

    def load_effective_exclude_patterns(self, project_root: str | None) -> list[str]:
        return self._window._file_project_commands_workflow.load_effective_exclude_patterns(project_root)

    def reload_current_project(self) -> None:
        self._window._project_tree_ui_workflow.reload_current_project()

    def refresh_search_sidebar_excludes(self) -> None:
        sidebar = self._window._search_sidebar
        loaded = self._window._loaded_project
        if sidebar is None or loaded is None:
            return
        from app.project.file_excludes import EffectiveExcludes

        sidebar.set_exclude_patterns(
            EffectiveExcludes.merge(
                self._window._file_project_commands_workflow.load_effective_exclude_patterns(
                    loaded.project_root
                ),
                loaded.metadata.exclude_patterns,
            ).as_list()
        )

    def set_project_placeholder(self, project_name: str) -> None:
        self._window.set_project_placeholder(project_name)

    def log_settings_updated(self) -> None:
        self._window._logger.info("Settings updated.")


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
        self._logger = get_subsystem_logger("shell.settings_apply")

    def apply_after_settings_saved(
        self,
        *,
        updated_snapshot: EditorSettingsSnapshot,
        baseline: SettingsApplyBaseline,
        project_root: str | None,
        preferences_bundle: ShellPreferencesBundle | None = None,
    ) -> None:
        """Apply preferences bundle, theme, timers, and lint refresh side effects."""

        profile_enabled = os.environ.get("CBCS_PROFILE_SETTINGS_APPLY", "").strip() == "1"
        started_at = time.perf_counter() if profile_enabled else 0.0

        diff = build_settings_apply_diff(baseline, updated_snapshot)

        if diff.theme_mode_changed:
            self._host.apply_theme_mode(updated_snapshot.theme_mode, skip_theme_styles=True)
        if diff.theme_affecting_changed:
            self._host.set_ui_font_weight(updated_snapshot.ui_font_weight)
            self._host.set_dark_chrome_palette(updated_snapshot.dark_chrome_palette)

        resolved_bundle = preferences_bundle
        if resolved_bundle is None:
            resolved_bundle = build_shell_preferences_bundle(
                self._settings_service.load_global(),
                self._settings_service.load_project(project_root) if project_root is not None else None,
            )
        self._host.apply_preferences_bundle(resolved_bundle)
        self._profile_phase(profile_enabled, started_at, "apply_preferences_bundle")

        self._host.sync_auto_save_menu_state()

        if not self._host.editor_auto_save():
            self._host.stop_auto_save_timer()
        if not self._host.diagnostics_enabled() or not self._host.diagnostics_realtime():
            self._host.stop_realtime_lint_timer()
            self._host.clear_pending_realtime_lint_path()

        if not self._host.intelligence_cache_enabled():
            self._host.cancel_symbol_index_worker_if_running()
        elif diff.cache_newly_enabled:
            loaded_project_root = self._host.loaded_project_root()
            if loaded_project_root is not None:
                self._host.start_symbol_indexing(loaded_project_root)

        if diff.editor_preferences_changed:
            self._host.apply_editor_preferences_to_open_editors()
        if diff.intelligence_highlighting_changed:
            self._host.apply_runtime_intelligence_preferences_to_open_editors()
        if diff.shortcut_overrides_changed:
            self._host.apply_shortcut_overrides_runtime()
        if diff.theme_affecting_changed:
            self._host.apply_theme_styles()
        self._profile_phase(profile_enabled, started_at, "runtime_apply")

        if baseline.snapshot.enable_preview and not self._host.editor_enable_preview():
            self._host.cancel_pending_project_tree_preview()
            self._host.promote_existing_preview_tab()

        if self._host.diagnostics_enabled() and diff.lint_profile_changed:
            self._host.relint_open_python_files()

        if not self._host.diagnostics_enabled():
            self._host.clear_stored_lint_diagnostics()
            self._host.render_merged_problems_panel()

        effective_excludes = self._host.load_effective_exclude_patterns(project_root)
        excludes_changed = effective_excludes != baseline.effective_excludes
        if excludes_changed:
            self._host.reload_current_project()
            if self._host.loaded_project_root() is not None:
                self._host.refresh_search_sidebar_excludes()
            if self._host.intelligence_cache_enabled():
                loaded_project_root = self._host.loaded_project_root()
                if loaded_project_root is not None:
                    self._host.start_symbol_indexing(loaded_project_root)

        loaded_project_name = self._host.loaded_project_name()
        if loaded_project_name is not None:
            self._host.set_project_placeholder(loaded_project_name)

        self._host.log_settings_updated()
        self._profile_phase(profile_enabled, started_at, "complete")

    def _profile_phase(self, enabled: bool, started_at: float, phase: str) -> None:
        if not enabled:
            return
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        self._logger.info("Settings apply profile: phase=%s elapsed_ms=%.2f", phase, elapsed_ms)


def _clone_snapshot(snapshot: EditorSettingsSnapshot) -> EditorSettingsSnapshot:
    return replace(
        snapshot,
        syntax_color_overrides_light=dict(snapshot.syntax_color_overrides_light),
        syntax_color_overrides_dark=dict(snapshot.syntax_color_overrides_dark),
        syntax_color_overrides_high_contrast_light=dict(snapshot.syntax_color_overrides_high_contrast_light),
        syntax_color_overrides_high_contrast_dark=dict(snapshot.syntax_color_overrides_high_contrast_dark),
        shortcut_overrides=dict(snapshot.shortcut_overrides),
        lint_rule_overrides={
            code: dict(value) for code, value in snapshot.lint_rule_overrides.items()
        },
        local_history_exclude_patterns=tuple(snapshot.local_history_exclude_patterns),
    )


def capture_settings_apply_baseline_from_snapshot(
    *,
    effective_snapshot: EditorSettingsSnapshot,
    effective_excludes: list[str],
) -> SettingsApplyBaseline:
    """Build a baseline snapshot for settings apply diffing from effective editor state."""

    return SettingsApplyBaseline(
        snapshot=_clone_snapshot(effective_snapshot),
        effective_excludes=list(effective_excludes),
    )


def capture_settings_apply_baseline(
    *,
    theme_mode: str,
    lint_rule_overrides: dict[str, dict[str, object]],
    diagnostics_enabled: bool,
    selected_linter: str,
    enable_preview: bool,
    effective_excludes: list[str],
) -> SettingsApplyBaseline:
    """Build a baseline snapshot for settings apply diffing (legacy test helper)."""

    snapshot = EditorSettingsSnapshot(
        theme_mode=theme_mode,
        lint_rule_overrides={code: dict(value) for code, value in lint_rule_overrides.items()},
        diagnostics_enabled=diagnostics_enabled,
        selected_linter=selected_linter,
        enable_preview=enable_preview,
    )
    return capture_settings_apply_baseline_from_snapshot(
        effective_snapshot=snapshot,
        effective_excludes=effective_excludes,
    )
