"""Pure settings parsing/serialization helpers for shell settings UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.core import constants
from app.intelligence.cache_controls import IntelligenceRuntimeSettings, parse_intelligence_runtime_settings
from app.intelligence.lint_profile import parse_lint_rule_overrides
from app.project.file_excludes import DEFAULT_EXCLUDE_PATTERNS, parse_global_exclude_patterns
from app.shell.shortcut_preferences import parse_shortcut_overrides
from app.shell.syntax_color_preferences import (
    THEME_DARK,
    THEME_LIGHT,
    parse_syntax_color_overrides,
)


@dataclass(frozen=True)
class EditorSettingsSnapshot:
    """Editable settings snapshot shown in settings dialog."""

    tab_width: int = constants.UI_EDITOR_TAB_WIDTH_DEFAULT
    font_size: int = constants.UI_EDITOR_FONT_SIZE_DEFAULT
    font_family: str = constants.UI_EDITOR_FONT_FAMILY_DEFAULT
    indent_style: str = constants.UI_EDITOR_INDENT_STYLE_DEFAULT
    indent_size: int = constants.UI_EDITOR_INDENT_SIZE_DEFAULT
    detect_indentation_from_file: bool = constants.UI_EDITOR_DETECT_INDENTATION_FROM_FILE_DEFAULT
    format_on_save: bool = constants.UI_EDITOR_FORMAT_ON_SAVE_DEFAULT
    trim_trailing_whitespace_on_save: bool = constants.UI_EDITOR_TRIM_TRAILING_WHITESPACE_ON_SAVE_DEFAULT
    insert_final_newline_on_save: bool = constants.UI_EDITOR_INSERT_FINAL_NEWLINE_ON_SAVE_DEFAULT
    completion_enabled: bool = constants.UI_INTELLIGENCE_ENABLE_COMPLETION_DEFAULT
    completion_auto_trigger: bool = constants.UI_INTELLIGENCE_AUTO_TRIGGER_COMPLETION_DEFAULT
    completion_min_chars: int = constants.UI_INTELLIGENCE_COMPLETION_MIN_CHARS_DEFAULT
    diagnostics_enabled: bool = constants.UI_INTELLIGENCE_ENABLE_DIAGNOSTICS_DEFAULT
    diagnostics_realtime: bool = constants.UI_INTELLIGENCE_DIAGNOSTICS_REALTIME_DEFAULT
    quick_fixes_enabled: bool = constants.UI_INTELLIGENCE_ENABLE_QUICK_FIXES_DEFAULT
    quick_fix_require_preview_for_multifile: bool = (
        constants.UI_INTELLIGENCE_QUICK_FIX_REQUIRE_PREVIEW_FOR_MULTIFILE_DEFAULT
    )
    cache_enabled: bool = constants.UI_INTELLIGENCE_CACHE_ENABLED_DEFAULT
    incremental_indexing: bool = constants.UI_INTELLIGENCE_INCREMENTAL_INDEXING_DEFAULT
    metrics_logging_enabled: bool = constants.UI_INTELLIGENCE_METRICS_LOGGING_ENABLED_DEFAULT
    force_full_reindex_on_open: bool = constants.UI_INTELLIGENCE_FORCE_FULL_REINDEX_ON_OPEN_DEFAULT
    highlighting_adaptive_mode: str = constants.UI_INTELLIGENCE_HIGHLIGHTING_ADAPTIVE_MODE_DEFAULT
    highlighting_reduced_threshold_chars: int = constants.UI_INTELLIGENCE_HIGHLIGHTING_REDUCED_THRESHOLD_CHARS_DEFAULT
    highlighting_lexical_only_threshold_chars: int = (
        constants.UI_INTELLIGENCE_HIGHLIGHTING_LEXICAL_ONLY_THRESHOLD_CHARS_DEFAULT
    )
    theme_mode: str = constants.UI_THEME_MODE_DEFAULT
    auto_open_console_on_run_output: bool = constants.UI_OUTPUT_AUTO_OPEN_CONSOLE_ON_RUN_OUTPUT_DEFAULT
    auto_open_problems_on_run_failure: bool = constants.UI_OUTPUT_AUTO_OPEN_PROBLEMS_ON_RUN_FAILURE_DEFAULT
    shortcut_overrides: dict[str, str] = field(default_factory=dict)
    syntax_color_overrides_light: dict[str, str] = field(default_factory=dict)
    syntax_color_overrides_dark: dict[str, str] = field(default_factory=dict)
    lint_rule_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    file_exclude_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE_PATTERNS))


@dataclass(frozen=True)
class MainWindowSettingsSnapshot:
    """Facade snapshot for MainWindow runtime preference loading."""

    editor_preferences: tuple[int, int, str, str, int, bool, bool, bool, bool]
    completion_preferences: tuple[bool, bool, int]
    diagnostics_preferences: tuple[bool, bool, bool, bool]
    output_preferences: tuple[bool, bool]
    intelligence_runtime_settings: IntelligenceRuntimeSettings


def parse_editor_settings_snapshot(settings_payload: Mapping[str, Any]) -> EditorSettingsSnapshot:
    """Parse persisted settings payload into editable snapshot."""
    editor_settings = settings_payload.get(constants.UI_EDITOR_SETTINGS_KEY, {})
    if not isinstance(editor_settings, dict):
        editor_settings = {}
    intelligence_settings = settings_payload.get(constants.UI_INTELLIGENCE_SETTINGS_KEY, {})
    if not isinstance(intelligence_settings, dict):
        intelligence_settings = {}
    runtime_settings = parse_intelligence_runtime_settings(settings_payload)
    shortcut_overrides = parse_shortcut_overrides(settings_payload)
    syntax_color_overrides = parse_syntax_color_overrides(settings_payload)
    lint_rule_overrides = parse_lint_rule_overrides(settings_payload)
    file_exclude_patterns = parse_global_exclude_patterns(settings_payload)
    theme_settings = settings_payload.get(constants.UI_THEME_SETTINGS_KEY, {})
    if not isinstance(theme_settings, dict):
        theme_settings = {}
    output_settings = settings_payload.get(constants.UI_OUTPUT_SETTINGS_KEY, {})
    if not isinstance(output_settings, dict):
        output_settings = {}
    theme_mode_raw = theme_settings.get(constants.UI_THEME_MODE_KEY, constants.UI_THEME_MODE_DEFAULT)
    _valid_modes = {constants.UI_THEME_MODE_SYSTEM, constants.UI_THEME_MODE_LIGHT, constants.UI_THEME_MODE_DARK}
    theme_mode = str(theme_mode_raw) if str(theme_mode_raw) in _valid_modes else constants.UI_THEME_MODE_DEFAULT

    tab_width = _coerce_int(
        editor_settings.get(constants.UI_EDITOR_TAB_WIDTH_KEY),
        default=constants.UI_EDITOR_TAB_WIDTH_DEFAULT,
        minimum=2,
    )
    font_size = _coerce_int(
        editor_settings.get(constants.UI_EDITOR_FONT_SIZE_KEY),
        default=constants.UI_EDITOR_FONT_SIZE_DEFAULT,
        minimum=8,
    )
    font_family_raw = editor_settings.get(
        constants.UI_EDITOR_FONT_FAMILY_KEY, constants.UI_EDITOR_FONT_FAMILY_DEFAULT
    )
    font_family = str(font_family_raw).strip() if isinstance(font_family_raw, str) and font_family_raw.strip() else constants.UI_EDITOR_FONT_FAMILY_DEFAULT
    indent_style_raw = editor_settings.get(constants.UI_EDITOR_INDENT_STYLE_KEY, constants.UI_EDITOR_INDENT_STYLE_DEFAULT)
    indent_style = "tabs" if indent_style_raw == "tabs" else "spaces"
    indent_size = _coerce_int(
        editor_settings.get(constants.UI_EDITOR_INDENT_SIZE_KEY),
        default=constants.UI_EDITOR_INDENT_SIZE_DEFAULT,
        minimum=1,
    )
    detect_indentation_from_file = _coerce_bool(
        editor_settings.get(constants.UI_EDITOR_DETECT_INDENTATION_FROM_FILE_KEY),
        default=constants.UI_EDITOR_DETECT_INDENTATION_FROM_FILE_DEFAULT,
    )
    format_on_save = _coerce_bool(
        editor_settings.get(constants.UI_EDITOR_FORMAT_ON_SAVE_KEY),
        default=constants.UI_EDITOR_FORMAT_ON_SAVE_DEFAULT,
    )
    trim_trailing_whitespace_on_save = _coerce_bool(
        editor_settings.get(constants.UI_EDITOR_TRIM_TRAILING_WHITESPACE_ON_SAVE_KEY),
        default=constants.UI_EDITOR_TRIM_TRAILING_WHITESPACE_ON_SAVE_DEFAULT,
    )
    insert_final_newline_on_save = _coerce_bool(
        editor_settings.get(constants.UI_EDITOR_INSERT_FINAL_NEWLINE_ON_SAVE_KEY),
        default=constants.UI_EDITOR_INSERT_FINAL_NEWLINE_ON_SAVE_DEFAULT,
    )

    return EditorSettingsSnapshot(
        tab_width=tab_width,
        font_size=font_size,
        font_family=font_family,
        indent_style=indent_style,
        indent_size=indent_size,
        detect_indentation_from_file=detect_indentation_from_file,
        format_on_save=format_on_save,
        trim_trailing_whitespace_on_save=trim_trailing_whitespace_on_save,
        insert_final_newline_on_save=insert_final_newline_on_save,
        completion_enabled=_coerce_bool(
            intelligence_settings.get(constants.UI_INTELLIGENCE_ENABLE_COMPLETION_KEY),
            default=constants.UI_INTELLIGENCE_ENABLE_COMPLETION_DEFAULT,
        ),
        completion_auto_trigger=_coerce_bool(
            intelligence_settings.get(constants.UI_INTELLIGENCE_AUTO_TRIGGER_COMPLETION_KEY),
            default=constants.UI_INTELLIGENCE_AUTO_TRIGGER_COMPLETION_DEFAULT,
        ),
        completion_min_chars=_coerce_int(
            intelligence_settings.get(constants.UI_INTELLIGENCE_COMPLETION_MIN_CHARS_KEY),
            default=constants.UI_INTELLIGENCE_COMPLETION_MIN_CHARS_DEFAULT,
            minimum=1,
        ),
        diagnostics_enabled=_coerce_bool(
            intelligence_settings.get(constants.UI_INTELLIGENCE_ENABLE_DIAGNOSTICS_KEY),
            default=constants.UI_INTELLIGENCE_ENABLE_DIAGNOSTICS_DEFAULT,
        ),
        diagnostics_realtime=_coerce_bool(
            intelligence_settings.get(constants.UI_INTELLIGENCE_DIAGNOSTICS_REALTIME_KEY),
            default=constants.UI_INTELLIGENCE_DIAGNOSTICS_REALTIME_DEFAULT,
        ),
        quick_fixes_enabled=_coerce_bool(
            intelligence_settings.get(constants.UI_INTELLIGENCE_ENABLE_QUICK_FIXES_KEY),
            default=constants.UI_INTELLIGENCE_ENABLE_QUICK_FIXES_DEFAULT,
        ),
        quick_fix_require_preview_for_multifile=_coerce_bool(
            intelligence_settings.get(constants.UI_INTELLIGENCE_QUICK_FIX_REQUIRE_PREVIEW_FOR_MULTIFILE_KEY),
            default=constants.UI_INTELLIGENCE_QUICK_FIX_REQUIRE_PREVIEW_FOR_MULTIFILE_DEFAULT,
        ),
        cache_enabled=runtime_settings.cache_enabled,
        incremental_indexing=runtime_settings.incremental_indexing,
        metrics_logging_enabled=runtime_settings.metrics_logging_enabled,
        force_full_reindex_on_open=runtime_settings.force_full_reindex_on_open,
        highlighting_adaptive_mode=runtime_settings.highlighting_adaptive_mode,
        highlighting_reduced_threshold_chars=runtime_settings.highlighting_reduced_threshold_chars,
        highlighting_lexical_only_threshold_chars=runtime_settings.highlighting_lexical_only_threshold_chars,
        theme_mode=theme_mode,
        auto_open_console_on_run_output=_coerce_bool(
            output_settings.get(constants.UI_OUTPUT_AUTO_OPEN_CONSOLE_ON_RUN_OUTPUT_KEY),
            default=constants.UI_OUTPUT_AUTO_OPEN_CONSOLE_ON_RUN_OUTPUT_DEFAULT,
        ),
        auto_open_problems_on_run_failure=_coerce_bool(
            output_settings.get(constants.UI_OUTPUT_AUTO_OPEN_PROBLEMS_ON_RUN_FAILURE_KEY),
            default=constants.UI_OUTPUT_AUTO_OPEN_PROBLEMS_ON_RUN_FAILURE_DEFAULT,
        ),
        shortcut_overrides=shortcut_overrides,
        syntax_color_overrides_light=syntax_color_overrides.get(THEME_LIGHT, {}),
        syntax_color_overrides_dark=syntax_color_overrides.get(THEME_DARK, {}),
        lint_rule_overrides=lint_rule_overrides,
        file_exclude_patterns=file_exclude_patterns,
    )


def parse_main_window_settings(settings_payload: Mapping[str, Any]) -> MainWindowSettingsSnapshot:
    """Parse persisted settings into MainWindow-focused preference groups."""
    snapshot = parse_editor_settings_snapshot(settings_payload)
    return MainWindowSettingsSnapshot(
        editor_preferences=(
            snapshot.tab_width,
            snapshot.font_size,
            snapshot.font_family,
            snapshot.indent_style,
            snapshot.indent_size,
            snapshot.detect_indentation_from_file,
            snapshot.format_on_save,
            snapshot.trim_trailing_whitespace_on_save,
            snapshot.insert_final_newline_on_save,
        ),
        completion_preferences=(
            snapshot.completion_enabled,
            snapshot.completion_auto_trigger,
            snapshot.completion_min_chars,
        ),
        diagnostics_preferences=(
            snapshot.diagnostics_enabled,
            snapshot.diagnostics_realtime,
            snapshot.quick_fixes_enabled,
            snapshot.quick_fix_require_preview_for_multifile,
        ),
        output_preferences=(
            snapshot.auto_open_console_on_run_output,
            snapshot.auto_open_problems_on_run_failure,
        ),
        intelligence_runtime_settings=IntelligenceRuntimeSettings(
            cache_enabled=snapshot.cache_enabled,
            incremental_indexing=snapshot.incremental_indexing,
            metrics_logging_enabled=snapshot.metrics_logging_enabled,
            force_full_reindex_on_open=snapshot.force_full_reindex_on_open,
            highlighting_adaptive_mode=snapshot.highlighting_adaptive_mode,
            highlighting_reduced_threshold_chars=snapshot.highlighting_reduced_threshold_chars,
            highlighting_lexical_only_threshold_chars=snapshot.highlighting_lexical_only_threshold_chars,
        ),
    )


def merge_theme_mode(settings_payload: Mapping[str, Any], theme_mode: str) -> dict[str, Any]:
    """Merge validated theme mode into settings payload."""
    merged = dict(settings_payload)
    valid_modes = {constants.UI_THEME_MODE_SYSTEM, constants.UI_THEME_MODE_LIGHT, constants.UI_THEME_MODE_DARK}
    normalized_mode = theme_mode if theme_mode in valid_modes else constants.UI_THEME_MODE_DEFAULT
    theme_payload = merged.get(constants.UI_THEME_SETTINGS_KEY, {})
    if not isinstance(theme_payload, dict):
        theme_payload = {}
    theme_payload = dict(theme_payload)
    theme_payload[constants.UI_THEME_MODE_KEY] = normalized_mode
    merged[constants.UI_THEME_SETTINGS_KEY] = theme_payload
    return merged


def merge_import_update_policy(settings_payload: Mapping[str, Any], policy_value: str) -> dict[str, Any]:
    """Merge import-update policy value into settings payload."""
    merged = dict(settings_payload)
    normalized_policy = policy_value.strip() if policy_value.strip() else constants.UI_IMPORT_UPDATE_POLICY_DEFAULT
    merged[constants.UI_IMPORT_UPDATE_POLICY_KEY] = normalized_policy
    return merged


def merge_last_project_path(settings_payload: Mapping[str, Any], project_root: str) -> dict[str, Any]:
    """Merge last opened project root into settings payload."""
    merged = dict(settings_payload)
    merged[constants.LAST_PROJECT_PATH_KEY] = str(project_root)
    return merged


def merge_editor_settings_snapshot(
    settings_payload: Mapping[str, Any],
    snapshot: EditorSettingsSnapshot,
) -> dict[str, Any]:
    """Merge snapshot back into persisted settings payload."""
    merged = dict(settings_payload)
    merged[constants.UI_EDITOR_SETTINGS_KEY] = {
        constants.UI_EDITOR_TAB_WIDTH_KEY: max(2, int(snapshot.tab_width)),
        constants.UI_EDITOR_FONT_SIZE_KEY: max(8, int(snapshot.font_size)),
        constants.UI_EDITOR_FONT_FAMILY_KEY: str(snapshot.font_family).strip() or constants.UI_EDITOR_FONT_FAMILY_DEFAULT,
        constants.UI_EDITOR_INDENT_STYLE_KEY: "tabs" if snapshot.indent_style == "tabs" else "spaces",
        constants.UI_EDITOR_INDENT_SIZE_KEY: max(1, int(snapshot.indent_size)),
        constants.UI_EDITOR_DETECT_INDENTATION_FROM_FILE_KEY: bool(snapshot.detect_indentation_from_file),
        constants.UI_EDITOR_FORMAT_ON_SAVE_KEY: bool(snapshot.format_on_save),
        constants.UI_EDITOR_TRIM_TRAILING_WHITESPACE_ON_SAVE_KEY: bool(snapshot.trim_trailing_whitespace_on_save),
        constants.UI_EDITOR_INSERT_FINAL_NEWLINE_ON_SAVE_KEY: bool(snapshot.insert_final_newline_on_save),
    }
    merged[constants.UI_INTELLIGENCE_SETTINGS_KEY] = {
        constants.UI_INTELLIGENCE_ENABLE_COMPLETION_KEY: bool(snapshot.completion_enabled),
        constants.UI_INTELLIGENCE_AUTO_TRIGGER_COMPLETION_KEY: bool(snapshot.completion_auto_trigger),
        constants.UI_INTELLIGENCE_COMPLETION_MIN_CHARS_KEY: max(1, int(snapshot.completion_min_chars)),
        constants.UI_INTELLIGENCE_ENABLE_DIAGNOSTICS_KEY: bool(snapshot.diagnostics_enabled),
        constants.UI_INTELLIGENCE_DIAGNOSTICS_REALTIME_KEY: bool(snapshot.diagnostics_realtime),
        constants.UI_INTELLIGENCE_ENABLE_QUICK_FIXES_KEY: bool(snapshot.quick_fixes_enabled),
        constants.UI_INTELLIGENCE_QUICK_FIX_REQUIRE_PREVIEW_FOR_MULTIFILE_KEY: bool(
            snapshot.quick_fix_require_preview_for_multifile
        ),
        constants.UI_INTELLIGENCE_CACHE_ENABLED_KEY: bool(snapshot.cache_enabled),
        constants.UI_INTELLIGENCE_INCREMENTAL_INDEXING_KEY: bool(snapshot.incremental_indexing),
        constants.UI_INTELLIGENCE_METRICS_LOGGING_ENABLED_KEY: bool(snapshot.metrics_logging_enabled),
        constants.UI_INTELLIGENCE_FORCE_FULL_REINDEX_ON_OPEN_KEY: bool(snapshot.force_full_reindex_on_open),
        constants.UI_INTELLIGENCE_HIGHLIGHTING_ADAPTIVE_MODE_KEY: (
            snapshot.highlighting_adaptive_mode
            if snapshot.highlighting_adaptive_mode
            in {
                constants.HIGHLIGHTING_MODE_NORMAL,
                constants.HIGHLIGHTING_MODE_REDUCED,
                constants.HIGHLIGHTING_MODE_LEXICAL_ONLY,
            }
            else constants.UI_INTELLIGENCE_HIGHLIGHTING_ADAPTIVE_MODE_DEFAULT
        ),
        constants.UI_INTELLIGENCE_HIGHLIGHTING_REDUCED_THRESHOLD_CHARS_KEY: max(
            1, int(snapshot.highlighting_reduced_threshold_chars)
        ),
        constants.UI_INTELLIGENCE_HIGHLIGHTING_LEXICAL_ONLY_THRESHOLD_CHARS_KEY: max(
            int(snapshot.highlighting_reduced_threshold_chars),
            int(snapshot.highlighting_lexical_only_threshold_chars),
        ),
    }
    _valid_modes = {constants.UI_THEME_MODE_SYSTEM, constants.UI_THEME_MODE_LIGHT, constants.UI_THEME_MODE_DARK}
    mode = snapshot.theme_mode if snapshot.theme_mode in _valid_modes else constants.UI_THEME_MODE_DEFAULT
    merged[constants.UI_THEME_SETTINGS_KEY] = {
        constants.UI_THEME_MODE_KEY: mode,
    }
    merged[constants.UI_OUTPUT_SETTINGS_KEY] = {
        constants.UI_OUTPUT_AUTO_OPEN_CONSOLE_ON_RUN_OUTPUT_KEY: bool(snapshot.auto_open_console_on_run_output),
        constants.UI_OUTPUT_AUTO_OPEN_PROBLEMS_ON_RUN_FAILURE_KEY: bool(snapshot.auto_open_problems_on_run_failure),
    }
    merged[constants.UI_KEYBINDINGS_SETTINGS_KEY] = {
        constants.UI_KEYBINDINGS_OVERRIDES_KEY: _normalize_string_map(snapshot.shortcut_overrides),
    }
    merged[constants.UI_SYNTAX_COLORS_SETTINGS_KEY] = {
        constants.UI_SYNTAX_COLORS_LIGHT_KEY: _normalize_string_map(snapshot.syntax_color_overrides_light),
        constants.UI_SYNTAX_COLORS_DARK_KEY: _normalize_string_map(snapshot.syntax_color_overrides_dark),
    }
    merged[constants.UI_LINTER_SETTINGS_KEY] = {
        constants.UI_LINTER_RULE_OVERRIDES_KEY: _normalize_lint_rule_override_map(snapshot.lint_rule_overrides),
    }
    merged[constants.UI_FILE_EXCLUDES_SETTINGS_KEY] = {
        constants.UI_FILE_EXCLUDES_PATTERNS_KEY: list(snapshot.file_exclude_patterns),
    }
    return merged


def _coerce_bool(value: Any, *, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _coerce_int(value: Any, *, default: int, minimum: int) -> int:
    if not isinstance(value, int):
        return default
    return max(minimum, value)


def _normalize_string_map(payload: Mapping[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        normalized[key] = value
    return normalized


def _normalize_lint_rule_override_map(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for code, override in payload.items():
        if not isinstance(code, str) or not isinstance(override, Mapping):
            continue
        normalized_override: dict[str, Any] = {}
        enabled = override.get("enabled")
        if isinstance(enabled, bool):
            normalized_override["enabled"] = enabled
        severity = override.get("severity")
        if isinstance(severity, str):
            normalized_override["severity"] = severity
        if normalized_override:
            normalized[code] = normalized_override
    return normalized
