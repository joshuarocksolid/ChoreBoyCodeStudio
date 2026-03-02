"""Unit tests for shell settings snapshot helpers."""

from __future__ import annotations

import pytest

from app.shell.settings_models import (
    EditorSettingsSnapshot,
    merge_editor_settings_snapshot,
    parse_editor_settings_snapshot,
)

pytestmark = pytest.mark.unit


def test_parse_editor_settings_snapshot_uses_defaults_for_invalid_payload() -> None:
    snapshot = parse_editor_settings_snapshot({"editor": "bad-shape", "intelligence": []})

    assert snapshot.tab_width == 4
    assert snapshot.font_size == 10
    assert snapshot.indent_style == "spaces"
    assert snapshot.completion_enabled is True
    assert snapshot.cache_enabled is True


def test_parse_editor_settings_snapshot_reads_explicit_values() -> None:
    snapshot = parse_editor_settings_snapshot(
        {
            "editor": {
                "tab_width": 8,
                "font_size": 14,
                "indent_style": "tabs",
                "indent_size": 1,
            },
            "intelligence": {
                "enable_completion": False,
                "auto_trigger_completion": False,
                "completion_min_chars": 3,
                "cache_enabled": False,
                "incremental_indexing": False,
                "metrics_logging_enabled": False,
                "force_full_reindex_on_open": True,
            },
        }
    )

    assert snapshot.tab_width == 8
    assert snapshot.font_size == 14
    assert snapshot.indent_style == "tabs"
    assert snapshot.indent_size == 1
    assert snapshot.completion_enabled is False
    assert snapshot.completion_auto_trigger is False
    assert snapshot.completion_min_chars == 3
    assert snapshot.cache_enabled is False
    assert snapshot.incremental_indexing is False
    assert snapshot.metrics_logging_enabled is False
    assert snapshot.force_full_reindex_on_open is True


def test_merge_editor_settings_snapshot_writes_editor_and_intelligence_keys() -> None:
    snapshot = EditorSettingsSnapshot(
        tab_width=6,
        font_size=12,
        indent_style="tabs",
        indent_size=1,
        completion_enabled=False,
        completion_auto_trigger=False,
        completion_min_chars=3,
        cache_enabled=False,
        incremental_indexing=True,
        metrics_logging_enabled=False,
        force_full_reindex_on_open=True,
    )
    merged = merge_editor_settings_snapshot({"schema_version": 1}, snapshot)

    assert merged["editor"]["tab_width"] == 6
    assert merged["editor"]["indent_style"] == "tabs"
    assert merged["intelligence"]["enable_completion"] is False
    assert merged["intelligence"]["cache_enabled"] is False
    assert merged["intelligence"]["force_full_reindex_on_open"] is True
