from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core import constants


def plugin_safe_mode_enabled(settings_payload: Mapping[str, Any]) -> bool:
    plugins_payload = settings_payload.get(constants.UI_PLUGINS_SETTINGS_KEY, {})
    if not isinstance(plugins_payload, dict):
        return constants.UI_PLUGINS_SAFE_MODE_DEFAULT
    raw_value = plugins_payload.get(
        constants.UI_PLUGINS_SAFE_MODE_KEY,
        constants.UI_PLUGINS_SAFE_MODE_DEFAULT,
    )
    return bool(raw_value) if isinstance(raw_value, bool) else constants.UI_PLUGINS_SAFE_MODE_DEFAULT


def merge_plugin_safe_mode(
    settings_payload: Mapping[str, Any],
    *,
    enabled: bool,
) -> dict[str, Any]:
    merged_payload = dict(settings_payload)
    plugins_payload = merged_payload.get(constants.UI_PLUGINS_SETTINGS_KEY, {})
    if not isinstance(plugins_payload, dict):
        plugins_payload = {}
    plugins_payload = dict(plugins_payload)
    plugins_payload[constants.UI_PLUGINS_SAFE_MODE_KEY] = bool(enabled)
    merged_payload[constants.UI_PLUGINS_SETTINGS_KEY] = plugins_payload
    return merged_payload


def should_disable_plugin_after_failure(failure_count: int, threshold: int | None = None) -> bool:
    resolved_threshold = (
        constants.PLUGIN_DISABLE_AFTER_FAILURES_DEFAULT
        if threshold is None
        else max(1, int(threshold))
    )
    return failure_count >= resolved_threshold
