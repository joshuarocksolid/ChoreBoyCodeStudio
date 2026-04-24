"""Unit tests for shell layout persistence helpers."""

from __future__ import annotations

import pytest

from app.core import constants
from app.shell.layout_persistence import (
    DEFAULT_OUTLINE_COLLAPSED,
    DEFAULT_OUTLINE_FOLLOW_CURSOR,
    DEFAULT_OUTLINE_SORT_MODE,
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


def test_parse_shell_layout_state_defaults_explorer_splitter_to_none_when_missing() -> None:
    """Backward-compat: saved settings predating the explorer splitter return None."""
    payload = {
        constants.UI_LAYOUT_SETTINGS_KEY: {
            "width": 1600,
            "height": 900,
            "top_splitter_sizes": [400, 1200],
            "vertical_splitter_sizes": [700, 200],
        }
    }
    parsed = parse_shell_layout_state(payload)
    assert parsed.explorer_splitter_sizes is None


def test_parse_shell_layout_state_reads_explorer_splitter_when_present() -> None:
    payload = {
        constants.UI_LAYOUT_SETTINGS_KEY: {
            "width": 1600,
            "height": 900,
            "top_splitter_sizes": [400, 1200],
            "vertical_splitter_sizes": [700, 200],
            "explorer_splitter_sizes": [600, 400],
        }
    }
    parsed = parse_shell_layout_state(payload)
    assert parsed.explorer_splitter_sizes == (600, 400)


def test_to_dict_omits_explorer_splitter_when_none() -> None:
    state = ShellLayoutState()
    payload = state.to_dict()
    assert "explorer_splitter_sizes" not in payload


def test_to_dict_includes_explorer_splitter_when_set() -> None:
    state = ShellLayoutState(explorer_splitter_sizes=(650, 350))
    payload = state.to_dict()
    assert payload["explorer_splitter_sizes"] == [650, 350]


def test_outline_state_defaults_when_keys_missing() -> None:
    parsed = parse_shell_layout_state(
        {
            constants.UI_LAYOUT_SETTINGS_KEY: {
                "width": 1280,
                "height": 820,
                "top_splitter_sizes": [300, 980],
                "vertical_splitter_sizes": [540, 280],
            }
        }
    )
    assert parsed.outline_collapsed is DEFAULT_OUTLINE_COLLAPSED
    assert parsed.outline_follow_cursor is DEFAULT_OUTLINE_FOLLOW_CURSOR
    assert parsed.outline_sort_mode == DEFAULT_OUTLINE_SORT_MODE


def test_outline_state_round_trips_through_to_dict_and_parse() -> None:
    state = ShellLayoutState(
        outline_collapsed=True,
        outline_follow_cursor=False,
        outline_sort_mode="category",
    )
    payload = {constants.UI_LAYOUT_SETTINGS_KEY: state.to_dict()}
    parsed = parse_shell_layout_state(payload)
    assert parsed.outline_collapsed is True
    assert parsed.outline_follow_cursor is False
    assert parsed.outline_sort_mode == "category"


def test_outline_sort_mode_invalid_value_falls_back_to_position() -> None:
    payload = {
        constants.UI_LAYOUT_SETTINGS_KEY: {
            "width": 1280,
            "height": 820,
            "top_splitter_sizes": [300, 980],
            "vertical_splitter_sizes": [540, 280],
            "outline_sort_mode": "totally-bogus",
        }
    }
    parsed = parse_shell_layout_state(payload)
    assert parsed.outline_sort_mode == DEFAULT_OUTLINE_SORT_MODE


def test_outline_collapsed_invalid_type_falls_back_to_default() -> None:
    payload = {
        constants.UI_LAYOUT_SETTINGS_KEY: {
            "width": 1280,
            "height": 820,
            "top_splitter_sizes": [300, 980],
            "vertical_splitter_sizes": [540, 280],
            "outline_collapsed": "yes",
            "outline_follow_cursor": 1,
        }
    }
    parsed = parse_shell_layout_state(payload)
    assert parsed.outline_collapsed is DEFAULT_OUTLINE_COLLAPSED
    assert parsed.outline_follow_cursor is DEFAULT_OUTLINE_FOLLOW_CURSOR


def test_to_dict_includes_outline_state_keys_with_defaults() -> None:
    state = ShellLayoutState()
    payload = state.to_dict()
    assert payload["outline_collapsed"] is DEFAULT_OUTLINE_COLLAPSED
    assert payload["outline_follow_cursor"] is DEFAULT_OUTLINE_FOLLOW_CURSOR
    assert payload["outline_sort_mode"] == DEFAULT_OUTLINE_SORT_MODE
