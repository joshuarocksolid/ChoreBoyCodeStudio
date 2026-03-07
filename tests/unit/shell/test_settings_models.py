"""Unit tests for shell settings snapshot helpers."""

from __future__ import annotations

import pytest

from app.core import constants
from app.shell.settings_models import (
    EditorSettingsSnapshot,
    SETTINGS_SCOPE_GLOBAL,
    SETTINGS_SCOPE_PROJECT,
    has_project_override,
    merge_import_update_policy,
    merge_editor_settings_snapshot_for_scope,
    merge_last_project_path,
    merge_editor_settings_snapshot,
    merge_theme_mode,
    parse_editor_settings_snapshot,
    parse_effective_editor_settings_snapshot,
    parse_main_window_settings,
    remove_project_override,
)

pytestmark = pytest.mark.unit


def test_parse_editor_settings_snapshot_uses_defaults_for_invalid_payload() -> None:
    snapshot = parse_editor_settings_snapshot({"editor": "bad-shape", "intelligence": []})

    assert snapshot.tab_width == 4
    assert snapshot.font_size == 10
    assert snapshot.font_family == "monospace"
    assert snapshot.indent_style == "spaces"
    assert snapshot.detect_indentation_from_file is True
    assert snapshot.format_on_save is False
    assert snapshot.trim_trailing_whitespace_on_save is True
    assert snapshot.insert_final_newline_on_save is True
    assert snapshot.enable_preview is True
    assert snapshot.auto_save is False
    assert snapshot.completion_enabled is True
    assert snapshot.completion_auto_trigger is False
    assert snapshot.diagnostics_enabled is True
    assert snapshot.diagnostics_realtime is True
    assert snapshot.quick_fixes_enabled is True
    assert snapshot.quick_fix_require_preview_for_multifile is True
    assert snapshot.cache_enabled is True
    assert snapshot.highlighting_adaptive_mode == "normal"
    assert snapshot.highlighting_reduced_threshold_chars == 250_000
    assert snapshot.highlighting_lexical_only_threshold_chars == 600_000
    assert snapshot.theme_mode == "system"
    assert snapshot.auto_open_console_on_run_output is True
    assert snapshot.auto_open_problems_on_run_failure is True
    assert snapshot.selected_linter == "default"
    assert snapshot.shortcut_overrides == {}
    assert snapshot.syntax_color_overrides_light == {}
    assert snapshot.syntax_color_overrides_dark == {}
    assert snapshot.lint_rule_overrides == {}


def test_parse_editor_settings_snapshot_reads_explicit_values() -> None:
    snapshot = parse_editor_settings_snapshot(
        {
            "editor": {
                "tab_width": 8,
                "font_size": 14,
                "font_family": "Courier New",
                "indent_style": "tabs",
                "indent_size": 1,
                "detect_indentation_from_file": False,
                "format_on_save": True,
                "trim_trailing_whitespace_on_save": False,
                "insert_final_newline_on_save": False,
                "enable_preview": False,
            },
            "intelligence": {
                "enable_completion": False,
                "auto_trigger_completion": False,
                "completion_min_chars": 3,
                "enable_diagnostics": False,
                "diagnostics_realtime": False,
                "enable_quick_fixes": False,
                "quick_fix_require_preview_for_multifile": False,
                "cache_enabled": False,
                "incremental_indexing": False,
                "metrics_logging_enabled": False,
                "force_full_reindex_on_open": True,
                "highlighting_adaptive_mode": "reduced",
                "highlighting_reduced_threshold_chars": 190000,
                "highlighting_lexical_only_threshold_chars": 480000,
            },
            "output": {
                "auto_open_console_on_run_output": False,
                "auto_open_problems_on_run_failure": False,
            },
            "keybindings": {
                "overrides": {
                    "shell.action.run.run": "Ctrl+R",
                }
            },
            "syntax_colors": {
                "light": {"keyword": "#123456"},
                "dark": {"keyword": "#654321"},
            },
            "linter": {
                "enabled": False,
                "selected_linter": "pyflakes",
                "rule_overrides": {
                    "PY220": {"enabled": False, "severity": "info"},
                }
            },
        }
    )

    assert snapshot.tab_width == 8
    assert snapshot.font_size == 14
    assert snapshot.font_family == "Courier New"
    assert snapshot.indent_style == "tabs"
    assert snapshot.indent_size == 1
    assert snapshot.detect_indentation_from_file is False
    assert snapshot.format_on_save is True
    assert snapshot.trim_trailing_whitespace_on_save is False
    assert snapshot.insert_final_newline_on_save is False
    assert snapshot.enable_preview is False
    assert snapshot.completion_enabled is False
    assert snapshot.completion_auto_trigger is False
    assert snapshot.completion_min_chars == 3
    assert snapshot.diagnostics_enabled is False
    assert snapshot.diagnostics_realtime is False
    assert snapshot.quick_fixes_enabled is False
    assert snapshot.quick_fix_require_preview_for_multifile is False
    assert snapshot.cache_enabled is False
    assert snapshot.incremental_indexing is False
    assert snapshot.metrics_logging_enabled is False
    assert snapshot.force_full_reindex_on_open is True
    assert snapshot.highlighting_adaptive_mode == "reduced"
    assert snapshot.highlighting_reduced_threshold_chars == 190000
    assert snapshot.highlighting_lexical_only_threshold_chars == 480000
    assert snapshot.auto_open_console_on_run_output is False
    assert snapshot.auto_open_problems_on_run_failure is False
    assert snapshot.selected_linter == "pyflakes"
    assert snapshot.shortcut_overrides == {"shell.action.run.run": "Ctrl+R"}
    assert snapshot.syntax_color_overrides_light == {"keyword": "#123456"}
    assert snapshot.syntax_color_overrides_dark == {"keyword": "#654321"}
    assert snapshot.lint_rule_overrides == {"PY220": {"enabled": False, "severity": "info"}}


