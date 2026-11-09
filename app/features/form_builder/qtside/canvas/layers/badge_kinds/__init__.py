"""Logic-badge kinds. A module here adds a kind with ``register(registry)``.

Modules are discovered in sorted name order (a name starting with ``_`` is a
helper). The canvas paints the first kind that applies, by ``order``, and a
count only when more than one applies. A lane adds a file here and edits no
shared one.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from types import ModuleType
from typing import Callable, List, Optional, Tuple

from app.features.form_builder.engine.contributors import run_contributors


@dataclass(frozen=True)
class BadgeFacts:
    """What a kind reads. ``events`` is the sender's event list (empty when it has none)."""

    document: object
    sender: str
    events: Tuple[object, ...] = ()


@dataclass(frozen=True)
class BadgeKind:
    kind_id: str
    order: int
    glyph: str
    applies: Callable  # (node, facts) -> bool
    sentence: Callable  # (node, facts) -> str


class BadgeRegistry:
    def __init__(self) -> None:
        self._kinds: List[Tuple[str, BadgeKind]] = []

    def add(self, kind: BadgeKind, *, module: str = "") -> None:
        if any(found.kind_id == kind.kind_id for _module, found in self._kinds):
            raise ValueError("badge kind %s is already registered" % kind.kind_id)
        self._kinds.append((module, kind))

    def scope(self, module: str) -> "_ModuleScope":
        return _ModuleScope(self, module)

    def all(self) -> Tuple[BadgeKind, ...]:
        return tuple(kind for _module, kind in self._kinds)

    def ordered(self) -> Tuple[BadgeKind, ...]:
        return tuple(sorted(self.all(), key=lambda kind: (kind.order, kind.kind_id)))


class _ModuleScope:
    def __init__(self, registry: BadgeRegistry, module: str) -> None:
        self._registry = registry
        self._module = module

    def add(self, kind: BadgeKind) -> None:
        self._registry.add(kind, module=self._module)


def load_kinds(*packages: ModuleType) -> BadgeRegistry:
    registry = BadgeRegistry()
    run_contributors("badge kind", packages, "register", lambda module, hook: hook(registry.scope(module.__name__)))
    return registry


_DEFAULT: Optional[BadgeRegistry] = None


def default_registry() -> BadgeRegistry:
    """This package's kinds, loaded once."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_kinds(sys.modules[__name__])
    return _DEFAULT


__all__ = ["BadgeFacts", "BadgeKind", "BadgeRegistry", "default_registry", "load_kinds"]
