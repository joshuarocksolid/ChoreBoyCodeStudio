"""Canvas double-click contributors (UX D8, UX-CODE-018, CONTRACTS.md section 1.4, M6.0s).

A double-click on a widget goes to the contributors here before the canvas
looks for text to edit or items to open. A lane adds one by adding a module.
Modules are discovered in sorted name order (a name starting with ``_`` is a
helper and is not imported); each exposes ``register(registry)`` and calls
``registry.add(Activator(...))``.

An ``Activator`` has two functions:

* ``claims(doc, node_id) -> Optional[str]``: **pure and cheap** (the hover
  runs it on every pointer move). ``None`` means "not mine". Otherwise it
  returns the hover words, ``"double-click to write code"``, which the status
  bar appends to ``{object} · {friendly class} · click to select · ``.
* ``activate(surface, node_id)``: what the double-click does. It runs on the GUI
  thread with the form tab. The canvas has already selected the node.

The first contributor that claims a node wins (module order, then
registration order); the same one gets ``activate``. Only a double-click asks:
Enter never does, so Enter still edits a widget's text (UX-TEXT-001). A
contributor that raises is logged and skipped, so one lane's bug never takes
away the canvas's own double-click.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.contributors import run_contributors
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Activator:
    activator_id: str
    claims: Callable[[UiDocument, NodeId], Optional[str]]
    activate: Callable[[Any, NodeId], None]

    def __post_init__(self) -> None:
        if not self.activator_id:
            raise ValueError("an activator needs an id")


class ActivateRegistry:
    def __init__(self) -> None:
        self._entries: List[Tuple[str, Activator]] = []

    def add(self, activator: Activator, *, module: str = "") -> None:
        if any(found.activator_id == activator.activator_id for _module, found in self._entries):
            raise ValueError("activator %s is already registered" % activator.activator_id)
        self._entries.append((module, activator))

    def scope(self, module: str) -> "_ModuleScope":
        return _ModuleScope(self, module)

    def activators(self) -> Tuple[Activator, ...]:
        return tuple(activator for _module, activator in self._entries)

    def claim(self, document: UiDocument, node: NodeId) -> Optional[str]:
        """The hover words of the first activator that claims ``node``, else None."""
        found = self._claimant(document, node)
        return None if found is None else found[1]

    def activate(self, surface: Any, node: NodeId) -> bool:
        """Run the activator that claims ``node``. False when none does or it raised."""
        found = self._claimant(surface.session.document, node)
        if found is None:
            return False
        try:
            found[0].activate(surface, node)
        except Exception:
            logger.exception("activator %s failed", found[0].activator_id)
            return False
        return True

    def _claimant(self, document: UiDocument, node: NodeId) -> Optional[Tuple[Activator, str]]:
        for _module, activator in self._entries:
            try:
                words = activator.claims(document, node)
            except Exception:
                logger.exception("activator %s could not decide", activator.activator_id)
                continue
            if words is not None:
                return activator, words
        return None


class _ModuleScope:
    def __init__(self, registry: ActivateRegistry, module: str) -> None:
        self._registry = registry
        self._module = module

    def add(self, activator: Activator) -> None:
        self._registry.add(activator, module=self._module)


def load_activators(*packages: ModuleType) -> ActivateRegistry:
    registry = ActivateRegistry()
    run_contributors("activator", packages, "register", lambda module, hook: hook(registry.scope(module.__name__)))
    return registry


_DEFAULT: Optional[ActivateRegistry] = None


def default_registry() -> ActivateRegistry:
    """This package's activators, loaded once."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_activators(sys.modules[__name__])
    return _DEFAULT


__all__: Sequence[str] = [
    "ActivateRegistry",
    "Activator",
    "default_registry",
    "load_activators",
]
