"""Old completion settings migrate to the single completion mode."""

from __future__ import annotations

import pytest

from app.intelligence.completion_mode import completion_mode_from_intelligence_settings

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ({}, "manual"),
        ({"enable_completion": True, "auto_trigger_completion": False, "auto_trigger_period": True}, "manual"),
        ({"enable_completion": False, "auto_trigger_completion": True}, "off"),
        ({"enable_completion": True, "auto_trigger_completion": True}, "typing"),
        ({"auto_trigger_period": False}, "manual"),
        ({"completion_mode": "typing", "enable_completion": False}, "typing"),
        ({"completion_mode": "bogus", "auto_trigger_completion": True}, "typing"),
    ],
)
def test_old_settings_migrate_to_the_right_mode(stored: dict, expected: str) -> None:
    assert completion_mode_from_intelligence_settings(stored) == expected
