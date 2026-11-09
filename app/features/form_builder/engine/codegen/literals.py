"""Deterministic Python literals for generated modules.

String literals follow CONTRACTS.md section 9.3. The rule does not call ``repr``
and does not depend on a Python version's Unicode tables.
"""

from __future__ import annotations

import math


def py_string(text: str) -> str:
    """``u"..."`` with the contract's escape rule."""
    parts = ['u"']
    for char in text:
        code = ord(char)
        if char == "\\":
            parts.append("\\\\")
        elif char == '"':
            parts.append('\\"')
        elif char == "\n":
            parts.append("\\n")
        elif char == "\r":
            parts.append("\\r")
        elif char == "\t":
            parts.append("\\t")
        elif code < 0x20 or code == 0x7F:
            parts.append("\\x%02x" % code)
        elif 0xD800 <= code <= 0xDFFF:
            parts.append("\\u%04x" % code)
        else:
            parts.append(char)
    parts.append('"')
    return "".join(parts)


def py_float(value: float) -> str:
    """A Python float token that parses back to ``value`` on 3.9 and 3.11."""
    if math.isnan(value):
        return "float('nan')"
    if value == float("inf"):
        return "float('inf')"
    if value == float("-inf"):
        return "float('-inf')"
    if value == 0.0:
        return "0.0"
    text = format(value, ".16g")
    if float(text) != value:
        text = format(value, ".17g")
    if "e" not in text and "E" not in text and "." not in text:
        text += ".0"
    return text


def py_bytes(data: bytes) -> str:
    """A ``bytes`` literal. Printable ASCII is raw. Everything else is ``\\xNN``."""
    parts = ['b"']
    for byte in data:
        if byte == ord("\\"):
            parts.append("\\\\")
        elif byte == ord('"'):
            parts.append('\\"')
        elif byte == ord("\n"):
            parts.append("\\n")
        elif byte == ord("\r"):
            parts.append("\\r")
        elif byte == ord("\t"):
            parts.append("\\t")
        elif 32 <= byte < 127:
            parts.append(chr(byte))
        else:
            parts.append("\\x%02x" % byte)
    parts.append('"')
    return "".join(parts)
