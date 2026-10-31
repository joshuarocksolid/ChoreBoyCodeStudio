"""Step-picker groups (CONTRACTS section 18.4). Qt-free.

A module in this package adds groups with ``register(registry)``. Modules are
discovered in sorted name order (a name starting with ``_`` is a helper). The
step page shows groups by ``order``. A lane adds a file here and edits no
shared one. ``page_signal`` is the event the page is building; group rows are
``(ctx) -> rows`` and read it, so the helpers can keep their ``(ctx, signal)``
signature.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from types import ModuleType
from typing import Callable, Iterator, List, Optional, Tuple

from app.features.form_builder.engine.contributors import run_contributors

_PAGE_SIGNAL: ContextVar[str] = ContextVar("cbcs_picker_page_signal", default="")


def page_signal() -> str:
    return _PAGE_SIGNAL.get()


@contextmanager
def bind_page_signal(signal: str) -> Iterator[None]:
    token = _PAGE_SIGNAL.set(signal or "")
    try:
        yield
    finally:
        _PAGE_SIGNAL.reset(token)


@dataclass(frozen=True)
class PickerGroup:
    group_id: str
    order: int
    title: str
    rows: Callable  # (ctx) -> sequence of Item, including the section header


class GroupRegistry:
    def __init__(self) -> None:
        self._groups: List[Tuple[str, PickerGroup]] = []

    def add(self, group: PickerGroup, *, module: str = "") -> None:
        if any(found.group_id == group.group_id for _module, found in self._groups):
            raise ValueError("picker group %s is already registered" % group.group_id)
        self._groups.append((module, group))

    def scope(self, module: str) -> "_ModuleScope":
        return _ModuleScope(self, module)

    def all(self) -> Tuple[PickerGroup, ...]:
        return tuple(group for _module, group in self._groups)

    def ordered(self) -> Tuple[PickerGroup, ...]:
        return tuple(sorted(self.all(), key=lambda group: (group.order, group.group_id)))


class _ModuleScope:
    def __init__(self, registry: GroupRegistry, module: str) -> None:
        self._registry = registry
        self._module = module

    def add(self, group: PickerGroup) -> None:
        self._registry.add(group, module=self._module)


def load_groups(*packages: ModuleType) -> GroupRegistry:
    registry = GroupRegistry()
    run_contributors(
        "picker group", packages, "register", lambda module, hook: hook(registry.scope(module.__name__))
    )
    return registry


_DEFAULT: Optional[GroupRegistry] = None


def default_registry() -> GroupRegistry:
    """This package's groups, loaded once."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_groups(sys.modules[__name__])
    return _DEFAULT


__all__ = [
    "GroupRegistry",
    "PickerGroup",
    "bind_page_signal",
    "default_registry",
    "load_groups",
    "page_signal",
]
