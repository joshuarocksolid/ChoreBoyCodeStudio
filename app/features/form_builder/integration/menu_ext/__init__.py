"""Context-menu contributors (UX-CONT-020).

Modules in this package are discovered in sorted name order. Each one exposes
``register(registry)`` and adds rows or a submenu with ``registry.add(group,
build)``. A module whose name starts with an underscore is a helper and is not
imported. Contributors never edit ``surface.py`` or ``context_menu.py``.

Groups, top to bottom: ``first`` (above the clipboard rows), ``structure``
(above Change to and Remove layout), ``last``. Within a group, rows keep the
order in which the modules registered them.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from dataclasses import dataclass, field
from types import ModuleType
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.ids import NodeId

if TYPE_CHECKING:
    from app.features.form_builder.engine.session import FormSession
    from app.qt.QtWidgets import QMenu

FIRST = "first"
STRUCTURE = "structure"
LAST = "last"
GROUPS: Tuple[str, ...] = (FIRST, STRUCTURE, LAST)


@dataclass(frozen=True)
class MenuContext:
    """What a contributor gets for the menu being built."""

    menu: "QMenu"
    ids: Tuple[NodeId, ...]
    current: Optional[NodeId]
    session: "FormSession"
    dispatch: Callable[[str], None]


Build = Callable[[MenuContext], None]


@dataclass
class MenuRegistry:
    """Contributors by group, in registration order."""

    _builds: Dict[str, List[Tuple[str, Build]]] = field(default_factory=lambda: {group: [] for group in GROUPS})

    def add(self, group: str, build: Build, *, module: str = "") -> None:
        if group not in GROUPS:
            raise ValueError("unknown menu group %r; use one of %s" % (group, ", ".join(GROUPS)))
        self._builds[group].append((module, build))

    def scope(self, module: str) -> "_ModuleScope":
        return _ModuleScope(self, module)

    def contributors(self, group: str) -> Tuple[Build, ...]:
        return tuple(build for _module, build in self._builds[group])

    def run(self, group: str, context: MenuContext) -> int:
        """Run every contributor of ``group``. Returns how many ran."""
        builds = self.contributors(group)
        for build in builds:
            build(context)
        return len(builds)


class _ModuleScope:
    def __init__(self, registry: MenuRegistry, module: str) -> None:
        self._registry = registry
        self._module = module

    def add(self, group: str, build: Build) -> None:
        self._registry.add(group, build, module=self._module)


def load_menu_contributors(*packages: ModuleType) -> MenuRegistry:
    """Import each public module of ``packages`` in sorted name order and call its ``register``."""
    registry = MenuRegistry()
    for package in packages:
        for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda item: item.name):
            if info.name.startswith("_"):
                continue
            module = importlib.import_module("%s.%s" % (package.__name__, info.name))
            register = getattr(module, "register", None)
            if not callable(register):
                continue
            register(registry.scope(module.__name__))
    return registry


_DEFAULT: Optional[MenuRegistry] = None


def default_registry() -> MenuRegistry:
    """The registry of this package's contributors, loaded once."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_menu_contributors(sys.modules[__name__])
    return _DEFAULT


__all__: Sequence[str] = [
    "FIRST",
    "GROUPS",
    "LAST",
    "MenuContext",
    "MenuRegistry",
    "STRUCTURE",
    "default_registry",
    "load_menu_contributors",
]
