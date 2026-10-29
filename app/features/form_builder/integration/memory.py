"""Per-user form builder choices in the global settings store (CONTRACTS section 14).

The keys live in ``form_builder`` on the same JSON file as the rest of the
shell settings. A missing or unreadable block is the default. Reads of keys
Settings > Form designer can change re-read the file (``force_refresh``), so a
change there shows without a restart; writes go through ``update_global``.
"""

from __future__ import annotations

from typing import Any, List, Mapping, Optional, Tuple

from app.features.form_builder.integration.layout import WorkbenchMemory
from app.features.form_builder.engine.preview_options import (
    DEFAULT_SCREEN,
    DEFAULT_STYLE,
    PreviewChoices,
    ScreenProfile,
    clean_profile,
    name_is_built_in,
)
from app.persistence.settings_service import SettingsService

SETTINGS_KEY = "form_builder"
WORKBENCH_KEY = "workbench"
QT_NAMES_KEY = "qt_names"
SORT_PROPERTIES_KEY = "sort_properties"
PREVIEW_KEY = "preview"

_BOOLS = (
    "outline_collapsed",
    "insert_collapsed",
    "pin_left",
    "pin_inspector",
)
_INTS = ("left", "inspector", "outline_share")


def memory_from_payload(payload: Mapping[str, Any]) -> WorkbenchMemory:
    section = payload.get(SETTINGS_KEY)
    if not isinstance(section, Mapping):
        return WorkbenchMemory()
    raw = section.get(WORKBENCH_KEY)
    if not isinstance(raw, Mapping):
        return WorkbenchMemory()
    values: dict[str, Any] = {}
    for name in _INTS:
        item = raw.get(name)
        if isinstance(item, int) and not isinstance(item, bool):
            values[name] = item
    for name in _BOOLS:
        item = raw.get(name)
        if isinstance(item, bool):
            values[name] = item
    return WorkbenchMemory(**values).clamped()


def payload_with_memory(payload: Mapping[str, Any], memory: WorkbenchMemory) -> dict[str, Any]:
    updated = dict(payload)
    section_raw = updated.get(SETTINGS_KEY)
    section = dict(section_raw) if isinstance(section_raw, Mapping) else {}
    stored = memory.clamped()
    section[WORKBENCH_KEY] = {
        "left": stored.left,
        "inspector": stored.inspector,
        "outline_share": stored.outline_share,
        "outline_collapsed": stored.outline_collapsed,
        "insert_collapsed": stored.insert_collapsed,
        "pin_left": stored.pin_left,
        "pin_inspector": stored.pin_inspector,
    }
    updated[SETTINGS_KEY] = section
    return updated


def qt_names_from_payload(payload: Mapping[str, Any]) -> bool:
    section = payload.get(SETTINGS_KEY)
    if not isinstance(section, Mapping):
        return False
    return section.get(QT_NAMES_KEY) is True


def payload_with_qt_names(payload: Mapping[str, Any], shown: bool) -> dict[str, Any]:
    updated = dict(payload)
    section_raw = updated.get(SETTINGS_KEY)
    section = dict(section_raw) if isinstance(section_raw, Mapping) else {}
    section[QT_NAMES_KEY] = bool(shown)
    updated[SETTINGS_KEY] = section
    return updated


def sort_properties_from_payload(payload: Mapping[str, Any]) -> bool:
    section = payload.get(SETTINGS_KEY)
    if not isinstance(section, Mapping):
        return False
    return section.get(SORT_PROPERTIES_KEY) is True


def payload_with_sort_properties(payload: Mapping[str, Any], shown: bool) -> dict[str, Any]:
    updated = dict(payload)
    section_raw = updated.get(SETTINGS_KEY)
    section = dict(section_raw) if isinstance(section_raw, Mapping) else {}
    section[SORT_PROPERTIES_KEY] = bool(shown)
    updated[SETTINGS_KEY] = section
    return updated


def preview_from_payload(payload: Mapping[str, Any]) -> Tuple[PreviewChoices, Tuple[ScreenProfile, ...]]:
    """The user's preview style, screen and screen profiles (UX-PREV-001, CONTRACTS section 14).

    One source of truth for the Aa menu and Settings > Form designer: ``preview_style``
    (absent: Fusion) and ``preview_screen`` (``small``, ``full_hd``, a profile of the
    user's by name, absent: the ChoreBoy screen). ``preview.profiles`` keeps the user's
    screens. A missing or wrongly typed value is the default.
    """
    section_raw = payload.get(SETTINGS_KEY)
    section: Mapping[str, Any] = section_raw if isinstance(section_raw, Mapping) else {}
    raw = section.get(PREVIEW_KEY)
    profiles: List[ScreenProfile] = []
    listed = raw.get("profiles") if isinstance(raw, Mapping) else None
    for item in listed if isinstance(listed, list) else ():
        if not isinstance(item, Mapping):
            continue
        profile = _profile_from(item)
        if profile is not None and not name_is_built_in(profile.name):
            profiles = [other for other in profiles if other.name.lower() != profile.name.lower()]
            profiles.append(profile)
    style = section.get(STYLE_KEY)
    screen = section.get(SCREEN_KEY)
    chosen = DEFAULT_SCREEN
    if isinstance(screen, str):
        if screen in _SCREEN_KEYS:
            chosen = _SCREEN_KEYS[screen]
        else:
            for profile in profiles:
                if profile.name.lower() == screen.strip().lower():
                    chosen = profile.name
    choices = PreviewChoices(
        style=style if isinstance(style, str) and style.strip() else DEFAULT_STYLE,
        screen=chosen,
    )
    return choices, tuple(profiles)


