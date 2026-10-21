"""Rename and delete participants (CONTRACTS.md section 3.6).

Modules in this package are discovered in sorted module-name order; each
defines ``register(registry: ParticipantRegistry) -> None``. A WP adds its own
module (e.g. ``logic_references.py`` in M6.0b) and never edits another.
"""

from __future__ import annotations

from typing import FrozenSet, Optional, Protocol, Tuple

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
        """Ops rewriting this participant's references for every ``(old, new)`` in
        ``renames``, applied SIMULTANEOUSLY (no chaining). ``scope`` limits the
        rewrite to owners in the set (InsertFragment passes the inserted
        subtree); None means the whole document (Rename). Called after the name
        fields have been changed. Pure function of ``doc``; the calling command
        applies the ops in the same entry. Names shared by several nodes (FB010)
        are never passed (Rename skips reference rewriting for them)."""
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
