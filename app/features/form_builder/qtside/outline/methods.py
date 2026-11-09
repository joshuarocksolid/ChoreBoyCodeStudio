"""Window methods a widget name must not replace.

``dir(QWidget)`` also lists ``layout`` and ``parent``. Those are legal object
names, so the refusal set stays the seven methods from the form logic design.
"""

from __future__ import annotations

from typing import FrozenSet

WINDOW_METHODS = frozenset({"close", "show", "update", "accept", "reject", "done", "print"})


def window_methods(root_class: str) -> FrozenSet[str]:
    del root_class
    return WINDOW_METHODS
