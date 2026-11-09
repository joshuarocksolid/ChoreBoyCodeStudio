"""Inspector Data tab sections (CONTRACTS.md section 19.1).

A module here exposes ``register(registry)`` and adds a ``DataSection``.
Sections show for the selected widget's class, top to bottom by
``(order, section_id)``. A lane adds a file and edits no shared one.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from types import ModuleType
from typing import Callable, List, Optional, Tuple

from app.features.form_builder.engine.contributors import run_contributors
from app.qt.QtWidgets import QWidget


@dataclass(frozen=True)
class DataSection:
    section_id: str
    order: int
    create: Callable[[QWidget], QWidget]
    applies: Callable[[str], bool]


class SectionRegistry:
    def __init__(self) -> None:
        self._sections: List[Tuple[str, DataSection]] = []

    def add(self, section: DataSection) -> None:
        if any(found.section_id == section.section_id for _module, found in self._sections):
            raise ValueError("data section %s is already registered" % section.section_id)
        self._sections.append(("", section))

    def sections(self) -> Tuple[DataSection, ...]:
        return tuple(sorted((section for _module, section in self._sections), key=lambda item: (item.order, item.section_id)))


def load_sections(*packages: ModuleType) -> SectionRegistry:
    registry = SectionRegistry()
    found = packages or (sys.modules[__name__],)
    run_contributors("inspector data section", found, "register", lambda _module, hook: hook(registry))
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
    "DataSection",
    "SectionRegistry",
    "default_registry",
    "load_sections",
    "reset_default_registry",
]
