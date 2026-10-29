"""Preview style and screen choices, kept per user (M5.5a, UX-PREV-001, R3 178 and 179).

The choices are not in the form. ``PreviewChoices`` is what the Aa menu shows as
checked; ``appearance_for`` turns it into the optional ``Appearance`` fields the
preview child understands (CONTRACTS section 10: no version bump). The canvas
always shows the ChoreBoy look (D21); nothing here touches it.

Everything in this module is Qt-free so the menu text, the window title and the
profile checks can be tested without a display.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.ipc.protocol import Appearance

DEFAULT_STYLE = "Fusion"
DEFAULT_SCREEN = "ChoreBoy screen"
CAPTION = "Preview only. The canvas always shows the ChoreBoy look."
ADD_SCREEN = "Add a screen…"

MIN_WIDTH, MAX_WIDTH = 320, 7680
MIN_HEIGHT, MAX_HEIGHT = 240, 4320
MIN_FONT, MAX_FONT = 6, 72
MIN_SCALE, MAX_SCALE = 100, 200

_TIMES = " × "
_DOT = " · "


@dataclass(frozen=True)
class ScreenProfile:
    """A screen the preview pretends to be on. ``font`` empty and ``font_size`` 0 keep the runtime font."""

    name: str
    width: int
    height: int
    font: str = ""
    font_size: int = 0
    scale: int = 100
    builtin: bool = False

    @property
    def label(self) -> str:
        """The menu text: ``Small screen · 1024 × 600``."""
        return "%s%s%d%s%d" % (self.name, _DOT, self.width, _TIMES, self.height)


BUILT_IN: Tuple[ScreenProfile, ...] = (
    ScreenProfile(DEFAULT_SCREEN, 1366, 768, builtin=True),
    ScreenProfile("Small screen", 1024, 600, builtin=True),
    ScreenProfile("Full HD", 1920, 1080, builtin=True),
)


@dataclass(frozen=True)
class PreviewChoices:
    """The style key and the screen profile name the user picked."""

    style: str = DEFAULT_STYLE
    screen: str = DEFAULT_SCREEN


def style_label(name: str) -> str:
    """``Fusion · as on ChoreBoy`` for the default, else the style's own name."""
    return "%s%sas on ChoreBoy" % (name, _DOT) if name == DEFAULT_STYLE else name


def ordered_styles(reported: Iterable[str]) -> Tuple[str, ...]:
    """The styles to list: Fusion first, then what the runtime reports, in its order, without repeats."""
    seen: List[str] = [DEFAULT_STYLE]
    for name in reported:
        if name and name.lower() not in {item.lower() for item in seen}:
            seen.append(str(name))
    return tuple(seen)


def all_profiles(user: Sequence[ScreenProfile]) -> Tuple[ScreenProfile, ...]:
    """Built-in screens, then the user's in the order they were added."""
    return BUILT_IN + tuple(user)


def find_profile(name: str, user: Sequence[ScreenProfile]) -> ScreenProfile:
    """The profile called ``name`` (any case), else the default screen."""
    wanted = name.strip().lower()
    for profile in all_profiles(user):
        if profile.name.lower() == wanted:
            return profile
    return BUILT_IN[0]


def clean_profile(
    name: str,
    width: int,
    height: int,
    font: str = "",
    font_size: int = 0,
    scale: int = 100,
) -> Optional[ScreenProfile]:
    """A user profile with every number held to its range, or None when the name is blank."""
    cleaned = " ".join(name.split())
    if not cleaned:
        return None
    return ScreenProfile(
        name=cleaned,
        width=max(MIN_WIDTH, min(MAX_WIDTH, int(width))),
        height=max(MIN_HEIGHT, min(MAX_HEIGHT, int(height))),
        font=font.strip(),
        font_size=0 if int(font_size) <= 0 else max(MIN_FONT, min(MAX_FONT, int(font_size))),
        scale=max(MIN_SCALE, min(MAX_SCALE, int(scale))),
    )


def name_is_built_in(name: str) -> bool:
    wanted = " ".join(name.split()).lower()
    return any(profile.name.lower() == wanted for profile in BUILT_IN)


def with_profile(user: Sequence[ScreenProfile], profile: ScreenProfile) -> Tuple[ScreenProfile, ...]:
    """``user`` with ``profile`` added, or replacing the one that has its name."""
    kept = [item for item in user if item.name.lower() != profile.name.lower()]
    kept.append(replace(profile, builtin=False))
    return tuple(kept)


def window_title(form_file: str, choices: PreviewChoices, user: Sequence[ScreenProfile]) -> str:
    """``Preview · invoice.ui · Windows style · Small screen``: only the choices that are not the default."""
    parts = ["Preview", form_file]
    if choices.style.lower() != DEFAULT_STYLE.lower():
        parts.append("%s style" % choices.style)
    profile = find_profile(choices.screen, user)
    if profile.name != DEFAULT_SCREEN:
        parts.append(profile.name)
    return _DOT.join(parts)


def appearance_for(form_file: str, choices: PreviewChoices, user: Sequence[ScreenProfile]) -> Appearance:
    """The ``Appearance`` of a load or a ``set_appearance`` for these choices."""
    profile = find_profile(choices.screen, user)
    return Appearance(
        style=choices.style or DEFAULT_STYLE,
        scale=float(profile.scale) / 100.0,
        device_profile=None if profile.name == DEFAULT_SCREEN else profile.name,
        title=window_title(form_file, choices, user),
        font_family=profile.font or None,
        font_point_size=float(profile.font_size) if profile.font_size else None,
        screen_width=profile.width,
        screen_height=profile.height,
    )


__all__ = [
    "ADD_SCREEN",
    "BUILT_IN",
    "CAPTION",
    "DEFAULT_SCREEN",
    "DEFAULT_STYLE",
    "PreviewChoices",
    "ScreenProfile",
    "all_profiles",
    "appearance_for",
    "clean_profile",
    "find_profile",
    "name_is_built_in",
    "ordered_styles",
    "style_label",
    "window_title",
    "with_profile",
]
