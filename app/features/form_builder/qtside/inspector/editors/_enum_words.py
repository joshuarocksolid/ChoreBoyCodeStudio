"""Friendly names for enumerators and flags.

A pair table wins, then a name table, then splitting the enumerator into words.
"""

from __future__ import annotations

import re
from typing import Sequence, Tuple

# Names whose word split is not what the screen should say.
_BY_NAME = {
    "PasswordEchoOnEdit": "Password while typing",
    "HLine": "Horizontal line",
    "VLine": "Vertical line",
    "WinPanel": "Windows panel",
    "TextSelectableByMouse": "Select with mouse",
    "TextSelectableByKeyboard": "Select with keyboard",
    "LinksAccessibleByMouse": "Open links with the mouse",
    "LinksAccessibleByKeyboard": "Open links with the keyboard",
    "TextEditable": "Editable",
    "TextEditorInteraction": "Text editor",
    "TextBrowserInteraction": "Text browser",
    "NoTextInteraction": "No interaction",
    "AlignLeft": "Left",
    "AlignLeading": "Left",
    "AlignRight": "Right",
    "AlignTrailing": "Right",
    "AlignHCenter": "Centre",
    "AlignVCenter": "Vertically centred",
    "AlignTop": "Top",
    "AlignBottom": "Bottom",
    "AlignJustify": "Justify",
    # Layout rows already shipped these short labels.
    "SetDefaultConstraint": "Default",
    "SetNoConstraint": "None",
    "SetMinimumSize": "Minimum",
    "SetFixedSize": "Fixed",
    "SetMaximumSize": "Maximum",
    "SetMinAndMaxSize": "Min and max",
    "FieldsStayAtSizeHint": "Stay at hint",
    "ExpandingFieldsGrow": "Expanding",
    "AllNonFixedFieldsGrow": "All but fixed",
    "DontWrapRows": "Don't wrap",
    "WrapLongRows": "Long rows",
    "WrapAllRows": "All rows",
}

# Echo mode and frame, where the spec names the words outright.
_BY_PAIR = {
    ("EchoMode", "Normal"): "Normal",
    ("EchoMode", "NoEcho"): "No echo",
    ("EchoMode", "Password"): "Password",
    ("EchoMode", "PasswordEchoOnEdit"): "Password while typing",
    ("echoMode", "Normal"): "Normal",
    ("echoMode", "NoEcho"): "No echo",
    ("echoMode", "Password"): "Password",
    ("echoMode", "PasswordEchoOnEdit"): "Password while typing",
    ("Shape", "NoFrame"): "No frame",
    ("Shape", "Box"): "Box",
    ("Shape", "Panel"): "Panel",
    ("Shape", "StyledPanel"): "Styled panel",
    ("Shape", "HLine"): "Horizontal line",
    ("Shape", "VLine"): "Vertical line",
    ("Shape", "WinPanel"): "Windows panel",
    ("frameShape", "NoFrame"): "No frame",
    ("frameShape", "Box"): "Box",
    ("frameShape", "Panel"): "Panel",
    ("frameShape", "StyledPanel"): "Styled panel",
    ("frameShape", "HLine"): "Horizontal line",
    ("frameShape", "VLine"): "Vertical line",
    ("frameShape", "WinPanel"): "Windows panel",
    ("Shadow", "Plain"): "Plain",
    ("Shadow", "Raised"): "Raised",
    ("Shadow", "Sunken"): "Sunken",
    ("frameShadow", "Plain"): "Plain",
    ("frameShadow", "Raised"): "Raised",
    ("frameShadow", "Sunken"): "Sunken",
}

_HORIZONTAL = (
    "AlignLeft",
    "AlignLeading",
    "AlignHCenter",
    "AlignRight",
    "AlignTrailing",
    "AlignJustify",
)
_VERTICAL = ("AlignTop", "AlignVCenter", "AlignBottom", "AlignBaseline")

_SPLIT_LOWER = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_SPLIT_ACRONYM = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")

POLICY_ORDER = (
    "Fixed",
    "Minimum",
    "Maximum",
    "Preferred",
    "Expanding",
    "MinimumExpanding",
    "Ignored",
)

POLICY_HELP = {
    "Fixed": "Exactly its size hint.",
    "Minimum": "Can grow; never smaller than its size hint.",
    "Maximum": "Can shrink; never larger than its size hint.",
    "Preferred": "Its size hint, but can grow or shrink.",
    "Expanding": "Takes all the room it can.",
    "MinimumExpanding": "Takes all the room it can; never smaller than its size hint.",
    "Ignored": "Ignores its size hint; takes the room it's given.",
}


def split_words(name: str) -> str:
    """MinimumExpanding becomes "Minimum expanding"."""
    spaced = _SPLIT_ACRONYM.sub(" ", _SPLIT_LOWER.sub(" ", name)).strip()
    parts = spaced.split()
    if not parts:
        return name
    head = parts[0][:1].upper() + parts[0][1:]
    return " ".join([head] + [part.lower() for part in parts[1:]])


def friendly(type_name: str, prop_name: str, enumerator: str) -> str:
    for key in ((type_name, enumerator), (prop_name, enumerator)):
        found = _BY_PAIR.get(key)
        if found:
            return found
    found = _BY_NAME.get(enumerator)
    if found:
        return found
    # inputMethodHints: ImhDigitsOnly reads "Digits only", not "Imh digits only".
    if enumerator.startswith("Imh") and len(enumerator) > 3 and enumerator[3].isupper():
        return split_words(enumerator[3:])
    return split_words(enumerator)


_DOCK_SIDES = (
    ("LeftDockWidgetArea", "Left"),
    ("RightDockWidgetArea", "Right"),
    ("TopDockWidgetArea", "Top"),
    ("BottomDockWidgetArea", "Bottom"),
)


def dock_area_summary(names: Sequence[str]) -> str:
    """Allowed sides. All four read "All sides"; otherwise "Left, Right"."""
    chosen = set(names)
    if not chosen or chosen == {"NoDockWidgetArea"}:
        return "None"
    sides = {name for name, _word in _DOCK_SIDES}
    if "AllDockWidgetAreas" in chosen or sides <= chosen:
        return "All sides"
    words = [word for name, word in _DOCK_SIDES if name in chosen]
    return ", ".join(words) if words else "None"


def radio_groups(type_name: str, names: Sequence[str]) -> Tuple[Tuple[str, ...], ...]:
    """Horizontal and vertical alignment exclude each other. Other flags do not."""
    if "Alignment" not in type_name:
        return ()
    present = set(names)
    groups = []
    horizontal = tuple(name for name in _HORIZONTAL if name in present)
    vertical = tuple(name for name in _VERTICAL if name in present)
    if len(horizontal) > 1:
        groups.append(horizontal)
    if len(vertical) > 1:
        groups.append(vertical)
    return tuple(groups)
