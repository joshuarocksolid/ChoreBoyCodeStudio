"""Unit tests for JSON-backed persistence helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core import constants
from app.persistence.settings_store import load_json_object, save_json_object

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
        },
    }
    save_json_object(path, payload)
    loaded = load_json_object(path, default={"schema_version": 1})
    assert loaded[constants.UI_EDITOR_SETTINGS_KEY][constants.UI_EDITOR_TAB_WIDTH_KEY] == 2
    assert loaded[constants.UI_EDITOR_SETTINGS_KEY][constants.UI_EDITOR_FONT_SIZE_KEY] == 12
    assert loaded[constants.UI_EDITOR_SETTINGS_KEY][constants.UI_EDITOR_INDENT_STYLE_KEY] == "tabs"
    assert loaded[constants.UI_EDITOR_SETTINGS_KEY][constants.UI_EDITOR_INDENT_SIZE_KEY] == 1
    assert loaded[constants.UI_EDITOR_SETTINGS_KEY][constants.UI_EDITOR_DETECT_INDENTATION_FROM_FILE_KEY] is False


def test_settings_payload_can_store_intelligence_cache_preferences(tmp_path: Path) -> None:
    """Intelligence cache flags should round-trip in settings payload."""
    path = tmp_path / "state" / "settings.json"
    payload = {
        "schema_version": 1,
        constants.UI_INTELLIGENCE_SETTINGS_KEY: {
            constants.UI_INTELLIGENCE_CACHE_ENABLED_KEY: False,
            constants.UI_INTELLIGENCE_INCREMENTAL_INDEXING_KEY: True,
            constants.UI_INTELLIGENCE_METRICS_LOGGING_ENABLED_KEY: False,
            constants.UI_INTELLIGENCE_FORCE_FULL_REINDEX_ON_OPEN_KEY: True,
        },
    }
    save_json_object(path, payload)
    loaded = load_json_object(path, default={"schema_version": 1})
    intelligence_settings = loaded[constants.UI_INTELLIGENCE_SETTINGS_KEY]
    assert intelligence_settings[constants.UI_INTELLIGENCE_CACHE_ENABLED_KEY] is False
    assert intelligence_settings[constants.UI_INTELLIGENCE_INCREMENTAL_INDEXING_KEY] is True
    assert intelligence_settings[constants.UI_INTELLIGENCE_METRICS_LOGGING_ENABLED_KEY] is False
    assert intelligence_settings[constants.UI_INTELLIGENCE_FORCE_FULL_REINDEX_ON_OPEN_KEY] is True