def test_merge_editor_settings_snapshot_writes_editor_and_intelligence_keys() -> None:
    snapshot = EditorSettingsSnapshot(
        tab_width=6,
        font_size=12,
        font_family="DejaVu Sans Mono",
        indent_style="tabs",
        indent_size=1,
        detect_indentation_from_file=False,
        format_on_save=True,
        trim_trailing_whitespace_on_save=False,
        insert_final_newline_on_save=False,
        enable_preview=False,
        completion_enabled=False,
        completion_auto_trigger=False,
        completion_min_chars=3,
        diagnostics_enabled=False,
        diagnostics_realtime=False,
        quick_fixes_enabled=False,
        quick_fix_require_preview_for_multifile=False,
        cache_enabled=False,
        incremental_indexing=True,
        metrics_logging_enabled=False,
        force_full_reindex_on_open=True,
        highlighting_adaptive_mode="reduced",
        highlighting_reduced_threshold_chars=200000,
        highlighting_lexical_only_threshold_chars=500000,
        auto_open_console_on_run_output=False,
        auto_open_problems_on_run_failure=False,
        selected_linter="pyflakes",
        shortcut_overrides={"shell.action.run.run": "Ctrl+R"},
        syntax_color_overrides_light={"keyword": "#123456"},
        syntax_color_overrides_dark={"keyword": "#654321"},
        lint_rule_overrides={"PY220": {"enabled": False, "severity": "info"}},
    )
    merged = merge_editor_settings_snapshot({"schema_version": 1}, snapshot)

    assert merged["editor"]["tab_width"] == 6
    assert merged["editor"]["font_family"] == "DejaVu Sans Mono"
    assert merged["editor"]["indent_style"] == "tabs"
    assert merged["editor"]["detect_indentation_from_file"] is False
    assert merged["editor"]["format_on_save"] is True
    assert merged["editor"]["trim_trailing_whitespace_on_save"] is False
    assert merged["editor"]["insert_final_newline_on_save"] is False
    assert merged["editor"]["enable_preview"] is False
    assert merged["intelligence"]["enable_completion"] is False
    assert merged["intelligence"]["enable_diagnostics"] is False
    assert merged["intelligence"]["diagnostics_realtime"] is False
    assert merged["intelligence"]["enable_quick_fixes"] is False
    assert merged["intelligence"]["quick_fix_require_preview_for_multifile"] is False
    assert merged["intelligence"]["cache_enabled"] is False
    assert merged["intelligence"]["force_full_reindex_on_open"] is True
    assert merged["intelligence"]["highlighting_adaptive_mode"] == "reduced"
    assert merged["intelligence"]["highlighting_reduced_threshold_chars"] == 200000
    assert merged["intelligence"]["highlighting_lexical_only_threshold_chars"] == 500000
    assert merged["theme"]["mode"] == "system"
    assert merged["output"]["auto_open_console_on_run_output"] is False
    assert merged["output"]["auto_open_problems_on_run_failure"] is False
    assert merged["keybindings"]["overrides"] == {"shell.action.run.run": "Ctrl+R"}
    assert merged["syntax_colors"]["light"] == {"keyword": "#123456"}
    assert merged["syntax_colors"]["dark"] == {"keyword": "#654321"}
    assert merged["linter"]["enabled"] is False
    assert merged["linter"]["selected_linter"] == "pyflakes"
    assert merged["linter"]["rule_overrides"] == {"PY220": {"enabled": False, "severity": "info"}}


