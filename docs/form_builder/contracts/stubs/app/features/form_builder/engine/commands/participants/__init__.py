"""Rename and delete participants (CONTRACTS.md section 3.6).

Modules in this package are discovered in sorted module-name order; each
defines ``register(registry: ParticipantRegistry) -> None``. A WP adds its own
module (e.g. ``logic_references.py`` in M6.0b) and never edits another.
"""

from __future__ import annotations

from typing import Protocol, Tuple

from app.features.form_builder.engine.commands.ops import Op
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument


class RenameParticipant(Protocol):
    participant_id: str

    def rename_ops(self, doc: UiDocument, old: str, new: str) -> Tuple[Op, ...]:
        """Ops rewriting this participant's references from ``old`` to ``new``.
        Called after the name field has been changed. Must be a pure function of
        ``doc``; ops are applied by the Rename command in the same entry."""
        ...

    def references(self, doc: UiDocument, name: str) -> Tuple[Tuple[NodeId, str], ...]:
        """``(owner id, property name)`` pairs that reference ``name``; feeds
        "used by" before delete (LOGIC_DESIGN 2.13) and Shift+F12."""
        ...


class DeleteParticipant(Protocol):
    participant_id: str

    def delete_ops(self, doc: UiDocument, removed_names: Tuple[str, ...]) -> Tuple[Op, ...]:
        """Extra ops for DeleteNodes (default participants add none: logic
        references are kept and flagged)."""
        ...


class ParticipantRegistry:
    def add_rename(self, participant: RenameParticipant) -> None:
        ...

    def add_delete(self, participant: DeleteParticipant) -> None:
        ...

    def all(self) -> Tuple[object, ...]:
        """Sorted by ``participant_id``."""
        ...
