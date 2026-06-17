"""Post-settings-OK runtime apply orchestration for the shell."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Protocol

from app.bootstrap.logging_setup import get_subsystem_logger
from app.shell.settings_models import EditorSettingsSnapshot
from app.shell.shell_preferences import SettingsReader, ShellPreferencesBundle, build_shell_preferences_bundle


@dataclass(frozen=True)
class SettingsApplyBaseline:
    """Runtime values captured before applying an accepted settings dialog."""

    theme_mode: str
    ui_font_weight: str
    dark_chrome_palette: str
    syntax_color_overrides_light: dict[str, str]
    syntax_color_overrides_dark: dict[str, str]
    syntax_color_overrides_high_contrast_light: dict[str, str]
    syntax_color_overrides_high_contrast_dark: dict[str, str]
    tab_width: int
    font_size: int
    font_family: str
    indent_style: str
    indent_size: int
    detect_indentation_from_file: bool
    hover_tooltip_enabled: bool
    auto_reindent_flat_python_paste: bool
    completion_enabled: bool
    completion_auto_trigger: bool
    completion_min_chars: int
    cache_enabled: bool
    highlighting_adaptive_mode: str
    highlighting_reduced_threshold_chars: int
    highlighting_lexical_only_threshold_chars: int
    local_history_max_checkpoints_per_file: int
    local_history_retention_days: int
    local_history_max_tracked_file_bytes: int
    local_history_exclude_patterns: tuple[str, ...]
    shortcut_overrides: dict[str, str]
    lint_rule_overrides: dict[str, dict[str, object]]
    diagnostics_enabled: bool
    selected_linter: str
    enable_preview: bool
    effective_excludes: list[str]


@dataclass(frozen=True)
class SettingsApplyDiff:
    """Flags indicating which expensive apply paths must run."""

    theme_mode_changed: bool
    theme_affecting_changed: bool
    editor_preferences_changed: bool
    intelligence_highlighting_changed: bool
    shortcut_overrides_changed: bool
    retention_policy_changed: bool
    cache_enabled_changed: bool
    cache_newly_enabled: bool


def build_settings_apply_diff(
    baseline: SettingsApplyBaseline,
    updated_snapshot: EditorSettingsSnapshot,
) -> SettingsApplyDiff:
    """Compare pre-dialog baseline to the accepted dialog snapshot."""

    theme_mode_changed = updated_snapshot.theme_mode != baseline.theme_mode
    syntax_changed = (
        dict(updated_snapshot.syntax_color_overrides_light) != baseline.syntax_color_overrides_light
        or dict(updated_snapshot.syntax_color_overrides_dark) != baseline.syntax_color_overrides_dark
        or dict(updated_snapshot.syntax_color_overrides_high_contrast_light)
        != baseline.syntax_color_overrides_high_contrast_light
        or dict(updated_snapshot.syntax_color_overrides_high_contrast_dark)
        != baseline.syntax_color_overrides_high_contrast_dark
    )
    theme_affecting_changed = (
        theme_mode_changed
        or updated_snapshot.ui_font_weight != baseline.ui_font_weight
        or updated_snapshot.dark_chrome_palette != baseline.dark_chrome_palette
        or syntax_changed
    )
    editor_preferences_changed = (
        updated_snapshot.tab_width != baseline.tab_width
        or updated_snapshot.font_size != baseline.font_size
        or updated_snapshot.font_family != baseline.font_family
        or updated_snapshot.indent_style != baseline.indent_style
        or updated_snapshot.indent_size != baseline.indent_size
        or updated_snapshot.detect_indentation_from_file != baseline.detect_indentation_from_file
        or updated_snapshot.hover_tooltip_enabled != baseline.hover_tooltip_enabled
        or updated_snapshot.auto_reindent_flat_python_paste != baseline.auto_reindent_flat_python_paste
        or updated_snapshot.completion_enabled != baseline.completion_enabled
        or updated_snapshot.completion_auto_trigger != baseline.completion_auto_trigger
        or updated_snapshot.completion_min_chars != baseline.completion_min_chars
    )
    intelligence_highlighting_changed = (
        updated_snapshot.highlighting_adaptive_mode != baseline.highlighting_adaptive_mode
        or updated_snapshot.highlighting_reduced_threshold_chars
        != baseline.highlighting_reduced_threshold_chars
        or updated_snapshot.highlighting_lexical_only_threshold_chars
        != baseline.highlighting_lexical_only_threshold_chars
    )
    shortcut_overrides_changed = dict(updated_snapshot.shortcut_overrides) != dict(baseline.shortcut_overrides)
    retention_policy_changed = (
        updated_snapshot.local_history_max_checkpoints_per_file != baseline.local_history_max_checkpoints_per_file
        or updated_snapshot.local_history_retention_days != baseline.local_history_retention_days
        or updated_snapshot.local_history_max_tracked_file_bytes != baseline.local_history_max_tracked_file_bytes
        or tuple(updated_snapshot.local_history_exclude_patterns) != baseline.local_history_exclude_patterns
    )
    cache_enabled_changed = updated_snapshot.cache_enabled != baseline.cache_enabled
    cache_newly_enabled = not baseline.cache_enabled and updated_snapshot.cache_enabled
    return SettingsApplyDiff(
        theme_mode_changed=theme_mode_changed,
        theme_affecting_changed=theme_affecting_changed,
        editor_preferences_changed=editor_preferences_changed,
        intelligence_highlighting_changed=intelligence_highlighting_changed,
        shortcut_overrides_changed=shortcut_overrides_changed,
        retention_policy_changed=retention_policy_changed,
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


def capture_settings_apply_baseline_from_snapshot(
    *,
    effective_snapshot: EditorSettingsSnapshot,
    effective_excludes: list[str],
) -> SettingsApplyBaseline:
    """Build a baseline snapshot for settings apply diffing from effective editor state."""

    return SettingsApplyBaseline(
        theme_mode=effective_snapshot.theme_mode,
        ui_font_weight=effective_snapshot.ui_font_weight,
        dark_chrome_palette=effective_snapshot.dark_chrome_palette,
        syntax_color_overrides_light=dict(effective_snapshot.syntax_color_overrides_light),
        syntax_color_overrides_dark=dict(effective_snapshot.syntax_color_overrides_dark),
        syntax_color_overrides_high_contrast_light=dict(
            effective_snapshot.syntax_color_overrides_high_contrast_light
        ),
        syntax_color_overrides_high_contrast_dark=dict(
            effective_snapshot.syntax_color_overrides_high_contrast_dark
        ),
        tab_width=effective_snapshot.tab_width,
        font_size=effective_snapshot.font_size,
        font_family=effective_snapshot.font_family,
        indent_style=effective_snapshot.indent_style,
        indent_size=effective_snapshot.indent_size,
        detect_indentation_from_file=effective_snapshot.detect_indentation_from_file,
        hover_tooltip_enabled=effective_snapshot.hover_tooltip_enabled,
        auto_reindent_flat_python_paste=effective_snapshot.auto_reindent_flat_python_paste,
        completion_enabled=effective_snapshot.completion_enabled,
        completion_auto_trigger=effective_snapshot.completion_auto_trigger,
        completion_min_chars=effective_snapshot.completion_min_chars,
        cache_enabled=effective_snapshot.cache_enabled,
        highlighting_adaptive_mode=effective_snapshot.highlighting_adaptive_mode,
        highlighting_reduced_threshold_chars=effective_snapshot.highlighting_reduced_threshold_chars,
        highlighting_lexical_only_threshold_chars=effective_snapshot.highlighting_lexical_only_threshold_chars,
        local_history_max_checkpoints_per_file=effective_snapshot.local_history_max_checkpoints_per_file,
        local_history_retention_days=effective_snapshot.local_history_retention_days,
        local_history_max_tracked_file_bytes=effective_snapshot.local_history_max_tracked_file_bytes,
        local_history_exclude_patterns=tuple(effective_snapshot.local_history_exclude_patterns),
        shortcut_overrides=dict(effective_snapshot.shortcut_overrides),
        lint_rule_overrides={
            code: dict(value) for code, value in effective_snapshot.lint_rule_overrides.items()
        },
        diagnostics_enabled=effective_snapshot.diagnostics_enabled,
        selected_linter=effective_snapshot.selected_linter,
        enable_preview=effective_snapshot.enable_preview,
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