def test_parse_editor_settings_snapshot_invalid_selected_linter_defaults_to_default() -> None:
    snapshot = parse_editor_settings_snapshot({"linter": {"selected_linter": "unknown"}})
    assert snapshot.selected_linter == "default"


def test_parse_theme_mode_reads_explicit_dark() -> None:
    snapshot = parse_editor_settings_snapshot({"theme": {"mode": "dark"}})
    assert snapshot.theme_mode == "dark"


def test_parse_theme_mode_reads_explicit_light() -> None:
    snapshot = parse_editor_settings_snapshot({"theme": {"mode": "light"}})
    assert snapshot.theme_mode == "light"


def test_parse_theme_mode_defaults_for_invalid_value() -> None:
    snapshot = parse_editor_settings_snapshot({"theme": {"mode": "neon"}})
    assert snapshot.theme_mode == "system"


def test_parse_theme_mode_defaults_for_missing_key() -> None:
    snapshot = parse_editor_settings_snapshot({})
    assert snapshot.theme_mode == "system"


def test_parse_theme_mode_defaults_for_invalid_theme_section() -> None:
    snapshot = parse_editor_settings_snapshot({"theme": "garbage"})
    assert snapshot.theme_mode == "system"


def test_merge_preserves_theme_mode() -> None:
    snapshot = EditorSettingsSnapshot(theme_mode="dark")
    merged = merge_editor_settings_snapshot({}, snapshot)
    assert merged["theme"]["mode"] == "dark"


def test_merge_theme_mode_round_trip() -> None:
    for mode in ("system", "light", "dark"):
        snapshot = EditorSettingsSnapshot(theme_mode=mode)
        merged = merge_editor_settings_snapshot({}, snapshot)
        restored = parse_editor_settings_snapshot(merged)
        assert restored.theme_mode == mode


def test_merge_invalid_theme_mode_falls_back_to_system() -> None:
    snapshot = EditorSettingsSnapshot(theme_mode="invalid")
    merged = merge_editor_settings_snapshot({}, snapshot)
    assert merged["theme"]["mode"] == "system"


# --- font_family tests ---


def test_parse_font_family_defaults_for_missing_key() -> None:
    snapshot = parse_editor_settings_snapshot({"editor": {}})
    assert snapshot.font_family == "monospace"


def test_parse_font_family_defaults_for_non_string_value() -> None:
    snapshot = parse_editor_settings_snapshot({"editor": {"font_family": 42}})
    assert snapshot.font_family == "monospace"


def test_parse_font_family_defaults_for_blank_string() -> None:
    snapshot = parse_editor_settings_snapshot({"editor": {"font_family": "  "}})
    assert snapshot.font_family == "monospace"


def test_parse_font_family_reads_explicit_value() -> None:
    snapshot = parse_editor_settings_snapshot({"editor": {"font_family": "Fira Code"}})
    assert snapshot.font_family == "Fira Code"


def test_merge_font_family_round_trip() -> None:
    snapshot = EditorSettingsSnapshot(font_family="Source Code Pro")
    merged = merge_editor_settings_snapshot({}, snapshot)
    restored = parse_editor_settings_snapshot(merged)
    assert restored.font_family == "Source Code Pro"


def test_merge_font_family_defaults_for_empty_string() -> None:
    snapshot = EditorSettingsSnapshot(font_family="")
    merged = merge_editor_settings_snapshot({}, snapshot)
    assert merged["editor"]["font_family"] == "monospace"


# --- zoom delta clamping tests ---


@pytest.mark.parametrize(
    "base_size, delta, expected",
    [
        (10, 0, 10),
        (10, 5, 15),
        (10, -2, 8),
        (10, -5, 8),
        (70, 5, 72),
        (8, -1, 8),
        (72, 1, 72),
    ],
)
def test_effective_font_size_clamping(base_size: int, delta: int, expected: int) -> None:
    """Verify the effective size formula: max(8, min(72, base + delta))."""
    effective = max(8, min(72, base_size + delta))
    assert effective == expected


