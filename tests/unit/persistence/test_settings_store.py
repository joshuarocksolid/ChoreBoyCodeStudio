"""Unit tests for JSON-backed persistence helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core import constants
from app.persistence.settings_store import (
    compute_effective_settings_payload,
    filter_project_settings_payload,
    load_json_object,
    load_project_settings,
    project_settings_has_overrides,
    save_json_object,
    save_project_settings,
)

pytestmark = pytest.mark.unit


def test_load_json_object_returns_default_copy_when_file_missing(tmp_path: Path) -> None:
    """Missing files should return a safe default object."""
    default_payload = {"items": []}
    payload = load_json_object(tmp_path / "missing.json", default=default_payload)

    assert payload == {"items": []}
    assert payload is not default_payload


def test_load_json_object_returns_default_copy_when_json_is_corrupt(tmp_path: Path) -> None:
    """Corrupt JSON should fail gracefully and return default content."""
    path = tmp_path / "state" / "corrupt.json"
    path.parent.mkdir(parents=True)
    path.write_text("{ not json", encoding="utf-8")

    payload = load_json_object(path, default={"schema_version": 1, "projects": []})

    assert payload == {"schema_version": 1, "projects": []}


def test_load_json_object_returns_default_copy_when_json_root_is_not_object(tmp_path: Path) -> None:
    """JSON payload roots must be object-shaped for deterministic callers."""
    path = tmp_path / "state" / "array.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(["bad", "shape"]), encoding="utf-8")

    payload = load_json_object(path, default={"schema_version": 1})

    assert payload == {"schema_version": 1}


def test_save_json_object_creates_parent_dirs_and_writes_deterministic_json(tmp_path: Path) -> None:
    """Saving should ensure parent dirs and persist stable UTF-8 JSON."""
    path = tmp_path / "state" / "nested" / "settings.json"
    payload = {
        "schema_version": 1,
        "projects": ["/tmp/beta", "/tmp/alpha"],
    }

    saved_path = save_json_object(path, payload)

    assert saved_path == path.resolve()
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == payload
    expected_text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    assert path.read_text(encoding="utf-8") == expected_text


def test_save_json_object_rejects_non_mapping_payload(tmp_path: Path) -> None:
    """Saving non-object payloads should raise a clear error."""
    path = tmp_path / "state" / "bad.json"

    with pytest.raises(ValueError):
        save_json_object(path, ["not", "an", "object"])  # type: ignore[arg-type]


def test_settings_payload_can_store_import_update_policy_key(tmp_path: Path) -> None:
    """Import update policy should round-trip through generic settings store."""
    path = tmp_path / "state" / "settings.json"
    payload = {"schema_version": 1, constants.UI_IMPORT_UPDATE_POLICY_KEY: "ask"}
    save_json_object(path, payload)
    loaded = load_json_object(path, default={"schema_version": 1})
    assert loaded[constants.UI_IMPORT_UPDATE_POLICY_KEY] == "ask"


def test_settings_payload_can_store_editor_preferences(tmp_path: Path) -> None:
    """Editor tab-width and font-size settings should round-trip."""
    path = tmp_path / "state" / "settings.json"
    payload = {
        "schema_version": 1,
        constants.UI_EDITOR_SETTINGS_KEY: {
            constants.UI_EDITOR_TAB_WIDTH_KEY: 2,
            constants.UI_EDITOR_FONT_SIZE_KEY: 12,
            constants.UI_EDITOR_INDENT_STYLE_KEY: "tabs",
            constants.UI_EDITOR_INDENT_SIZE_KEY: 1,
            constants.UI_EDITOR_DETECT_INDENTATION_FROM_FILE_KEY: False,
            constants.UI_EDITOR_FORMAT_ON_SAVE_KEY: True,
            constants.UI_EDITOR_TRIM_TRAILING_WHITESPACE_ON_SAVE_KEY: False,
            constants.UI_EDITOR_INSERT_FINAL_NEWLINE_ON_SAVE_KEY: False,
        },
    }
    save_json_object(path, payload)
    loaded = load_json_object(path, default={"schema_version": 1})
    assert loaded[constants.UI_EDITOR_SETTINGS_KEY][constants.UI_EDITOR_TAB_WIDTH_KEY] == 2
    assert loaded[constants.UI_EDITOR_SETTINGS_KEY][constants.UI_EDITOR_FONT_SIZE_KEY] == 12
    assert loaded[constants.UI_EDITOR_SETTINGS_KEY][constants.UI_EDITOR_INDENT_STYLE_KEY] == "tabs"
    assert loaded[constants.UI_EDITOR_SETTINGS_KEY][constants.UI_EDITOR_INDENT_SIZE_KEY] == 1
    assert loaded[constants.UI_EDITOR_SETTINGS_KEY][constants.UI_EDITOR_DETECT_INDENTATION_FROM_FILE_KEY] is False
    assert loaded[constants.UI_EDITOR_SETTINGS_KEY][constants.UI_EDITOR_FORMAT_ON_SAVE_KEY] is True
    assert loaded[constants.UI_EDITOR_SETTINGS_KEY][constants.UI_EDITOR_TRIM_TRAILING_WHITESPACE_ON_SAVE_KEY] is False
    assert loaded[constants.UI_EDITOR_SETTINGS_KEY][constants.UI_EDITOR_INSERT_FINAL_NEWLINE_ON_SAVE_KEY] is False


def test_settings_payload_can_store_intelligence_cache_preferences(tmp_path: Path) -> None:
    """Intelligence cache flags should round-trip in settings payload."""
    path = tmp_path / "state" / "settings.json"
    payload = {
        "schema_version": 1,
        constants.UI_INTELLIGENCE_SETTINGS_KEY: {
            constants.UI_INTELLIGENCE_ENABLE_DIAGNOSTICS_KEY: False,
            constants.UI_INTELLIGENCE_DIAGNOSTICS_REALTIME_KEY: False,
            constants.UI_INTELLIGENCE_ENABLE_QUICK_FIXES_KEY: False,
            constants.UI_INTELLIGENCE_QUICK_FIX_REQUIRE_PREVIEW_FOR_MULTIFILE_KEY: False,
            constants.UI_INTELLIGENCE_CACHE_ENABLED_KEY: False,
            constants.UI_INTELLIGENCE_INCREMENTAL_INDEXING_KEY: True,
            constants.UI_INTELLIGENCE_METRICS_LOGGING_ENABLED_KEY: False,
            constants.UI_INTELLIGENCE_FORCE_FULL_REINDEX_ON_OPEN_KEY: True,
        },
    }
    save_json_object(path, payload)
    loaded = load_json_object(path, default={"schema_version": 1})
    intelligence_settings = loaded[constants.UI_INTELLIGENCE_SETTINGS_KEY]
    assert intelligence_settings[constants.UI_INTELLIGENCE_ENABLE_DIAGNOSTICS_KEY] is False
    assert intelligence_settings[constants.UI_INTELLIGENCE_DIAGNOSTICS_REALTIME_KEY] is False
    assert intelligence_settings[constants.UI_INTELLIGENCE_ENABLE_QUICK_FIXES_KEY] is False
    assert intelligence_settings[constants.UI_INTELLIGENCE_QUICK_FIX_REQUIRE_PREVIEW_FOR_MULTIFILE_KEY] is False
    assert intelligence_settings[constants.UI_INTELLIGENCE_CACHE_ENABLED_KEY] is False
    assert intelligence_settings[constants.UI_INTELLIGENCE_INCREMENTAL_INDEXING_KEY] is True
    assert intelligence_settings[constants.UI_INTELLIGENCE_METRICS_LOGGING_ENABLED_KEY] is False
    assert intelligence_settings[constants.UI_INTELLIGENCE_FORCE_FULL_REINDEX_ON_OPEN_KEY] is True


def test_load_project_settings_returns_default_copy_when_missing(tmp_path: Path) -> None:
    payload = load_project_settings(tmp_path / "project")

    assert payload == {"schema_version": 1}


def test_save_project_settings_filters_non_overridable_root_keys(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    payload = {
        "schema_version": 7,
        constants.UI_EDITOR_SETTINGS_KEY: {
            constants.UI_EDITOR_TAB_WIDTH_KEY: 2,
        },
        constants.UI_THEME_SETTINGS_KEY: {
            constants.UI_THEME_MODE_KEY: constants.UI_THEME_MODE_DARK,
        },
        constants.UI_KEYBINDINGS_SETTINGS_KEY: {
            constants.UI_KEYBINDINGS_OVERRIDES_KEY: {"shell.action.file.save": "Ctrl+Shift+S"},
        },
    }

    saved_path = save_project_settings(project_root, payload)
    loaded = json.loads(saved_path.read_text(encoding="utf-8"))

    assert loaded == {
        "schema_version": 7,
        constants.UI_EDITOR_SETTINGS_KEY: {
            constants.UI_EDITOR_TAB_WIDTH_KEY: 2,
        },
    }


def test_compute_effective_settings_payload_layers_defaults_global_and_project() -> None:
    global_payload = {
        "schema_version": 3,
        constants.UI_EDITOR_SETTINGS_KEY: {
            constants.UI_EDITOR_TAB_WIDTH_KEY: 4,
            constants.UI_EDITOR_FONT_SIZE_KEY: 12,
        },
        constants.UI_OUTPUT_SETTINGS_KEY: {
            constants.UI_OUTPUT_AUTO_OPEN_CONSOLE_ON_RUN_OUTPUT_KEY: True,
        },
    }
    project_payload = {
        "schema_version": 9,
        constants.UI_EDITOR_SETTINGS_KEY: {
            constants.UI_EDITOR_TAB_WIDTH_KEY: 2,
        },
        constants.UI_OUTPUT_SETTINGS_KEY: {
            constants.UI_OUTPUT_AUTO_OPEN_PROBLEMS_ON_RUN_FAILURE_KEY: False,
        },
        constants.UI_THEME_SETTINGS_KEY: {
            constants.UI_THEME_MODE_KEY: constants.UI_THEME_MODE_DARK,
        },
    }

    effective = compute_effective_settings_payload(global_payload, project_payload)

    assert effective["schema_version"] == 9
    assert effective[constants.UI_EDITOR_SETTINGS_KEY][constants.UI_EDITOR_TAB_WIDTH_KEY] == 2
    assert effective[constants.UI_EDITOR_SETTINGS_KEY][constants.UI_EDITOR_FONT_SIZE_KEY] == 12
    assert effective[constants.UI_OUTPUT_SETTINGS_KEY][constants.UI_OUTPUT_AUTO_OPEN_CONSOLE_ON_RUN_OUTPUT_KEY] is True
    assert (
        effective[constants.UI_OUTPUT_SETTINGS_KEY][constants.UI_OUTPUT_AUTO_OPEN_PROBLEMS_ON_RUN_FAILURE_KEY]
        is False
    )
    assert constants.UI_THEME_SETTINGS_KEY not in effective


def test_filter_project_settings_payload_keeps_overridable_nested_maps_only() -> None:
    filtered = filter_project_settings_payload(
        {
            "schema_version": 2,
            constants.UI_LINTER_SETTINGS_KEY: {
                constants.UI_LINTER_RULE_OVERRIDES_KEY: {"PY220": {"enabled": False}},
            },
            constants.UI_LAYOUT_SETTINGS_KEY: {"width": 1111},
        }
    )

    assert filtered == {
        "schema_version": 2,
        constants.UI_LINTER_SETTINGS_KEY: {
            constants.UI_LINTER_RULE_OVERRIDES_KEY: {"PY220": {"enabled": False}},
        },
    }


def test_project_settings_has_overrides_true_only_for_overridable_sections() -> None:
    assert project_settings_has_overrides({"schema_version": 1}) is False
    assert project_settings_has_overrides({constants.UI_THEME_SETTINGS_KEY: {"mode": "dark"}}) is False
    assert project_settings_has_overrides(
        {
            constants.UI_OUTPUT_SETTINGS_KEY: {
                constants.UI_OUTPUT_AUTO_OPEN_CONSOLE_ON_RUN_OUTPUT_KEY: False,
            }
        }
    ) is True
