"""Runtime controls for intelligence cache behavior."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.core import constants


@dataclass(frozen=True)
class IntelligenceRuntimeSettings:
    """Parsed runtime settings for intelligence cache behavior."""

    cache_enabled: bool = constants.UI_INTELLIGENCE_CACHE_ENABLED_DEFAULT
    incremental_indexing: bool = constants.UI_INTELLIGENCE_INCREMENTAL_INDEXING_DEFAULT
    metrics_logging_enabled: bool = constants.UI_INTELLIGENCE_METRICS_LOGGING_ENABLED_DEFAULT
    force_full_reindex_on_open: bool = constants.UI_INTELLIGENCE_FORCE_FULL_REINDEX_ON_OPEN_DEFAULT
    highlighting_adaptive_mode: str = constants.UI_INTELLIGENCE_HIGHLIGHTING_ADAPTIVE_MODE_DEFAULT
    highlighting_reduced_threshold_chars: int = constants.UI_INTELLIGENCE_HIGHLIGHTING_REDUCED_THRESHOLD_CHARS_DEFAULT
    highlighting_lexical_only_threshold_chars: int = (
        constants.UI_INTELLIGENCE_HIGHLIGHTING_LEXICAL_ONLY_THRESHOLD_CHARS_DEFAULT
    )


def parse_intelligence_runtime_settings(settings_payload: Mapping[str, Any]) -> IntelligenceRuntimeSettings:
    """Parse intelligence runtime settings from global settings payload."""
    intelligence_settings = settings_payload.get(constants.UI_INTELLIGENCE_SETTINGS_KEY, {})
    if not isinstance(intelligence_settings, dict):
        return IntelligenceRuntimeSettings()

    cache_enabled = intelligence_settings.get(
        constants.UI_INTELLIGENCE_CACHE_ENABLED_KEY,
        constants.UI_INTELLIGENCE_CACHE_ENABLED_DEFAULT,
    )
    incremental_indexing = intelligence_settings.get(
        constants.UI_INTELLIGENCE_INCREMENTAL_INDEXING_KEY,
        constants.UI_INTELLIGENCE_INCREMENTAL_INDEXING_DEFAULT,
    )
    metrics_logging_enabled = intelligence_settings.get(
        constants.UI_INTELLIGENCE_METRICS_LOGGING_ENABLED_KEY,
        constants.UI_INTELLIGENCE_METRICS_LOGGING_ENABLED_DEFAULT,
    )
    force_full_reindex_on_open = intelligence_settings.get(
        constants.UI_INTELLIGENCE_FORCE_FULL_REINDEX_ON_OPEN_KEY,
        constants.UI_INTELLIGENCE_FORCE_FULL_REINDEX_ON_OPEN_DEFAULT,
    )
    highlighting_adaptive_mode = intelligence_settings.get(
        constants.UI_INTELLIGENCE_HIGHLIGHTING_ADAPTIVE_MODE_KEY,
        constants.UI_INTELLIGENCE_HIGHLIGHTING_ADAPTIVE_MODE_DEFAULT,
    )
    highlighting_reduced_threshold_chars = intelligence_settings.get(
        constants.UI_INTELLIGENCE_HIGHLIGHTING_REDUCED_THRESHOLD_CHARS_KEY,
        constants.UI_INTELLIGENCE_HIGHLIGHTING_REDUCED_THRESHOLD_CHARS_DEFAULT,
    )
    highlighting_lexical_only_threshold_chars = intelligence_settings.get(
        constants.UI_INTELLIGENCE_HIGHLIGHTING_LEXICAL_ONLY_THRESHOLD_CHARS_KEY,
        constants.UI_INTELLIGENCE_HIGHLIGHTING_LEXICAL_ONLY_THRESHOLD_CHARS_DEFAULT,
    )

    valid_modes = {
        constants.HIGHLIGHTING_MODE_NORMAL,
        constants.HIGHLIGHTING_MODE_REDUCED,
        constants.HIGHLIGHTING_MODE_LEXICAL_ONLY,
    }
    parsed_mode = (
        str(highlighting_adaptive_mode)
        if str(highlighting_adaptive_mode) in valid_modes
        else constants.UI_INTELLIGENCE_HIGHLIGHTING_ADAPTIVE_MODE_DEFAULT
    )
    reduced_threshold = _coerce_positive_int(
        highlighting_reduced_threshold_chars,
        default=constants.UI_INTELLIGENCE_HIGHLIGHTING_REDUCED_THRESHOLD_CHARS_DEFAULT,
    )
    lexical_only_threshold = _coerce_positive_int(
        highlighting_lexical_only_threshold_chars,
        default=constants.UI_INTELLIGENCE_HIGHLIGHTING_LEXICAL_ONLY_THRESHOLD_CHARS_DEFAULT,
    )
    if lexical_only_threshold < reduced_threshold:
        lexical_only_threshold = reduced_threshold

    return IntelligenceRuntimeSettings(
        cache_enabled=cache_enabled if isinstance(cache_enabled, bool) else constants.UI_INTELLIGENCE_CACHE_ENABLED_DEFAULT,
        incremental_indexing=(
            incremental_indexing
            if isinstance(incremental_indexing, bool)
            else constants.UI_INTELLIGENCE_INCREMENTAL_INDEXING_DEFAULT
        ),
        metrics_logging_enabled=(
            metrics_logging_enabled
            if isinstance(metrics_logging_enabled, bool)
            else constants.UI_INTELLIGENCE_METRICS_LOGGING_ENABLED_DEFAULT
        ),
        force_full_reindex_on_open=(
            force_full_reindex_on_open
            if isinstance(force_full_reindex_on_open, bool)
            else constants.UI_INTELLIGENCE_FORCE_FULL_REINDEX_ON_OPEN_DEFAULT
        ),
        highlighting_adaptive_mode=parsed_mode,
        highlighting_reduced_threshold_chars=reduced_threshold,
        highlighting_lexical_only_threshold_chars=lexical_only_threshold,
    )


def should_refresh_index_after_save(settings: IntelligenceRuntimeSettings, *, has_loaded_project: bool) -> bool:
    """Return whether save should trigger symbol index refresh."""
    return has_loaded_project and settings.cache_enabled and settings.incremental_indexing


def rebuild_symbol_cache(cache_db_path: str) -> bool:
    """Delete symbol cache file if present; return True when deleted."""
    path = Path(cache_db_path).expanduser().resolve()
    if not path.exists():
        return False
    path.unlink()
    return True


def _coerce_positive_int(value: Any, *, default: int) -> int:
    if not isinstance(value, int):
        return default
    if value <= 0:
        return default
    return value