STYLE_KEY = "preview_style"
SCREEN_KEY = "preview_screen"
#: The built-in screens' values of ``preview_screen`` (Settings > Form designer writes the same).
_SCREEN_KEYS = {"small": "Small screen", "full_hd": "Full HD"}


def _profile_from(item: Mapping[str, Any]) -> Optional[ScreenProfile]:
    name = item.get("name")
    numbers = []
    for key, default in (("width", 0), ("height", 0), ("font_size", 0), ("scale", 100)):
        value = item.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        numbers.append(value)
    font = item.get("font", "")
    if not isinstance(name, str) or not isinstance(font, str):
        return None
    return clean_profile(name, numbers[0], numbers[1], font, numbers[2], numbers[3])


def payload_with_preview(
    payload: Mapping[str, Any],
    choices: PreviewChoices,
    profiles: Tuple[ScreenProfile, ...],
) -> dict[str, Any]:
    """``payload`` with this style, screen and the user's screens; default choices are written as absent keys."""
    updated = dict(payload)
    section_raw = updated.get(SETTINGS_KEY)
    section = dict(section_raw) if isinstance(section_raw, Mapping) else {}
    if choices.style and choices.style.lower() != DEFAULT_STYLE.lower():
        section[STYLE_KEY] = choices.style
    else:
        section.pop(STYLE_KEY, None)
    screen_value = {name: key for key, name in _SCREEN_KEYS.items()}.get(choices.screen)
    if screen_value is None and choices.screen != DEFAULT_SCREEN:
        screen_value = choices.screen
    if screen_value:
        section[SCREEN_KEY] = screen_value
    else:
        section.pop(SCREEN_KEY, None)
    section[PREVIEW_KEY] = {
        "profiles": [
            {
                "name": item.name,
                "width": item.width,
                "height": item.height,
                "font": item.font,
                "font_size": item.font_size,
                "scale": item.scale,
            }
            for item in profiles
        ],
    }
    updated[SETTINGS_KEY] = section
    return updated


class PreviewOptionsStore:
    """Load and save one user's preview style, screen and screen profiles."""

    def __init__(self, state_root: Optional[str] = None) -> None:
        self._service = SettingsService(state_root=state_root)

    def load(self) -> Tuple[PreviewChoices, Tuple[ScreenProfile, ...]]:
        try:
            # Settings > Form designer writes the same keys from another SettingsService.
            return preview_from_payload(self._service.load_global(force_refresh=True))
        except OSError:
            return PreviewChoices(), ()

    def save(self, choices: PreviewChoices, profiles: Tuple[ScreenProfile, ...]) -> None:
        try:
            self._service.update_global(lambda payload: payload_with_preview(payload, choices, profiles))
        except OSError:
            return


class WorkbenchMemoryStore:
    """Load and save one user's workbench memory."""

    def __init__(self, state_root: Optional[str] = None) -> None:
        self._service = SettingsService(state_root=state_root)
        self._memory: Optional[WorkbenchMemory] = None

    def load(self) -> WorkbenchMemory:
        if self._memory is None:
            try:
                self._memory = memory_from_payload(self._service.load_global())
            except OSError:
                self._memory = WorkbenchMemory()
        return self._memory

    def save(self, memory: WorkbenchMemory) -> None:
        stored = memory.clamped()
        self._memory = stored
        try:
            self._service.update_global(lambda payload: payload_with_memory(payload, stored))
        except OSError:
            return

    def qt_names(self) -> bool:
        try:
            return qt_names_from_payload(self._service.load_global(force_refresh=True))
        except OSError:
            return False

    def set_qt_names(self, shown: bool) -> None:
        try:
            self._service.update_global(lambda payload: payload_with_qt_names(payload, shown))
        except OSError:
            return

    def sort_properties(self) -> bool:
        try:
            return sort_properties_from_payload(self._service.load_global(force_refresh=True))
        except OSError:
            return False

    def set_sort_properties(self, shown: bool) -> None:
        try:
            self._service.update_global(lambda payload: payload_with_sort_properties(payload, shown))
        except OSError:
            return


__all__ = [
    "PREVIEW_KEY",
    "SCREEN_KEY",
    "STYLE_KEY",
    "PreviewOptionsStore",
    "QT_NAMES_KEY",
    "SORT_PROPERTIES_KEY",
    "SETTINGS_KEY",
    "WORKBENCH_KEY",
    "WorkbenchMemoryStore",
    "memory_from_payload",
    "payload_with_memory",
    "payload_with_preview",
    "payload_with_qt_names",
    "payload_with_sort_properties",
    "preview_from_payload",
    "qt_names_from_payload",
    "sort_properties_from_payload",
]
