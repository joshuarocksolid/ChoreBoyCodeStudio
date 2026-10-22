"""Rename and delete participants (CONTRACTS.md section 3.6).

Modules in this package are discovered in sorted module-name order. Each
defines ``register(registry)``. A later work package adds its own module.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import FrozenSet, List, Optional, Protocol, Tuple

from app.features.form_builder.engine.commands.ops import Op
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument


class RenameParticipant(Protocol):
    participant_id: str

    def rename_ops(
        self,
        doc: UiDocument,
        renames: Tuple[Tuple[str, str], ...],
        scope: Optional[FrozenSet[NodeId]],
    ) -> Tuple[Op, ...]:
        """Ops for these renames, applied simultaneously. ``scope`` limits owners."""
        ...

    def references(self, doc: UiDocument, name: str) -> Tuple[Tuple[NodeId, str], ...]:
        """``(owner id, property name)`` pairs that mention ``name``."""
        ...


class DeleteParticipant(Protocol):
    participant_id: str

    def delete_ops(self, doc: UiDocument, removed_names: Tuple[str, ...]) -> Tuple[Op, ...]:
        """Extra ops for DeleteNodes. The default participants add none."""
        ...


class ParticipantRegistry:
    def __init__(self) -> None:
        self._rename: List[object] = []
        self._delete: List[object] = []

    def add_rename(self, participant: RenameParticipant) -> None:
        self._rename.append(participant)

    def add_delete(self, participant: DeleteParticipant) -> None:
        self._delete.append(participant)

    def all(self) -> Tuple[object, ...]:
        """Each participant once, sorted by ``participant_id``."""
        found: List[object] = []
        for item in self._rename + self._delete:
            if item not in found:
                found.append(item)
        found.sort(key=lambda item: str(getattr(item, "participant_id", "")))
        return tuple(found)


def load_participants(registry: ParticipantRegistry) -> None:
    """Import ``register`` from each sibling module, in module-name order."""
    package = __name__
    prefix = package + "."
    discovered = sorted(pkgutil.iter_modules(__path__), key=lambda item: item.name)
    for info in discovered:
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(prefix + info.name)
        register = getattr(module, "register", None)
        if register is not None:
            register(registry)


_DEFAULT: Optional[ParticipantRegistry] = None


def default_registry() -> ParticipantRegistry:
    """The process-wide registry. Built on first use so tests can add to it."""
    global _DEFAULT
    if _DEFAULT is None:
        registry = ParticipantRegistry()
        load_participants(registry)
        _DEFAULT = registry
    return _DEFAULT
