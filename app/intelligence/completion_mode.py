"""The one code-completion setting: Off, Manual (Ctrl+Space) or While typing."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from app.core import constants

COMPLETION_MODE_OFF = constants.UI_INTELLIGENCE_COMPLETION_MODE_OFF
COMPLETION_MODE_MANUAL = constants.UI_INTELLIGENCE_COMPLETION_MODE_MANUAL
COMPLETION_MODE_TYPING = constants.UI_INTELLIGENCE_COMPLETION_MODE_TYPING
COMPLETION_MODES: tuple[str, ...] = constants.UI_INTELLIGENCE_COMPLETION_MODE_VALUES
COMPLETION_MODE_DEFAULT = constants.UI_INTELLIGENCE_COMPLETION_MODE_DEFAULT

COMPLETION_MODE_KEY = constants.UI_INTELLIGENCE_COMPLETION_MODE_KEY
LEGACY_ENABLE_COMPLETION_KEY = "enable_completion"
LEGACY_AUTO_TRIGGER_COMPLETION_KEY = "auto_trigger_completion"
LEGACY_AUTO_TRIGGER_PERIOD_KEY = "auto_trigger_period"

COMPLETION_MODE_LABELS = {
    COMPLETION_MODE_OFF: "Off",
    COMPLETION_MODE_MANUAL: "Manual (Ctrl+Space)",
    COMPLETION_MODE_TYPING: "While typing",
}

COMPLETION_MODE_HELP = {
    COMPLETION_MODE_OFF: "Never shows the list. Ctrl+Space does nothing.",
    COMPLETION_MODE_MANUAL: (
        "Nothing pops up by itself, not even after '.'. Press Ctrl+Space to open the list; "
        "it then filters as you type."
    ),
    COMPLETION_MODE_TYPING: (
        "Opens after '.' on a name and after two letters of a name. "
        "Never in strings, comments or after a number."
    ),
}

COMPLETION_OFF_HINT = "Code completion is off. Turn it on in Settings > General > Intelligence."


def normalize_completion_mode(value: Any) -> Optional[str]:
    """Return ``value`` when it names a mode, else ``None``."""

    return value if isinstance(value, str) and value in COMPLETION_MODES else None


def completion_mode_from_intelligence_settings(intelligence_settings: Mapping[str, Any]) -> str:
    """Read the mode, migrating the three pre-v0.4.13 completion settings.

    A user who explicitly turned completion off gets Off. A user who explicitly
    turned on auto-trigger gets While typing. Everyone else gets Manual.
    """

    mode = normalize_completion_mode(intelligence_settings.get(COMPLETION_MODE_KEY))
    if mode is not None:
        return mode
    if intelligence_settings.get(LEGACY_ENABLE_COMPLETION_KEY) is False:
        return COMPLETION_MODE_OFF
    if intelligence_settings.get(LEGACY_AUTO_TRIGGER_COMPLETION_KEY) is True:
        return COMPLETION_MODE_TYPING
    return COMPLETION_MODE_DEFAULT


def project_legacy_completion_mode(project_intelligence: Mapping[str, Any]) -> Optional[str]:
    """Map a project layer that still uses the pre-v0.4.13 keys.

    A valid ``completion_mode`` on that layer is left to the normal merge.
    ``auto_trigger_period`` by itself is not an override. Turning completion
    off wins over an auto-trigger flag on the same layer.
    """

    if normalize_completion_mode(project_intelligence.get(COMPLETION_MODE_KEY)) is not None:
        return None
    if project_intelligence.get(LEGACY_ENABLE_COMPLETION_KEY) is False:
        return COMPLETION_MODE_OFF
    auto_trigger = project_intelligence.get(LEGACY_AUTO_TRIGGER_COMPLETION_KEY)
    if isinstance(auto_trigger, bool):
        if auto_trigger:
            return COMPLETION_MODE_TYPING
        return COMPLETION_MODE_MANUAL
    return None


def completion_mode_from_flags(*, enabled: bool, auto_trigger: bool) -> str:
    """Map the window's enabled / auto-trigger flags back onto a mode."""

    if not enabled:
        return COMPLETION_MODE_OFF
    if auto_trigger:
        return COMPLETION_MODE_TYPING
    return COMPLETION_MODE_MANUAL


def completion_mode_label(mode: str) -> str:
    return COMPLETION_MODE_LABELS.get(mode, COMPLETION_MODE_LABELS[COMPLETION_MODE_DEFAULT])


def describe_effective_completion_mode(
    *,
    global_mode: str,
    project_mode: Optional[str],
    project_available: bool,
) -> str:
    """Say which mode is in effect and which settings scope it comes from.

    ``project_mode`` is ``None`` when the project follows the Global value.
    """

    global_label = completion_mode_label(global_mode)
    if not project_available:
        return "In effect: <b>{}</b><br>from <b>Global</b> settings.".format(global_label)
    if project_mode is None:
        return (
            "In effect for this project: <b>{}</b><br>"
            "from <b>Global</b> settings (Project: Use Global)."
        ).format(global_label)
    return (
        "In effect for this project: <b>{}</b><br>"
        "set in <b>Project</b> settings (overrides Global: {})."
    ).format(completion_mode_label(project_mode), global_label)


__all__ = [
    "COMPLETION_MODES",
    "COMPLETION_MODE_DEFAULT",
    "COMPLETION_MODE_HELP",
    "COMPLETION_MODE_KEY",
    "COMPLETION_MODE_LABELS",
    "COMPLETION_MODE_MANUAL",
    "COMPLETION_MODE_OFF",
    "COMPLETION_MODE_TYPING",
    "COMPLETION_OFF_HINT",
    "completion_mode_from_flags",
    "completion_mode_from_intelligence_settings",
    "project_legacy_completion_mode",
    "completion_mode_label",
    "describe_effective_completion_mode",
    "normalize_completion_mode",
]
