"""Colours in style sheet text. Qt-free."""

from __future__ import annotations

import re
from typing import Optional, Tuple

Rgb = Tuple[int, int, int]

_HEX = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_FUNC = re.compile(r"^rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)$", re.IGNORECASE)
_NAMED = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "red": (255, 0, 0),
    "green": (0, 128, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
    "orange": (255, 165, 0),
    "purple": (128, 0, 128),
    "transparent": None,
}


def parse_color(text: str) -> Optional[Rgb]:
    """``#RGB``, ``#RRGGBB``, ``rgb(r, g, b)`` or a basic name; None for anything else."""
    body = text.strip().rstrip(";").strip()
    found = _HEX.match(body)
    if found:
        digits = found.group(1)
        if len(digits) == 3:
            digits = "".join(ch * 2 for ch in digits)
        return (int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))
    func = _FUNC.match(body)
    if func:
        red, green, blue = (int(func.group(i)) for i in (1, 2, 3))
        if max(red, green, blue) <= 255:
            return (red, green, blue)
        return None
    named = _NAMED.get(body.lower())
    return named


def hex_text(red: int, green: int, blue: int) -> str:
    return "#%02X%02X%02X" % (red, green, blue)
