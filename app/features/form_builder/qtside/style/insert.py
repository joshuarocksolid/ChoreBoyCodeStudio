"""Text for the drawer's Insert menu (UX-STYLE-006). Qt-free helpers, then the small dialogs.

Each helper returns the text to put at the caret. The drawer inserts it,
replacing the selection; with the caret inside a colour value, the Colour
helper replaces that value.
"""

from __future__ import annotations

from typing import Optional, Tuple

from app.features.form_builder.engine.style.tokenizer import HASH, tokenize

_COLOUR_LENGTHS = (4, 7, 9)


def colour_span_at(text: str, position: int) -> Optional[Tuple[int, int]]:
    """The ``[start, end)`` of a ``#hex`` colour the caret touches, or None."""
    tokens, _problems = tokenize(text)
    for token in tokens:
        if token.kind == HASH and token.start <= position <= token.end and len(token.text) in _COLOUR_LENGTHS:
            body = token.text[1:]
            if all(ch in "0123456789abcdefABCDEF" for ch in body):
                return (token.start, token.end)
    return None


def gradient_text(first: str, second: str, *, vertical: bool = True) -> str:
    """``qlineargradient(...)`` from the top (or left) colour to the bottom (or right) one."""
    end = "x2:0, y2:1" if vertical else "x2:1, y2:0"
    return "qlineargradient(x1:0, y1:0, %s, stop:0 %s, stop:1 %s)" % (end, first, second)


def font_text(family: str, points: int, *, bold: bool = False, italic: bool = False) -> str:
    """``font: bold 12pt "Sans Serif";``"""
    parts = []
    if italic:
        parts.append("italic")
    if bold:
        parts.append("bold")
    parts.append("%dpt" % points)
    parts.append('"%s"' % family.replace('"', ""))
    return "font: %s;" % " ".join(parts)


def picture_text(stored: str) -> str:
    """``url(:/pictures/logo.png)`` for a resource path or a file path."""
    return "url(%s)" % stored.replace(")", "%29")


def rule_text(name: str) -> Tuple[str, int]:
    """The rule for a widget and the caret's offset in it: on the empty middle line."""
    head = "#%s {\n" % name
    return head + "    \n}", len(head) + 4
