"""Applies one entry's ops and records the inverse (CONTRACTS.md section 3.3).

Freshness is checked here, on the way forward. ``mutate``, undo and redo do
not check it: undo puts old ids back, and redo repeats ids allocated earlier.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.commands.base import Command, CommandRejected
from app.features.form_builder.engine.commands.ops import InsertNodeOp, Op, RemoveNodeOp, ReplaceRootOp
from app.features.form_builder.engine.events import Change, DocumentReplaced, NodeRemoved, change_from_op
from app.features.form_builder.engine.ids import DOCUMENT_ID, NodeId
from app.features.form_builder.engine.ui4 import mutate
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.mutate import OpError


class ApplyContext:
    """The ``PlanContext`` for one entry, or for one open transaction."""

    def __init__(
        self,
        doc: UiDocument,
        allocator: Any,
        participants: Tuple[object, ...],
        *,
        check_freshness: bool,
    ) -> None:
        self.doc = doc
        self._allocator = allocator
        self._participants = participants
        self._check_freshness = check_freshness
        self.ops: List[Op] = []
        self.inverses: List[Op] = []
        self.changes: List[Change] = []
        self.allocated: List[NodeId] = []
        self.commands: List[Command] = []
        self._fresh: set = set()
        self._removed: set = set()
        self.selection_before: Any = None
        self.selection_ids: Optional[Tuple[NodeId, ...]] = None
        self.selection_current: Optional[NodeId] = None
        self.chose_selection = False

    @property
    def classes(self) -> QtClassTable:
        return QtClassTable.shared()

    def alloc(self) -> NodeId:
        node_id = self._allocator.alloc()
        self.allocated.append(node_id)
        self._fresh.add(node_id)
        return node_id

    def do(self, op: Op) -> None:
        """Apply ``op`` now. A failed precondition becomes ``CommandRejected``."""
        self._guard(op)
        change = change_from_op(self.doc, op)
        try:
            inverse = mutate.apply(self.doc, op)
        except OpError as exc:
            raise CommandRejected(str(exc)) from exc
        self.ops.append(op)
        self.inverses.append(inverse)
        self.changes.append(change)
        self._remember_removal(op)

    def run(self, command: Command) -> Any:
        # The parent command is what replay re-runs. It calls ``run`` again.
        return command.apply(self.doc, self)

    def select(self, ids: Sequence[NodeId], current: Optional[NodeId] = None) -> None:
        self.selection_ids = tuple(ids)
        self.selection_current = current
        self.chose_selection = True

    def participants(self) -> Tuple[object, ...]:
        return self._participants

    def _guard(self, op: Op) -> None:
        inserted = _inserted_ids(op)
        if inserted:
            if self._check_freshness:
                for node_id in inserted:
                    if node_id not in self._fresh:
                        raise CommandRejected("That id was not allocated for this edit.")
            for node_id in inserted:
                if node_id in self._removed:
                    raise CommandRejected("An id removed in this edit cannot be inserted again.")

    def forget_tail(self, start: int, alloc_start: int) -> None:
        """Drop ops and ids rolled back after ``start`` / ``alloc_start``."""
        del self.ops[start:]
        del self.inverses[start:]
        del self.changes[start:]
        for node_id in self.allocated[alloc_start:]:
            self._fresh.discard(node_id)
        del self.allocated[alloc_start:]
        self._removed.clear()
        for change in self.changes:
            if isinstance(change, NodeRemoved):
                self._removed.update(change.subtree)
            elif isinstance(change, DocumentReplaced):
                self._removed.update(change.removed)

    def _remember_removal(self, op: Op) -> None:
        if isinstance(op, RemoveNodeOp):
            change = self.changes[-1]
            subtree = getattr(change, "subtree", ())
            for node_id in subtree:
                self._removed.add(node_id)
        elif isinstance(op, ReplaceRootOp):
            change = self.changes[-1]
            removed = getattr(change, "removed", ())
            for node_id in removed:
                self._removed.add(node_id)


def _inserted_ids(op: Op) -> Tuple[NodeId, ...]:
    if isinstance(op, InsertNodeOp):
        return op.spec.ids()
    if isinstance(op, ReplaceRootOp):
        return tuple(node_id for node_id in op.spec.ids() if node_id != DOCUMENT_ID)
    return ()
