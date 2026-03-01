"""Shell window layout persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.core import constants

DEFAULT_WINDOW_WIDTH = 1280
DEFAULT_WINDOW_HEIGHT = 820
DEFAULT_TOP_SPLITTER_SIZES = (300, 980)
DEFAULT_VERTICAL_SPLITTER_SIZES = (540, 280)


@dataclass(frozen=True)
class ShellLayoutState:
    """Serializable shell layout state."""

    width: int = DEFAULT_WINDOW_WIDTH
    height: int = DEFAULT_WINDOW_HEIGHT
    top_splitter_sizes: tuple[int, int] = DEFAULT_TOP_SPLITTER_SIZES
    vertical_splitter_sizes: tuple[int, int] = DEFAULT_VERTICAL_SPLITTER_SIZES

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "top_splitter_sizes": list(self.top_splitter_sizes),
            "vertical_splitter_sizes": list(self.vertical_splitter_sizes),
        }


def parse_shell_layout_state(settings_payload: Mapping[str, Any]) -> ShellLayoutState:
    """Parse UI layout state from settings payload with safe defaults."""
    raw_layout = settings_payload.get(constants.UI_LAYOUT_SETTINGS_KEY)
    if not isinstance(raw_layout, Mapping):
        return ShellLayoutState()

    width = _parse_dimension(raw_layout.get("width"), DEFAULT_WINDOW_WIDTH)
    height = _parse_dimension(raw_layout.get("height"), DEFAULT_WINDOW_HEIGHT)
    top_sizes = _parse_splitter_sizes(raw_layout.get("top_splitter_sizes"), DEFAULT_TOP_SPLITTER_SIZES)
    vertical_sizes = _parse_splitter_sizes(raw_layout.get("vertical_splitter_sizes"), DEFAULT_VERTICAL_SPLITTER_SIZES)
    return ShellLayoutState(
        width=width,
        height=height,
        top_splitter_sizes=top_sizes,
        vertical_splitter_sizes=vertical_sizes,
    )


def merge_layout_into_settings(settings_payload: Mapping[str, Any], layout_state: ShellLayoutState) -> dict[str, Any]:
    """Merge serialized layout state into settings payload copy."""
    merged = dict(settings_payload)
    merged[constants.UI_LAYOUT_SETTINGS_KEY] = layout_state.to_dict()
    return merged


def _parse_dimension(raw_value: Any, default: int) -> int:
    if not isinstance(raw_value, int):
        return default
    return max(320, raw_value)


def _parse_splitter_sizes(raw_value: Any, default: tuple[int, int]) -> tuple[int, int]:
    if not isinstance(raw_value, list) or len(raw_value) != 2:
        return default
    first, second = raw_value
    if not isinstance(first, int) or not isinstance(second, int):
        return default
    return (max(80, first), max(80, second))
