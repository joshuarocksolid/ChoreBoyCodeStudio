"""Unit tests for intelligence cache runtime controls."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence.cache_controls import (
    IntelligenceRuntimeSettings,
    parse_intelligence_runtime_settings,
    rebuild_symbol_cache,
    should_refresh_index_after_save,
)

pytestmark = pytest.mark.unit


_DEFAULT_FIELDS = {
    "cache_enabled": True,
    "incremental_indexing": True,
    "metrics_logging_enabled": True,
    "force_full_reindex_on_open": False,
    "highlighting_adaptive_mode": "normal",
    "highlighting_reduced_threshold_chars": 250_000,
    "highlighting_lexical_only_threshold_chars": 600_000,
}

_EXPLICIT_PAYLOAD = {
    "intelligence": {
        "cache_enabled": False,
        "incremental_indexing": False,
        "metrics_logging_enabled": False,
        "force_full_reindex_on_open": True,
        "highlighting_adaptive_mode": "reduced",
        "highlighting_reduced_threshold_chars": 180000,
        "highlighting_lexical_only_threshold_chars": 360000,
    }
}

_EXPLICIT_FIELDS = {
    "cache_enabled": False,
    "incremental_indexing": False,
    "metrics_logging_enabled": False,
    "force_full_reindex_on_open": True,
    "highlighting_adaptive_mode": "reduced",
    "highlighting_reduced_threshold_chars": 180000,
    "highlighting_lexical_only_threshold_chars": 360000,
}


@pytest.mark.parametrize(
    ("payload", "field", "expected"),
    [
        ({}, field, value)
        for field, value in _DEFAULT_FIELDS.items()
    ]
    + [
        (_EXPLICIT_PAYLOAD, field, value)
        for field, value in _EXPLICIT_FIELDS.items()
    ],
)
def test_parse_intelligence_runtime_settings_field_value(
    payload: dict, field: str, expected: object
) -> None:
    settings = parse_intelligence_runtime_settings(payload)
    assert getattr(settings, field) == expected


def test_parse_intelligence_runtime_settings_clamps_invalid_highlighting_values() -> None:
    settings = parse_intelligence_runtime_settings(
        {
            "intelligence": {
                "highlighting_adaptive_mode": "garbage",
                "highlighting_reduced_threshold_chars": -1,
                "highlighting_lexical_only_threshold_chars": 10,
            }
        }
    )
    assert settings.highlighting_adaptive_mode == "normal"
    assert settings.highlighting_reduced_threshold_chars == 250_000
    assert settings.highlighting_lexical_only_threshold_chars == 250_000


def test_should_refresh_index_after_save_requires_project_and_enabled_flags() -> None:
    settings = IntelligenceRuntimeSettings(cache_enabled=True, incremental_indexing=True)
    assert should_refresh_index_after_save(settings, has_loaded_project=True) is True
    assert should_refresh_index_after_save(settings, has_loaded_project=False) is False
    assert (
        should_refresh_index_after_save(
            IntelligenceRuntimeSettings(cache_enabled=False, incremental_indexing=True),
            has_loaded_project=True,
        )
        is False
    )


def test_rebuild_symbol_cache_deletes_existing_cache_file(tmp_path: Path) -> None:
    cache_path = tmp_path / "state" / "symbols.sqlite3"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text("placeholder", encoding="utf-8")

    deleted = rebuild_symbol_cache(str(cache_path))

    assert deleted is True
    assert not cache_path.exists()


def test_rebuild_symbol_cache_returns_false_when_file_missing(tmp_path: Path) -> None:
    cache_path = tmp_path / "missing.sqlite3"
    assert rebuild_symbol_cache(str(cache_path)) is False
