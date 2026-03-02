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


def test_parse_intelligence_runtime_settings_uses_defaults_for_missing_payload() -> None:
    settings = parse_intelligence_runtime_settings({})

    assert settings.cache_enabled is True
    assert settings.incremental_indexing is True
    assert settings.metrics_logging_enabled is True
    assert settings.force_full_reindex_on_open is False


def test_parse_intelligence_runtime_settings_reads_boolean_flags() -> None:
    settings = parse_intelligence_runtime_settings(
        {
            "intelligence": {
                "cache_enabled": False,
                "incremental_indexing": False,
                "metrics_logging_enabled": False,
                "force_full_reindex_on_open": True,
            }
        }
    )

    assert settings.cache_enabled is False
    assert settings.incremental_indexing is False
    assert settings.metrics_logging_enabled is False
    assert settings.force_full_reindex_on_open is True


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
