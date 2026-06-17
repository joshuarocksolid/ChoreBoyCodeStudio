"""Unit tests for post-settings-OK runtime apply orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.project.file_excludes import DEFAULT_EXCLUDE_PATTERNS  # noqa: E402
from app.shell.settings_apply_workflow import (  # noqa: E402
    SettingsApplyBaseline,
    SettingsApplyWorkflow,
    build_settings_apply_diff,
    capture_settings_apply_baseline,
    capture_settings_apply_baseline_from_snapshot,
)
from app.shell.settings_models import EditorSettingsSnapshot  # noqa: E402
from app.shell.shell_preferences import ShellPreferencesBundle  # noqa: E402

pytestmark = pytest.mark.unit


@dataclass
class FakeSettingsService:
    global_payload: dict[str, Any] = field(default_factory=dict)
    project_payloads: dict[str, dict[str, Any]] = field(default_factory=dict)

    def load_global(self) -> dict[str, Any]:
        return dict(self.global_payload)

    def load_project(self, project_root: str) -> dict[str, Any]:
        return dict(self.project_payloads.get(project_root, {}))


@dataclass
class RecordingSettingsApplyHost:
    lint_rule_overrides_value: dict[str, dict[str, object]] = field(default_factory=dict)
    diagnostics_enabled_value: bool = True
    selected_linter_value: str = constants.LINTER_PROVIDER_DEFAULT
    editor_enable_preview_value: bool = True
    editor_auto_save_value: bool = True
    diagnostics_realtime_value: bool = True
    intelligence_cache_enabled_value: bool = True
    loaded_project_root_value: str | None = "/tmp/project"
    loaded_project_name_value: str | None = "Demo Project"
    effective_excludes_value: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE_PATTERNS))

    theme_modes: list[str] = field(default_factory=list)
    theme_mode_skip_flags: list[bool] = field(default_factory=list)
    ui_font_weights: list[str] = field(default_factory=list)
    dark_chrome_palettes: list[str] = field(default_factory=list)
    applied_bundles: list[ShellPreferencesBundle] = field(default_factory=list)
    editor_preferences_calls: int = 0
    intelligence_preferences_calls: int = 0
    shortcut_override_calls: int = 0
    theme_styles_calls: int = 0
    relint_calls: int = 0
    cleared_diagnostics: int = 0
    rendered_problems: int = 0
    reload_calls: int = 0
    search_sidebar_refreshes: int = 0
    preview_cancellations: int = 0
    preview_promotions: int = 0
    auto_save_timer_stops: int = 0
    realtime_lint_timer_stops: int = 0
    symbol_index_cancellations: int = 0
    symbol_index_starts: list[str] = field(default_factory=list)
    project_placeholders: list[str] = field(default_factory=list)
    logged_updates: int = 0

    def lint_rule_overrides(self) -> dict[str, dict[str, object]]:
        return self.lint_rule_overrides_value

    def diagnostics_enabled(self) -> bool:
        return self.diagnostics_enabled_value

    def selected_linter(self) -> str:
        return self.selected_linter_value

    def editor_enable_preview(self) -> bool:
        return self.editor_enable_preview_value

    def editor_auto_save(self) -> bool:
        return self.editor_auto_save_value

    def diagnostics_realtime(self) -> bool:
        return self.diagnostics_realtime_value

    def intelligence_cache_enabled(self) -> bool:
        return self.intelligence_cache_enabled_value

    def loaded_project_root(self) -> str | None:
        return self.loaded_project_root_value

    def loaded_project_name(self) -> str | None:
        return self.loaded_project_name_value

    def set_ui_font_weight(self, ui_font_weight: str) -> None:
        self.ui_font_weights.append(ui_font_weight)

    def set_dark_chrome_palette(self, dark_chrome_palette: str) -> None:
        self.dark_chrome_palettes.append(dark_chrome_palette)

    def apply_theme_mode(self, theme_mode: str, *, skip_theme_styles: bool = False) -> None:
        self.theme_modes.append(theme_mode)
        self.theme_mode_skip_flags.append(skip_theme_styles)

    def apply_preferences_bundle(self, bundle: ShellPreferencesBundle) -> None:
        self.applied_bundles.append(bundle)

    def sync_auto_save_menu_state(self) -> None:
        return None

    def stop_auto_save_timer(self) -> None:
        self.auto_save_timer_stops += 1

    def stop_realtime_lint_timer(self) -> None:
        self.realtime_lint_timer_stops += 1

    def clear_pending_realtime_lint_path(self) -> None:
        return None

    def cancel_symbol_index_worker_if_running(self) -> None:
        self.symbol_index_cancellations += 1

    def start_symbol_indexing(self, project_root: str) -> None:
        self.symbol_index_starts.append(project_root)

    def apply_editor_preferences_to_open_editors(self) -> None:
        self.editor_preferences_calls += 1

    def apply_runtime_intelligence_preferences_to_open_editors(self) -> None:
        self.intelligence_preferences_calls += 1

    def apply_shortcut_overrides_runtime(self) -> None:
        self.shortcut_override_calls += 1

    def apply_theme_styles(self) -> None:
        self.theme_styles_calls += 1

    def cancel_pending_project_tree_preview(self) -> None:
        self.preview_cancellations += 1

    def promote_existing_preview_tab(self) -> None:
        self.preview_promotions += 1

    def relint_open_python_files(self) -> None:
        self.relint_calls += 1

    def clear_stored_lint_diagnostics(self) -> None:
        self.cleared_diagnostics += 1

    def render_merged_problems_panel(self) -> None:
        self.rendered_problems += 1

    def load_effective_exclude_patterns(self, project_root: str | None) -> list[str]:
        del project_root
        return list(self.effective_excludes_value)

    def reload_current_project(self) -> None:
        self.reload_calls += 1

    def refresh_search_sidebar_excludes(self) -> None:
        self.search_sidebar_refreshes += 1

    def set_project_placeholder(self, project_name: str) -> None:
        self.project_placeholders.append(project_name)

    def log_settings_updated(self) -> None:
        self.logged_updates += 1


def _updated_snapshot(**overrides: object) -> EditorSettingsSnapshot:
    snapshot = EditorSettingsSnapshot()
    for key, value in overrides.items():
        object.__setattr__(snapshot, key, value)
    return snapshot


def test_apply_after_settings_saved_applies_theme_and_preferences_bundle() -> None:
    host = RecordingSettingsApplyHost()
    settings_service = FakeSettingsService()
    workflow = SettingsApplyWorkflow(settings_service=settings_service, host=host)
    baseline = capture_settings_apply_baseline(
        theme_mode=constants.UI_THEME_MODE_LIGHT,
        lint_rule_overrides={},
        diagnostics_enabled=True,
        selected_linter=constants.LINTER_PROVIDER_DEFAULT,
        enable_preview=True,
        effective_excludes=list(DEFAULT_EXCLUDE_PATTERNS),
    )

    workflow.apply_after_settings_saved(
        updated_snapshot=_updated_snapshot(
            theme_mode=constants.UI_THEME_MODE_DARK,
            ui_font_weight=constants.UI_THEME_FONT_WEIGHT_BOLD,
            dark_chrome_palette=constants.UI_THEME_DARK_CHROME_PALETTE_NEUTRAL_GRAY,
        ),
        baseline=baseline,
        project_root="/tmp/project",
    )

    assert host.theme_modes == [constants.UI_THEME_MODE_DARK]
    assert host.theme_mode_skip_flags == [True]
    assert host.ui_font_weights == [constants.UI_THEME_FONT_WEIGHT_BOLD]
    assert host.dark_chrome_palettes == [constants.UI_THEME_DARK_CHROME_PALETTE_NEUTRAL_GRAY]
    assert host.theme_styles_calls == 1
    assert len(host.applied_bundles) == 1
    assert host.project_placeholders == ["Demo Project"]
    assert host.logged_updates == 1


def test_apply_after_settings_saved_skips_expensive_paths_for_auto_save_toggle() -> None:
    host = RecordingSettingsApplyHost()
    baseline = capture_settings_apply_baseline_from_snapshot(
        effective_snapshot=EditorSettingsSnapshot(auto_save=False),
        effective_excludes=list(DEFAULT_EXCLUDE_PATTERNS),
    )
    workflow = SettingsApplyWorkflow(settings_service=FakeSettingsService(), host=host)

    workflow.apply_after_settings_saved(
        updated_snapshot=_updated_snapshot(auto_save=True),
        baseline=baseline,
        project_root="/tmp/project",
    )

    assert host.theme_styles_calls == 0
    assert host.editor_preferences_calls == 0
    assert host.intelligence_preferences_calls == 0
    assert host.shortcut_override_calls == 0
    assert host.symbol_index_starts == []
    assert len(host.applied_bundles) == 1


def test_apply_after_settings_saved_relints_when_lint_profile_changes() -> None:
    host = RecordingSettingsApplyHost()
    host.lint_rule_overrides_value = {"E501": {"enabled": False}}
    workflow = SettingsApplyWorkflow(settings_service=FakeSettingsService(), host=host)
    baseline = capture_settings_apply_baseline(
        theme_mode=constants.UI_THEME_MODE_LIGHT,
        lint_rule_overrides={},
        diagnostics_enabled=True,
        selected_linter=constants.LINTER_PROVIDER_DEFAULT,
        enable_preview=True,
        effective_excludes=list(DEFAULT_EXCLUDE_PATTERNS),
    )

    workflow.apply_after_settings_saved(
        updated_snapshot=_updated_snapshot(
            lint_rule_overrides={"E501": {"enabled": False}},
        ),
        baseline=baseline,
        project_root=None,
    )

    assert host.relint_calls == 1


def test_apply_after_settings_saved_clears_diagnostics_when_disabled() -> None:
    host = RecordingSettingsApplyHost()
    host.diagnostics_enabled_value = False
    workflow = SettingsApplyWorkflow(settings_service=FakeSettingsService(), host=host)
    baseline = capture_settings_apply_baseline(
        theme_mode=constants.UI_THEME_MODE_LIGHT,
        lint_rule_overrides={},
        diagnostics_enabled=True,
        selected_linter=constants.LINTER_PROVIDER_DEFAULT,
        enable_preview=True,
        effective_excludes=list(DEFAULT_EXCLUDE_PATTERNS),
    )

    workflow.apply_after_settings_saved(
        updated_snapshot=_updated_snapshot(),
        baseline=baseline,
        project_root=None,
    )

    assert host.cleared_diagnostics == 1
    assert host.rendered_problems == 1
    assert host.relint_calls == 0


def test_apply_after_settings_saved_handles_preview_disable_and_excludes() -> None:
    host = RecordingSettingsApplyHost()
    host.editor_enable_preview_value = False
    host.effective_excludes_value = ["*.tmp"]
    workflow = SettingsApplyWorkflow(settings_service=FakeSettingsService(), host=host)
    baseline = capture_settings_apply_baseline(
        theme_mode=constants.UI_THEME_MODE_LIGHT,
        lint_rule_overrides={},
        diagnostics_enabled=True,
        selected_linter=constants.LINTER_PROVIDER_DEFAULT,
        enable_preview=True,
        effective_excludes=list(DEFAULT_EXCLUDE_PATTERNS),
    )

    workflow.apply_after_settings_saved(
        updated_snapshot=_updated_snapshot(),
        baseline=baseline,
        project_root="/tmp/project",
    )

    assert host.preview_cancellations == 1
    assert host.preview_promotions == 1
    assert host.reload_calls == 1
    assert host.search_sidebar_refreshes == 1


def test_apply_after_settings_saved_stops_timers_and_symbol_indexing() -> None:
    host = RecordingSettingsApplyHost()
    host.editor_auto_save_value = False
    host.diagnostics_realtime_value = False
    host.intelligence_cache_enabled_value = False
    workflow = SettingsApplyWorkflow(settings_service=FakeSettingsService(), host=host)
    baseline = capture_settings_apply_baseline(
        theme_mode=constants.UI_THEME_MODE_LIGHT,
        lint_rule_overrides={},
        diagnostics_enabled=True,
        selected_linter=constants.LINTER_PROVIDER_DEFAULT,
        enable_preview=True,
        effective_excludes=list(DEFAULT_EXCLUDE_PATTERNS),
    )

    workflow.apply_after_settings_saved(
        updated_snapshot=_updated_snapshot(),
        baseline=baseline,
        project_root="/tmp/project",
    )

    assert host.auto_save_timer_stops == 1
    assert host.realtime_lint_timer_stops == 1
    assert host.symbol_index_cancellations == 1
    assert host.symbol_index_starts == []


def test_apply_after_settings_saved_starts_symbol_index_only_when_cache_newly_enabled() -> None:
    host = RecordingSettingsApplyHost()
    host.intelligence_cache_enabled_value = True
    workflow = SettingsApplyWorkflow(settings_service=FakeSettingsService(), host=host)
    baseline = capture_settings_apply_baseline_from_snapshot(
        effective_snapshot=EditorSettingsSnapshot(cache_enabled=True),
        effective_excludes=list(DEFAULT_EXCLUDE_PATTERNS),
    )

    workflow.apply_after_settings_saved(
        updated_snapshot=_updated_snapshot(),
        baseline=baseline,
        project_root="/tmp/project",
    )

    assert host.symbol_index_starts == []


def test_apply_after_settings_saved_starts_symbol_index_when_cache_turned_on() -> None:
    host = RecordingSettingsApplyHost()
    host.intelligence_cache_enabled_value = True
    workflow = SettingsApplyWorkflow(settings_service=FakeSettingsService(), host=host)
    baseline = capture_settings_apply_baseline_from_snapshot(
        effective_snapshot=EditorSettingsSnapshot(cache_enabled=False),
        effective_excludes=list(DEFAULT_EXCLUDE_PATTERNS),
    )

    workflow.apply_after_settings_saved(
        updated_snapshot=_updated_snapshot(cache_enabled=True),
        baseline=baseline,
        project_root="/tmp/project",
    )

    assert host.symbol_index_starts == ["/tmp/project"]


def test_build_settings_apply_diff_detects_editor_preference_changes() -> None:
    baseline = capture_settings_apply_baseline_from_snapshot(
        effective_snapshot=EditorSettingsSnapshot(font_size=12),
        effective_excludes=[],
    )
    diff = build_settings_apply_diff(baseline, _updated_snapshot(font_size=14))
    assert diff.editor_preferences_changed is True
    assert diff.theme_affecting_changed is False
