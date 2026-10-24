"""Canvas-only text size and screen scale.

``text_point_size`` None is the startup font (Normal). Screen percent
multiplies that one point size. Nothing here writes a document.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

_SCREENS = (100, 125, 150, 200)
_FACTORS = {"smaller": 0.85, "larger": 1.25, "largest": 1.5}
_WORDS = {
    "smaller": "smaller text",
    "larger": "larger text",
    "largest": "largest text",
}
_FALLBACK_POINT = 10.0


def base_point_size(startup_point_size: Optional[float]) -> float:
    """Startup point size, or 10 when the font has none."""
    if startup_point_size is None or startup_point_size <= 0:
        return _FALLBACK_POINT
    return float(startup_point_size)


def points_for_preset(startup_point_size: Optional[float], preset: str) -> Optional[float]:
    """None for Normal. Smaller, Larger and Largest are factors of the base."""
    if preset == "normal":
        return None
    factor = _FACTORS.get(preset)
    if factor is None:
        raise ValueError("unknown text preset %r" % preset)
    return base_point_size(startup_point_size) * factor


@dataclass(frozen=True)
class PreviewState:
    """One preview. Point size and screen percent are not two fonts."""

    text_point_size: Optional[float] = None
    screen_percent: int = 100

    def __post_init__(self) -> None:
        if self.screen_percent not in _SCREENS:
            raise ValueError("screen percent must be 100, 125, 150, or 200")

    def is_plain(self) -> bool:
        return self.text_point_size is None and self.screen_percent == 100


def applied_point_size(state: PreviewState, startup_point_size: Optional[float]) -> float:
    """The single point size ``setFont`` uses."""
    base = state.text_point_size
    if base is None:
        base = base_point_size(startup_point_size)
    return float(base) * (state.screen_percent / 100.0)


def active_preset(state: PreviewState, startup_point_size: Optional[float]) -> Optional[str]:
    """``normal`` when the field is unset. None when the points are not a preset."""
    if state.text_point_size is None:
        return "normal"
    base = base_point_size(startup_point_size)
    for name, factor in _FACTORS.items():
        if abs(state.text_point_size - base * factor) < 0.05:
            return name
    return None


def pill_sentence(
    state: PreviewState, startup_point_size: Optional[float], cutoff: int
) -> Optional[str]:
    """The backdrop sentence, or None while the preview is Normal at 100%."""
    lead = _lead(state, startup_point_size)
    if lead is None:
        return None
    if cutoff > 0:
        return "%s %s \u00b7 Reset" % (lead, _cutoff_phrase(cutoff))
    return "%s \u00b7 Reset" % lead


def _lead(state: PreviewState, startup_point_size: Optional[float]) -> Optional[str]:
    if state.is_plain():
        return None
    phrase = ""
    if state.text_point_size is not None:
        phrase = _phrase(state.text_point_size, base_point_size(startup_point_size))
    screen = ""
    if state.screen_percent != 100:
        screen = "%d%% screen" % state.screen_percent
    if phrase and screen:
        return "Previewing %s at %s" % (phrase, screen)
    if phrase:
        return "Previewing %s" % phrase
    return "Previewing %s" % screen


def _phrase(points: float, base: float) -> str:
    for name, factor in _FACTORS.items():
        if abs(points - base * factor) < 0.05:
            return _WORDS[name]
    return "%s pt text" % ("%g" % points)


def _cutoff_phrase(count: int) -> str:
    if count == 1:
        return "\u00b7 1 widget cut off text"
    return "\u00b7 %d widgets cut off text" % count
