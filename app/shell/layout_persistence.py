"""Shell window layout persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.core import constants

DEFAULT_WINDOW_WIDTH = 1280
DEFAULT_WINDOW_HEIGHT = 820
DEFAULT_TOP_SPLITTER_SIZES = (300, 980)
DEFAULT_VERTICAL_SPLITTER_SIZES = (540, 280)
DEFAULT_EXPLORER_SPLITTER_SIZES = (700, 300)

DEFAULT_OUTLINE_COLLAPSED = False
DEFAULT_OUTLINE_FOLLOW_CURSOR = True
DEFAULT_OUTLINE_SORT_MODE = "position"
_VALID_OUTLINE_SORT_MODES = frozenset({"position", "name", "category"})


@dataclass(frozen=True)
class ShellLayoutState:
    """Serializable shell layout state."""

    width: int = DEFAULT_WINDOW_WIDTH
    height: int = DEFAULT_WINDOW_HEIGHT
    top_splitter_sizes: tuple[int, int] = DEFAULT_TOP_SPLITTER_SIZES
    vertical_splitter_sizes: tuple[int, int] = DEFAULT_VERTICAL_SPLITTER_SIZES
    explorer_splitter_sizes: tuple[int, int] | None = None
    outline_collapsed: bool = DEFAULT_OUTLINE_COLLAPSED
    outline_follow_cursor: bool = DEFAULT_OUTLINE_FOLLOW_CURSOR
    outline_sort_mode: str = DEFAULT_OUTLINE_SORT_MODE

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "width": self.width,
            "height": self.height,
            "top_splitter_sizes": list(self.top_splitter_sizes),
            "vertical_splitter_sizes": list(self.vertical_splitter_sizes),
            "outline_collapsed": bool(self.outline_collapsed),
            "outline_follow_cursor": bool(self.outline_follow_cursor),
            "outline_sort_mode": self.outline_sort_mode,
        }
        if self.explorer_splitter_sizes is not None:
            payload["explorer_splitter_sizes"] = list(self.explorer_splitter_sizes)
        return payload


def parse_shell_layout_state(settings_payload: Mapping[str, Any]) -> ShellLayoutState:
    """Parse UI layout state from settings payload with safe defaults."""
    raw_layout = settings_payload.get(constants.UI_LAYOUT_SETTINGS_KEY)
    if not isinstance(raw_layout, Mapping):
        return ShellLayoutState()

    width = _parse_dimension(raw_layout.get("width"), DEFAULT_WINDOW_WIDTH)
    height = _parse_dimension(raw_layout.get("height"), DEFAULT_WINDOW_HEIGHT)
    top_sizes = _parse_splitter_sizes(raw_layout.get("top_splitter_sizes"), DEFAULT_TOP_SPLITTER_SIZES)
    vertical_sizes = _parse_splitter_sizes(raw_layout.get("vertical_splitter_sizes"), DEFAULT_VERTICAL_SPLITTER_SIZES)
    explorer_raw = raw_layout.get("explorer_splitter_sizes")
    explorer_sizes: tuple[int, int] | None
    if explorer_raw is None:
        explorer_sizes = None
    else:
        explorer_sizes = _parse_splitter_sizes(explorer_raw, DEFAULT_EXPLORER_SPLITTER_SIZES)
    outline_collapsed = _parse_bool(
        raw_layout.get("outline_collapsed"), DEFAULT_OUTLINE_COLLAPSED
    )
    outline_follow_cursor = _parse_bool(
        raw_layout.get("outline_follow_cursor"), DEFAULT_OUTLINE_FOLLOW_CURSOR
    )
    outline_sort_mode = _parse_sort_mode(raw_layout.get("outline_sort_mode"))
    return ShellLayoutState(
        width=width,
        height=height,
        top_splitter_sizes=top_sizes,
        vertical_splitter_sizes=vertical_sizes,
        explorer_splitter_sizes=explorer_sizes,
        outline_collapsed=outline_collapsed,
        outline_follow_cursor=outline_follow_cursor,
        outline_sort_mode=outline_sort_mode,
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


def _parse_bool(raw_value: Any, default: bool) -> bool:
    if isinstance(raw_value, bool):
        return raw_value
    return default


def _parse_sort_mode(raw_value: Any) -> str:
    if isinstance(raw_value, str) and raw_value in _VALID_OUTLINE_SORT_MODES:
        return raw_value
    return DEFAULT_OUTLINE_SORT_MODE
