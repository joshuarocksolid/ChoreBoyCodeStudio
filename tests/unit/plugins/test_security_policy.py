"""Unit tests for plugin safety policy helpers."""

from __future__ import annotations

import pytest

from app.core import constants
from app.plugins.security_policy import (
    merge_plugin_safe_mode,
    plugin_safe_mode_enabled,
    should_disable_plugin_after_failure,
)

pytestmark = pytest.mark.unit


def test_plugin_safe_mode_enabled_uses_defaults_for_missing_payload() -> None:
    assert plugin_safe_mode_enabled({}) == constants.UI_PLUGINS_SAFE_MODE_DEFAULT


def test_plugin_safe_mode_enabled_reads_boolean_flag() -> None:
    payload = {
        constants.UI_PLUGINS_SETTINGS_KEY: {
            constants.UI_PLUGINS_SAFE_MODE_KEY: True,
        }
    }
    assert plugin_safe_mode_enabled(payload) is True


def test_merge_plugin_safe_mode_preserves_existing_settings() -> None:
    payload = {"existing": {"value": 1}}

    merged = merge_plugin_safe_mode(payload, enabled=True)

    assert merged["existing"] == {"value": 1}
    assert merged[constants.UI_PLUGINS_SETTINGS_KEY][constants.UI_PLUGINS_SAFE_MODE_KEY] is True


def test_should_disable_plugin_after_failure_respects_threshold() -> None:
    assert should_disable_plugin_after_failure(3, threshold=3) is True
    assert should_disable_plugin_after_failure(2, threshold=3) is False
    assert should_disable_plugin_after_failure(constants.PLUGIN_DISABLE_AFTER_FAILURES_DEFAULT) is True
