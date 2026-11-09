"""Left-pane Data sections (CONTRACTS.md section 19.1).

Same discovery rule as the inspector Data sections. M8.0s registers only the
empty state.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable, List, Optional, Tuple

from app.features.form_builder.engine.contributors import run_contributors
from app.qt.QtWidgets import QWidget


@dataclass(frozen=True)
class PanelSection:
    section_id: str
    order: int
    create: Callable[[Any], QWidget]
    applies: Callable[[Any], bool]


class SectionRegistry:
    def __init__(self) -> None:
        self._sections: List[PanelSection] = []

    def add(self, section: PanelSection) -> None:
        if any(found.section_id == section.section_id for found in self._sections):
            raise ValueError("data panel section %s is already registered" % section.section_id)
        self._sections.append(section)

    def sections(self) -> Tuple[PanelSection, ...]:
        return tuple(sorted(self._sections, key=lambda item: (item.order, item.section_id)))


def load_sections(*packages: ModuleType) -> SectionRegistry:
    registry = SectionRegistry()
    found = packages or (sys.modules[__name__],)
    run_contributors("data panel section", found, "register", lambda _module, hook: hook(registry))
    return registry


_DEFAULT: Optional[SectionRegistry] = None


def default_registry() -> SectionRegistry:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_sections()
    return _DEFAULT


def reset_default_registry() -> None:
    global _DEFAULT
    _DEFAULT = None


__all__ = [
    "PanelSection",
    "SectionRegistry",
    "default_registry",
    "load_sections",
    "reset_default_registry",
]
