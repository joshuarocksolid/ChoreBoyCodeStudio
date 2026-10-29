"""Workbench slot contributors (M5.0s, UX-MAIN-010, UX-STYLE-002, UX-PREV-004).

The workbench has three slots a lane fills from its own file:

* a **left-pane section** under Outline and Insert (the Actions section). It
  is declared here with ``slots.add_left_section(LeftSection(...))``.
* a **drawer under the canvas** (the style sheet drawer) and
* a **split beside the canvas** (View Python code).

The last two open on a gesture, so a lane gets the workbench through
``slots.on_workbench(callback)``, which runs once for every workbench built,
and calls ``workbench.open_under_canvas`` / ``open_beside_canvas`` later.

Modules in this package are discovered in sorted name order. Each one exposes
``register(slots)``. A module whose name starts with an underscore is a helper
and is not imported. Lanes never edit ``workbench.py``.

Order of left sections: ``(order, key)``. Outline is 10 and Insert is 20, so a
lane section uses 30 or more. Tabs at short heights and rail buttons follow
the same order.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.contributors import run_contributors

logger = logging.getLogger(__name__)

OUTLINE_ORDER = 10
INSERT_ORDER = 20


def _always(_session: Any) -> bool:
    return True


@dataclass(frozen=True)
class LeftSection:
    """A section of the left pane.

    ``build(workbench)`` returns the section's widget, once per workbench.
    ``shown(session)`` is asked after every change to the form and must be
    cheap; a section that is not shown takes no room, has no tab and no rail
    button. ``weight`` is its share, in percent, of the pane's height when the
    pane is split (Outline and Insert share the rest, 40 and 35 by default).
    ``keys`` is the key that focuses it (``"Alt+5"``). ``keys_ext`` turns it
    into the row ``form.action.focusSection.<key>`` ("Focus <title>"), which
    the form tab binds and Settings lists; the lane writes no key row. ``focus``
    receives the widget and defaults to ``widget.setFocus()``. ``glyph`` names
    a painted glyph for the rail button; empty shows the title's first letter.
    """

    key: str
    title: str
    build: Callable[[Any], Any]
    order: int = 30
    weight: int = 25
    shown: Callable[[Any], bool] = _always
    keys: str = ""
    focus: Optional[Callable[[Any], None]] = None
    glyph: str = ""

    def __post_init__(self) -> None:
        if not self.key or not self.title:
            raise ValueError("a left section needs a key and a title")
        if self.order <= INSERT_ORDER:
            raise ValueError("left section orders above %d are free; Outline and Insert use the rest" % INSERT_ORDER)
        if not 5 <= self.weight <= 60:
            raise ValueError("a left section takes 5 to 60 percent of the pane")


class WorkbenchSlots:
    """What lanes registered: left sections and workbench callbacks."""

    def __init__(self) -> None:
        self._sections: List[LeftSection] = []
        self._attachers: List[Tuple[str, Callable[[Any], None]]] = []

    def add_left_section(self, section: LeftSection) -> None:
        if any(other.key == section.key for other in self._sections):
            raise ValueError("left section %s is already registered" % section.key)
        self._sections.append(section)

    def on_workbench(self, callback: Callable[[Any], None], *, module: str = "") -> None:
        self._attachers.append((module, callback))

    def sections(self) -> Tuple[LeftSection, ...]:
        return tuple(sorted(self._sections, key=lambda found: (found.order, found.key)))

    def attach(self, workbench: Any) -> None:
        """Run every ``on_workbench`` callback. One that raises is logged and skipped."""
        for module, callback in self._attachers:
            try:
                callback(workbench)
            except Exception:
                logger.exception("workbench contributor %s failed", module or "?")


def load_workbench_contributors(*packages: ModuleType) -> WorkbenchSlots:
    slots = WorkbenchSlots()
    run_contributors("workbench", packages, "register", lambda _module, hook: hook(slots))
    return slots


_DEFAULT: Optional[WorkbenchSlots] = None


def default_slots() -> WorkbenchSlots:
    """The slots of this package's contributors, loaded once."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_workbench_contributors(sys.modules[__name__])
    return _DEFAULT


__all__: Sequence[str] = [
    "INSERT_ORDER",
    "LeftSection",
    "OUTLINE_ORDER",
    "WorkbenchSlots",
    "default_slots",
    "load_workbench_contributors",
]