def test_parse_main_window_settings_builds_grouped_preferences() -> None:
    grouped = parse_main_window_settings(
        {
            "editor": {
                "tab_width": 6,
                "font_size": 13,
                "font_family": "Fira Code",
                "indent_style": "tabs",
                "indent_size": 2,
                "detect_indentation_from_file": False,
                "format_on_save": True,
                "trim_trailing_whitespace_on_save": False,
                "insert_final_newline_on_save": False,
                "enable_preview": False,
            },
            "intelligence": {
                "enable_completion": False,
                "auto_trigger_completion": False,
                "completion_min_chars": 4,
                "enable_diagnostics": False,
                "diagnostics_realtime": False,
                "enable_quick_fixes": False,
                "quick_fix_require_preview_for_multifile": False,
                "cache_enabled": False,
                "incremental_indexing": False,
                "metrics_logging_enabled": False,
                "force_full_reindex_on_open": True,
                "highlighting_adaptive_mode": "reduced",
                "highlighting_reduced_threshold_chars": 200000,
                "highlighting_lexical_only_threshold_chars": 400000,
            },
            "output": {
                "auto_open_console_on_run_output": False,
                "auto_open_problems_on_run_failure": False,
            },
        }
    )

    assert grouped.editor_preferences == (6, 13, "Fira Code", "tabs", 2, False, True, False, False, False, False)
    assert grouped.completion_preferences == (False, False, 4)
    assert grouped.diagnostics_preferences == (False, False, False, False)
    assert grouped.output_preferences == (False, False)
    runtime = grouped.intelligence_runtime_settings
    assert runtime.cache_enabled is False
    assert runtime.incremental_indexing is False
    assert runtime.metrics_logging_enabled is False
    assert runtime.force_full_reindex_on_open is True
    assert runtime.highlighting_adaptive_mode == "reduced"
    assert runtime.highlighting_reduced_threshold_chars == 200000
    assert runtime.highlighting_lexical_only_threshold_chars == 400000


def test_merge_theme_mode_normalizes_invalid_values() -> None:
    merged = merge_theme_mode({"theme": {"mode": "dark"}}, "bad-mode")
    assert merged["theme"]["mode"] == "system"


def test_merge_import_update_policy_defaults_blank_value() -> None:
    merged = merge_import_update_policy({}, "   ")
    assert merged["python_import_update_policy"] == "ask"


def test_merge_last_project_path_sets_project_root_key() -> None:
    merged = merge_last_project_path({}, "/tmp/project")
    assert merged["last_project_path"] == "/tmp/project"


def test_parse_effective_editor_settings_snapshot_applies_project_overrides() -> None:
    global_payload = {
        constants.UI_EDITOR_SETTINGS_KEY: {
            constants.UI_EDITOR_TAB_WIDTH_KEY: 4,
            constants.UI_EDITOR_FONT_SIZE_KEY: 12,
        },
        constants.UI_THEME_SETTINGS_KEY: {
            constants.UI_THEME_MODE_KEY: "dark",
        },
    }
    project_payload = {
        constants.UI_EDITOR_SETTINGS_KEY: {
            constants.UI_EDITOR_TAB_WIDTH_KEY: 2,
        },
        constants.UI_THEME_SETTINGS_KEY: {
            constants.UI_THEME_MODE_KEY: "light",
        },
    }

    snapshot = parse_effective_editor_settings_snapshot(global_payload, project_payload)

    assert snapshot.tab_width == 2
    assert snapshot.font_size == 12
    assert snapshot.theme_mode == "dark"


def test_merge_editor_settings_snapshot_for_scope_global_updates_global_only() -> None:
    global_payload = {
        constants.UI_EDITOR_SETTINGS_KEY: {
            constants.UI_EDITOR_TAB_WIDTH_KEY: 4,
        },
    }
    project_payload = {
        "schema_version": 1,
        constants.UI_EDITOR_SETTINGS_KEY: {
            constants.UI_EDITOR_TAB_WIDTH_KEY: 2,
        },
    }
    updated_snapshot = EditorSettingsSnapshot(tab_width=6)

    merged_global, merged_project = merge_editor_settings_snapshot_for_scope(
        scope=SETTINGS_SCOPE_GLOBAL,
        global_settings_payload=global_payload,
        project_settings_payload=project_payload,
        snapshot=updated_snapshot,
    )

    assert merged_global[constants.UI_EDITOR_SETTINGS_KEY][constants.UI_EDITOR_TAB_WIDTH_KEY] == 6
    assert merged_project == project_payload


