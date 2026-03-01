"""Unit tests for shell layout persistence helpers."""

from __future__ import annotations

import pytest

from app.core import constants
from app.shell.layout_persistence import (
    DEFAULT_TOP_SPLITTER_SIZES,
    DEFAULT_VERTICAL_SPLITTER_SIZES,
    ShellLayoutState,
    merge_layout_into_settings,
    parse_shell_layout_state,
)

pytestmark = pytest.mark.unit


def test_parse_shell_layout_state_returns_defaults_for_missing_payload() -> None:
    """Missing layout payload should map to deterministic defaults."""
    parsed = parse_shell_layout_state({})
    assert parsed == ShellLayoutState()


def test_parse_shell_layout_state_reads_valid_payload() -> None:
    """Valid layout payload should be parsed without fallback."""
    payload = {
        constants.UI_LAYOUT_SETTINGS_KEY: {
            "width": 1600,
            "height": 900,
            "top_splitter_sizes": [400, 1200],
            "vertical_splitter_sizes": [700, 200],
        }
    }
    parsed = parse_shell_layout_state(payload)
    assert parsed.width == 1600
    assert parsed.height == 900
    assert parsed.top_splitter_sizes == (400, 1200)
    assert parsed.vertical_splitter_sizes == (700, 200)


def test_parse_shell_layout_state_falls_back_for_invalid_splitter_shapes() -> None:
    """Invalid splitter shapes should safely fall back to defaults."""
    payload = {
        constants.UI_LAYOUT_SETTINGS_KEY: {
            "width": "bad",
            "height": None,
            "top_splitter_sizes": [10],
            "vertical_splitter_sizes": ["a", "b"],
        }
    }
    parsed = parse_shell_layout_state(payload)
    assert parsed.width == ShellLayoutState().width
    assert parsed.height == ShellLayoutState().height
    assert parsed.top_splitter_sizes == DEFAULT_TOP_SPLITTER_SIZES
    assert parsed.vertical_splitter_sizes == DEFAULT_VERTICAL_SPLITTER_SIZES


def test_merge_layout_into_settings_replaces_layout_key_only() -> None:
    """Merging layout should preserve unrelated settings keys."""
    merged = merge_layout_into_settings(
        {"foo": "bar"},
        ShellLayoutState(width=1111, height=777, top_splitter_sizes=(300, 900), vertical_splitter_sizes=(500, 240)),
    )
    assert merged["foo"] == "bar"
    assert merged[constants.UI_LAYOUT_SETTINGS_KEY]["width"] == 1111
