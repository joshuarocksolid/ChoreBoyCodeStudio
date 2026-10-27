"""One name check for the inline editor and ``Rename``.

Reserved names are decided before the identifier rule so ``form`` and ``True``
stay FB106, which is the sentence ``_check_name`` already raised.
"""

from __future__ import annotations

import keyword
from dataclasses import dataclass
from typing import FrozenSet, Optional

from app.features.form_builder.engine.commands.refs import FORMULA_NAMES, RESERVED_NAMES

_IDENTIFIER = "Names use letters, digits and _, and can't start with a digit."
_EMPTY = "A name can't be empty."
_RESERVED = "That name is reserved."
_KEYWORD = "%s is a Python word, so it can't be a name."


@dataclass(frozen=True)
class NameRefusal:
    code: str
    prose: str


def explain_name(
    name: str,
    taken: FrozenSet[str],
    base_methods: FrozenSet[str],
    current: str,
) -> Optional[NameRefusal]:
    """None when ``name`` may be committed. Keeping the widget's current name is allowed.

    An empty ``current`` means there is no name to keep, so ``""`` still fails,
    with its own sentence.
    """
    if current and name == current:
        return None
    if not name:
        return NameRefusal("FB011", _EMPTY)
    if name.startswith("cbcs") or name in RESERVED_NAMES or name in FORMULA_NAMES:
        return NameRefusal("FB106", _RESERVED)
    if keyword.iskeyword(name):
        return NameRefusal("FB011", _KEYWORD % name)
    if not name.isidentifier():
        return NameRefusal("FB011", _IDENTIFIER)
    if name in taken:
        return NameRefusal("FB010", "Another widget is already called %s." % name)
    if name in base_methods:
        suggestion = _suggestion(name, taken, base_methods, current)
        prose = "\u201c%s\u201d would replace a method of the window. Try %s." % (name, suggestion)
        return NameRefusal("FB204", prose)
    return None


def _suggestion(name: str, taken: FrozenSet[str], base_methods: FrozenSet[str], current: str) -> str:
    button = name + "Button"
    if explain_name(button, taken, base_methods, current) is None:
        return button
    return name + "Widget"
