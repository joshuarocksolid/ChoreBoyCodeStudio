"""The shared selection model (CONTRACTS.md section 6).

One per FormSession. Canvas, outline and inspector all read and write this
object; none of them keeps its own selection. Selection is not undoable by
itself, but every log entry snapshots it so undo/redo restore it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.events import ChangeSet, NodeRemoved
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument


class SelectionSource(str, Enum):
    CANVAS = "canvas"
    OUTLINE = "outline"
    INSPECTOR = "inspector"
    COMMAND = "command"
    UNDO = "undo"
    PRUNE = "prune"
    PROGRAM = "program"


@dataclass(frozen=True)
class SelectionState:
    """``ids``: selected nodes in selection order, no duplicates, all present.

    ``current`` is None exactly when ``ids`` is empty, and otherwise a member
    of ``ids``. Empty selection means the inspector shows the form.
    """

    ids: Tuple[NodeId, ...] = ()
    current: Optional[NodeId] = None


@dataclass(frozen=True)
class SelectionChange:
    before: SelectionState
    after: SelectionState
    source: SelectionSource


class SelectionModel:
    def __init__(self, doc: UiDocument) -> None:
        self._doc = doc
        self._state = SelectionState()
        self._listeners: List[Callable[[SelectionChange], None]] = []
        self._pending: Optional[SelectionChange] = None
        self._holding = False

    @property
    def state(self) -> SelectionState:
        return self._state

    def set(
        self,
        ids: Sequence[NodeId],
        *,
        current: Optional[NodeId] = None,
        source: SelectionSource,
    ) -> None:
        """Replace the selection. Unknown ids are dropped.

        ``current`` defaults to the last remaining id. Outside a ChangeSet
        dispatch, listeners run immediately.
        """
        chosen: List[NodeId] = []
        seen = set()
        for node_id in ids:
            if node_id in seen or not self._doc.contains(node_id):
                continue
            seen.add(node_id)
            chosen.append(node_id)
        self._commit(tuple(chosen), current, source)

    def toggle(self, node_id: NodeId, *, source: SelectionSource) -> None:
        """Add ``node_id``, or remove it. Removing ``current`` makes the last id current."""
        if not self._doc.contains(node_id):
            return
        ids = list(self._state.ids)
        if node_id in ids:
            ids.remove(node_id)
            current = self._state.current
            if current == node_id:
                current = ids[-1] if ids else None
            self._commit(tuple(ids), current, source)
            return
        ids.append(node_id)
        self._commit(tuple(ids), node_id, source)

    def clear(self, *, source: SelectionSource) -> None:
        self._commit((), None, source)

    def apply_changeset(self, changeset: ChangeSet, restore: Optional[SelectionState]) -> None:
        """Update state at PRIORITY_SELECTION. Listeners wait for ``release``.

        A restore snapshot (do/redo ``selection_after``, undo ``selection_before``)
        is filtered to ids still in the document. With no snapshot, removed ids
        are pruned. If ``current`` was removed, it moves to the nearest surviving
        ancestor that this ChangeSet marked structure-dirty.
        """
        self._holding = True
        if restore is not None:
            source = SelectionSource.UNDO if changeset.origin in ("undo", "redo") else SelectionSource.COMMAND
            self.set(restore.ids, current=restore.current, source=source)
            return
        kept = tuple(
            node_id
            for node_id in self._state.ids
            if node_id not in changeset.removed and self._doc.contains(node_id)
        )
        current = self._state.current
        if current not in kept:
            current = self._surviving_ancestor(current, changeset)
            if current is not None and current not in kept:
                kept = kept + (current,)
        self._commit(kept, current, SelectionSource.PRUNE)

    def release(self) -> None:
        """Notify subscribers once, after later log listeners have run."""
        self._holding = False
        pending = self._pending
        self._pending = None
        if pending is not None:
            self._emit(pending)

    def subscribe(self, listener: Callable[[SelectionChange], None]) -> Callable[[], None]:
        """Listeners run synchronously in subscription order."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                return

        return unsubscribe

    def _commit(
        self,
        ids: Tuple[NodeId, ...],
        current: Optional[NodeId],
        source: SelectionSource,
    ) -> None:
        if not ids:
            new = SelectionState()
        elif current not in ids:
            new = SelectionState(ids, ids[-1])
        else:
            new = SelectionState(ids, current)
        if new == self._state:
            return
        change = SelectionChange(self._state, new, source)
        self._state = new
        if self._holding:
            self._pending = change
            return
        self._emit(change)

    def _emit(self, change: SelectionChange) -> None:
        for listener in tuple(self._listeners):
            listener(change)

    def _surviving_ancestor(self, removed_id: Optional[NodeId], changeset: ChangeSet) -> Optional[NodeId]:
        if removed_id is None:
            return None
        parent = _removal_parent(changeset, removed_id)
        while parent is not None:
            if parent not in changeset.removed and self._doc.contains(parent):
                if parent in changeset.structure_dirty:
                    return parent
                node = self._doc.get(parent)
                parent = None if node is None else node.parent_id
                continue
            parent = _removal_parent(changeset, parent)
        return None


def _removal_parent(changeset: ChangeSet, node_id: NodeId) -> Optional[NodeId]:
    """Parent recorded on the NodeRemoved that names ``node_id``."""
    fallback: Optional[NodeId] = None
    for change in changeset.changes:
        if not isinstance(change, NodeRemoved) or node_id not in change.subtree:
            continue
        if change.node == node_id:
            return change.parent
        if fallback is None:
            fallback = change.parent
    return fallback
