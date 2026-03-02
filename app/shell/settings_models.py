"""Pure settings parsing/serialization helpers for shell settings UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.core import constants


@dataclass(frozen=True)
class EditorSettingsSnapshot:
    """Editable settings snapshot shown in settings dialog."""

    tab_width: int = constants.UI_EDITOR_TAB_WIDTH_DEFAULT
    font_size: int = constants.UI_EDITOR_FONT_SIZE_DEFAULT
    indent_style: str = constants.UI_EDITOR_INDENT_STYLE_DEFAULT
    indent_size: int = constants.UI_EDITOR_INDENT_SIZE_DEFAULT
    detect_indentation_from_file: bool = constants.UI_EDITOR_DETECT_INDENTATION_FROM_FILE_DEFAULT
    format_on_save: bool = constants.UI_EDITOR_FORMAT_ON_SAVE_DEFAULT
    trim_trailing_whitespace_on_save: bool = constants.UI_EDITOR_TRIM_TRAILING_WHITESPACE_ON_SAVE_DEFAULT
    insert_final_newline_on_save: bool = constants.UI_EDITOR_INSERT_FINAL_NEWLINE_ON_SAVE_DEFAULT
    completion_enabled: bool = constants.UI_INTELLIGENCE_ENABLE_COMPLETION_DEFAULT
    completion_auto_trigger: bool = constants.UI_INTELLIGENCE_AUTO_TRIGGER_COMPLETION_DEFAULT
    completion_min_chars: int = constants.UI_INTELLIGENCE_COMPLETION_MIN_CHARS_DEFAULT
    cache_enabled: bool = constants.UI_INTELLIGENCE_CACHE_ENABLED_DEFAULT
    incremental_indexing: bool = constants.UI_INTELLIGENCE_INCREMENTAL_INDEXING_DEFAULT
    metrics_logging_enabled: bool = constants.UI_INTELLIGENCE_METRICS_LOGGING_ENABLED_DEFAULT
    force_full_reindex_on_open: bool = constants.UI_INTELLIGENCE_FORCE_FULL_REINDEX_ON_OPEN_DEFAULT


def parse_editor_settings_snapshot(settings_payload: Mapping[str, Any]) -> EditorSettingsSnapshot:
    """Parse persisted settings payload into editable snapshot."""
    editor_settings = settings_payload.get(constants.UI_EDITOR_SETTINGS_KEY, {})
    if not isinstance(editor_settings, dict):
        editor_settings = {}
    intelligence_settings = settings_payload.get(constants.UI_INTELLIGENCE_SETTINGS_KEY, {})
    if not isinstance(intelligence_settings, dict):
        intelligence_settings = {}

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
        cache_enabled=_coerce_bool(
            intelligence_settings.get(constants.UI_INTELLIGENCE_CACHE_ENABLED_KEY),
            default=constants.UI_INTELLIGENCE_CACHE_ENABLED_DEFAULT,
        ),
        incremental_indexing=_coerce_bool(
            intelligence_settings.get(constants.UI_INTELLIGENCE_INCREMENTAL_INDEXING_KEY),
            default=constants.UI_INTELLIGENCE_INCREMENTAL_INDEXING_DEFAULT,
        ),
        metrics_logging_enabled=_coerce_bool(
            intelligence_settings.get(constants.UI_INTELLIGENCE_METRICS_LOGGING_ENABLED_KEY),
            default=constants.UI_INTELLIGENCE_METRICS_LOGGING_ENABLED_DEFAULT,
        ),
        force_full_reindex_on_open=_coerce_bool(
            intelligence_settings.get(constants.UI_INTELLIGENCE_FORCE_FULL_REINDEX_ON_OPEN_KEY),
            default=constants.UI_INTELLIGENCE_FORCE_FULL_REINDEX_ON_OPEN_DEFAULT,
        ),
    )


def merge_editor_settings_snapshot(
    settings_payload: Mapping[str, Any],
    snapshot: EditorSettingsSnapshot,
) -> dict[str, Any]:
    """Merge snapshot back into persisted settings payload."""
    merged = dict(settings_payload)
    merged[constants.UI_EDITOR_SETTINGS_KEY] = {
        constants.UI_EDITOR_TAB_WIDTH_KEY: max(2, int(snapshot.tab_width)),
        constants.UI_EDITOR_FONT_SIZE_KEY: max(8, int(snapshot.font_size)),
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
        constants.UI_INTELLIGENCE_CACHE_ENABLED_KEY: bool(snapshot.cache_enabled),
        constants.UI_INTELLIGENCE_INCREMENTAL_INDEXING_KEY: bool(snapshot.incremental_indexing),
        constants.UI_INTELLIGENCE_METRICS_LOGGING_ENABLED_KEY: bool(snapshot.metrics_logging_enabled),
        constants.UI_INTELLIGENCE_FORCE_FULL_REINDEX_ON_OPEN_KEY: bool(snapshot.force_full_reindex_on_open),
    }
    return merged


def _coerce_bool(value: Any, *, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _coerce_int(value: Any, *, default: int, minimum: int) -> int:
    if not isinstance(value, int):
        return default
    return max(minimum, value)
