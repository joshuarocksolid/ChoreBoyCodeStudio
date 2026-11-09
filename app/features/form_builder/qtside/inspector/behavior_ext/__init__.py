"""Behavior tab sections (UX-BEH-001, CONTRACTS.md section 1.4, M6.0s).

The Behavior tab body is a stack of sections, each registered from its own
module here. Modules are discovered in sorted name order (a name starting with
``_`` is a helper and is not imported). A module exposes ``register(registry)``
and calls ``registry.add(BehaviorSection(...))``. A lane adds a section by adding
a file and edits no shared one.

A ``BehaviorSection`` has:

* ``section_id``: unique, e.g. ``"events"``.
* ``order``: sections show top to bottom by ``(order, section_id)``. The M6
  numbers are State 10 and Checks 20 (M7), Events 30, From other widgets 35,
  All events on this form 40, Your methods 50.
* ``applies(inputs) -> bool``: a pure predicate on the selection. A section for
  which it is False is hidden (Events always says True, UX-BEH-013).
* ``create(host) -> QWidget``: builds the section's widget, once, the first time
  it applies. The widget may define any of ``paint(inputs)`` (called on each
  refresh while the section shows), ``apply_colors(panel, text)``,
  ``set_refresh(callback)``, ``note_focus(widget)``, ``has_draft() -> bool`` and
  ``discard_draft() -> bool`` (Esc closes a half-made row). Missing ones are
  skipped.

The host (``qtside/inspector/_behavior.py``) owns the layout, the colors and the
order. A section whose predicate, builder or ``paint`` raises is logged and
hidden; the other sections still show. Until M6.1b registers the Events
section, the host shows the M3 Connections list (``_legacy_connections.py``)
in the Events slot (order 30).
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from types import ModuleType
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.contributors import run_contributors
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.qtside.inspector.model import BehaviorView
from app.qt.QtWidgets import QWidget

if TYPE_CHECKING:
    from app.features.form_builder.qtside.inspector._services import Services
    from app.features.form_builder.qtside.realize import Realizer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SectionInputs:
    """What a section may look at for the current selection. ``view`` is the inspector's own projection."""

    view: BehaviorView
    services: "Services"
    ids: Tuple[NodeId, ...] = ()

    @property
    def session(self) -> Any:
        return self.services.session

    @property
    def is_form(self) -> bool:
        """True when the form itself (the ``<ui>`` root) is the only thing selected."""
        document = self.session.document
        return len(self.ids) == 1 and self.ids[0] in (document.root.id, 0)


@dataclass(frozen=True)
class SectionHost:
    """What ``create`` gets: the services, the realizer and the parent for the new widget."""

    services: "Services"
    realizer: "Realizer"
    parent: QWidget


def _always(_inputs: SectionInputs) -> bool:
    return True


@dataclass(frozen=True)
class BehaviorSection:
    section_id: str
    order: int
    create: Callable[[SectionHost], QWidget]
    applies: Callable[[SectionInputs], bool] = _always

    def __post_init__(self) -> None:
        if not self.section_id:
            raise ValueError("a section needs an id")


class SectionRegistry:
    def __init__(self) -> None:
        self._sections: List[Tuple[str, BehaviorSection]] = []

    def add(self, section: BehaviorSection, *, module: str = "") -> None:
        if any(found.section_id == section.section_id for _module, found in self._sections):
            raise ValueError("behavior section %s is already registered" % section.section_id)
        self._sections.append((module, section))

    def scope(self, module: str) -> "_ModuleScope":
        return _ModuleScope(self, module)

    def sections(self) -> Tuple[BehaviorSection, ...]:
        """In display order: ``(order, section_id)``."""
        return tuple(sorted((section for _module, section in self._sections), key=lambda s: (s.order, s.section_id)))

    def get(self, section_id: str) -> Optional[BehaviorSection]:
        for _module, section in self._sections:
            if section.section_id == section_id:
                return section
        return None


class _ModuleScope:
    def __init__(self, registry: SectionRegistry, module: str) -> None:
        self._registry = registry
        self._module = module

    def add(self, section: BehaviorSection) -> None:
        self._registry.add(section, module=self._module)


def load_sections(*packages: ModuleType) -> SectionRegistry:
    registry = SectionRegistry()
    run_contributors("behavior section", packages, "register", lambda module, hook: hook(registry.scope(module.__name__)))
    return registry


_DEFAULT: Optional[SectionRegistry] = None


def default_registry() -> SectionRegistry:
    """This package's sections, loaded once."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_sections(sys.modules[__name__])
    return _DEFAULT


__all__: Sequence[str] = [
    "BehaviorSection",
    "SectionHost",
    "SectionInputs",
    "SectionRegistry",
    "default_registry",
    "load_sections",
]
