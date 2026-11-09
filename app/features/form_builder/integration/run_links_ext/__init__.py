"""Run-console links (CONTRACTS section 18.5). Qt-free.

A module in this package adds links with ``register(registry)``. Modules are
discovered in sorted name order (a name starting with ``_`` is a helper). No
product contributor ships here: an empty package loads nothing, and the console
draws no anchors until a lane adds a file. The first match wins.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from types import ModuleType
from typing import Callable, List, Optional, Tuple

from app.features.form_builder.engine.contributors import run_contributors


@dataclass(frozen=True)
class RunLink:
    match: Callable[[str], Optional[str]]  # target or None
    activate: Callable[[str], None]


class RunLinkRegistry:
    def __init__(self) -> None:
        self._links: List[Tuple[str, RunLink]] = []

    def add(self, link: RunLink, *, module: str = "") -> None:
        self._links.append((module, link))

    def scope(self, module: str) -> "_ModuleScope":
        return _ModuleScope(self, module)

    def all(self) -> Tuple[RunLink, ...]:
        return tuple(link for _module, link in self._links)


class _ModuleScope:
    def __init__(self, registry: RunLinkRegistry, module: str) -> None:
        self._registry = registry
        self._module = module

    def add(self, link: RunLink) -> None:
        self._registry.add(link, module=self._module)


def load_run_links(*packages: ModuleType) -> RunLinkRegistry:
    registry = RunLinkRegistry()
    run_contributors("run link", packages, "register", lambda module, hook: hook(registry.scope(module.__name__)))
    return registry


_DEFAULT: Optional[RunLinkRegistry] = None


def default_registry() -> RunLinkRegistry:
    """This package's links, loaded once. Empty until a lane adds a module."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_run_links(sys.modules[__name__])
    return _DEFAULT


def resolve_run_link(line: str) -> Optional[tuple]:
    """The first contributor that matches ``line``, as ``(link, target)``."""
    for link in default_registry().all():
        try:
            target = link.match(line)
        except Exception:
            continue
        if target:
            return (link, target)
    return None


def install_console_hook() -> None:
    """Point the shell Run Log at this registry.

    ``app.shell`` cannot import this package (dune file-role). The feature
    install should call this once. Until that call lands, a test calls it.
    """
    from app.shell.run_log_panel import set_run_link_resolver

    set_run_link_resolver(resolve_run_link)


__all__ = [
    "RunLink",
    "RunLinkRegistry",
    "default_registry",
    "install_console_hook",
    "load_run_links",
    "resolve_run_link",
]
