"""Locale-free number and boolean text (CONTRACTS.md section 8.3).

Every number-to-text conversion in the writer, codegen and IPC goes through
this module. Nothing here reads the locale, the clock or the hash seed.
"""

from __future__ import annotations


def format_int(value: int) -> str:
    """Decimal digits with a leading ``-`` for negatives. No grouping, no ``+``."""
    ...


def format_double(value: float) -> str:
    """Designer's text for ``<double>`` and double-valued attributes and children
    (gradient coordinates, rectf, sizef, pointf, stop positions): fixed notation
    with 15 fractional digits, ``format(value, ".15f")``. PROVISIONAL until
    M0.4b pins it, together with how ``-0`` is written (provisionally
    ``0.000000000000000``). If the corpus shows otherwise, only this changes."""
    ...


def format_float(value: float) -> str:
    """Designer's text for ``<float>``: likely 8 fractional digits. PROVISIONAL
    until M0.4b pins it."""
    ...


def format_real(value: float, *, element: str = "double") -> str:
    """``format_float`` for element ``float``, ``format_double`` otherwise."""
    ...


def parse_real(text: str) -> float:
    """``float(text.strip())`` restricted to the XML Schema double lexical space
    plus ``inf``/``-inf``/``nan`` spelled as Qt writes them. ValueError otherwise."""
    ...


def format_bool(value: bool) -> str:
    """``true`` / ``false``."""
    ...


def real_round_trips(value: float, *, element: str = "double") -> bool:
    """True when ``parse_real(format_real(value, element=element)) == value``. A value read from a
    file that does not round-trip is kept as OpaqueValue (FB005)."""
    ...


def format_python_float(value: float) -> str:
    """Codegen spelling of a float literal: ``repr(value)`` (shortest round-trip,
    locale-free), matching what ``uic -g python`` writes for doubles."""
    ...
