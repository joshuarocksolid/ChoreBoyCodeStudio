"""Locale-free number and boolean text (CONTRACTS.md section 8.3).

Every number-to-text conversion in the writer, codegen and IPC goes through
this module. Nothing here reads the locale, the clock or the hash seed.
"""

from __future__ import annotations

import math
import re

_REAL_RE = re.compile(
    r"[+-]?(?:(?:[0-9]+(?:\.[0-9]*)?)|(?:\.[0-9]+))(?:[eE][+-]?[0-9]+)?\Z"
)
_INF_RE = re.compile(r"[+-]?(?:inf|infinity)\Z", re.IGNORECASE)
_NAN_RE = re.compile(r"[+-]?nan\Z", re.IGNORECASE)


def format_int(value: int) -> str:
    """Decimal digits with a leading ``-`` for negatives. No grouping, no ``+``."""
    return str(value)


def format_real(value: float) -> str:
    """Designer's text for ``<double>``/``<float>`` and double-valued attributes
    and children (gradient coordinates, rectf, sizef, pointf, stop positions):
    fixed notation with 15 fractional digits, ``format(value, ".15f")``, with
    ``-0`` written as ``0.000000000000000``. The M0.4b corpus confirms this
    form; if it shows otherwise, only this function changes."""
    if value == 0.0:
        # IEEE -0 compares equal to 0. Writer output must not carry the sign.
        return "0.000000000000000"
    return format(value, ".15f")


def parse_real(text: str) -> float:
    """``float(text.strip())`` restricted to the XML Schema double lexical space
    plus ``inf``/``-inf``/``nan`` spelled as Qt writes them. ValueError otherwise."""
    stripped = text.strip()
    if _REAL_RE.match(stripped) or _INF_RE.match(stripped) or _NAN_RE.match(stripped):
        return float(stripped)
    raise ValueError("not a real: %r" % (text,))


def format_bool(value: bool) -> str:
    """``true`` / ``false``."""
    if value:
        return "true"
    return "false"


def real_round_trips(value: float) -> bool:
    """True when ``parse_real(format_real(value)) == value``. A value read from a
    file that does not round-trip is kept as OpaqueValue (FB005)."""
    if math.isnan(value) or math.isinf(value):
        return False
    try:
        return parse_real(format_real(value)) == value
    except ValueError:
        return False


def format_python_float(value: float) -> str:
    """Codegen spelling of a float literal: ``repr(value)`` (shortest round-trip,
    locale-free), matching what ``uic -g python`` writes for doubles."""
    return repr(value)