def test_merge_editor_settings_snapshot_for_scope_project_persists_only_diffs() -> None:
    global_payload = {
        constants.UI_EDITOR_SETTINGS_KEY: {
            constants.UI_EDITOR_TAB_WIDTH_KEY: 4,
            constants.UI_EDITOR_FONT_SIZE_KEY: 11,
        },
        constants.UI_OUTPUT_SETTINGS_KEY: {
            constants.UI_OUTPUT_AUTO_OPEN_CONSOLE_ON_RUN_OUTPUT_KEY: True,
        },
        constants.UI_THEME_SETTINGS_KEY: {
            constants.UI_THEME_MODE_KEY: constants.UI_THEME_MODE_DARK,
        },
    }
    project_payload = {"schema_version": 1}
    updated_snapshot = EditorSettingsSnapshot(
        tab_width=2,
        font_size=11,
        auto_open_console_on_run_output=False,
        theme_mode=constants.UI_THEME_MODE_LIGHT,
    )

    merged_global, merged_project = merge_editor_settings_snapshot_for_scope(
        scope=SETTINGS_SCOPE_PROJECT,
        global_settings_payload=global_payload,
        project_settings_payload=project_payload,
        snapshot=updated_snapshot,
    )

    assert merged_global == global_payload
    assert merged_project == {
        "schema_version": 1,
        constants.UI_EDITOR_SETTINGS_KEY: {
            constants.UI_EDITOR_TAB_WIDTH_KEY: 2,
        },
        constants.UI_OUTPUT_SETTINGS_KEY: {
            constants.UI_OUTPUT_AUTO_OPEN_CONSOLE_ON_RUN_OUTPUT_KEY: False,
        },
    }
    assert constants.UI_THEME_SETTINGS_KEY not in merged_project


def test_has_project_override_and_remove_project_override_manage_nested_paths() -> None:
    payload = {
        "schema_version": 1,
        constants.UI_INTELLIGENCE_SETTINGS_KEY: {
            constants.UI_INTELLIGENCE_ENABLE_COMPLETION_KEY: False,
            constants.UI_INTELLIGENCE_COMPLETION_MIN_CHARS_KEY: 3,
        },
    }
    assert has_project_override(
        payload,
        constants.UI_INTELLIGENCE_SETTINGS_KEY,
        constants.UI_INTELLIGENCE_ENABLE_COMPLETION_KEY,
    ) is True

    updated = remove_project_override(
        payload,
        constants.UI_INTELLIGENCE_SETTINGS_KEY,
        constants.UI_INTELLIGENCE_ENABLE_COMPLETION_KEY,
    )

    assert has_project_override(
        updated,
        constants.UI_INTELLIGENCE_SETTINGS_KEY,
        constants.UI_INTELLIGENCE_ENABLE_COMPLETION_KEY,
    ) is False
    assert has_project_override(
        updated,
        constants.UI_INTELLIGENCE_SETTINGS_KEY,
        constants.UI_INTELLIGENCE_COMPLETION_MIN_CHARS_KEY,
    ) is True


# --- auto_save tests ---


def test_parse_auto_save_defaults_to_false() -> None:
    snapshot = parse_editor_settings_snapshot({})
    assert snapshot.auto_save is False


def test_parse_auto_save_reads_explicit_true() -> None:
    snapshot = parse_editor_settings_snapshot({"editor": {"auto_save": True}})
    assert snapshot.auto_save is True


def test_parse_auto_save_ignores_non_bool_value() -> None:
    snapshot = parse_editor_settings_snapshot({"editor": {"auto_save": "yes"}})
    assert snapshot.auto_save is False


def test_merge_auto_save_round_trip() -> None:
    for value in (True, False):
        snapshot = EditorSettingsSnapshot(auto_save=value)
        merged = merge_editor_settings_snapshot({}, snapshot)
        assert merged["editor"]["auto_save"] is value
        restored = parse_editor_settings_snapshot(merged)
        assert restored.auto_save is value


def test_parse_main_window_settings_includes_auto_save_in_editor_preferences() -> None:
    grouped = parse_main_window_settings({"editor": {"auto_save": True}})
    assert grouped.editor_preferences[-1] is True
