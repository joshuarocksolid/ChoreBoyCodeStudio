"""The shared selection model (CONTRACTS.md section 6).

One per FormSession. Canvas, outline and inspector all read and write this
object; none of them keeps its own selection. Selection is not undoable by
itself, but every log entry snapshots it so undo/redo restore it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, Sequence, Tuple

from app.features.form_builder.engine.events import ChangeSet
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument


class SelectionSource(str, Enum):
    CANVAS = "canvas"
    OUTLINE = "outline"
    INSPECTOR = "inspector"
    COMMAND = "command"    # ctx.select from a command
    UNDO = "undo"          # restored by undo/redo
    PRUNE = "prune"        # ids removed by a ChangeSet
    PROGRAM = "program"    # Problems navigation, search results, Try log clicks


@dataclass(frozen=True)
class SelectionState:
    """``ids``: selected nodes in selection order (first selected first), no
    duplicates, all present in the document. ``current``: the anchor the
    inspector shows and keyboard navigation starts from; None iff ``ids`` is
    empty; always a member of ``ids``. Empty selection means "the form" for the
    inspector (spike DESIGN: never empty)."""

    ids: Tuple[NodeId, ...] = ()
    current: Optional[NodeId] = None


@dataclass(frozen=True)
class SelectionChange:
    before: SelectionState
    after: SelectionState
    source: SelectionSource


class SelectionModel:
    def __init__(self, doc: UiDocument) -> None:
        ...

    @property
    def state(self) -> SelectionState:
        ...

    def set(self, ids: Sequence[NodeId], *, current: Optional[NodeId] = None, source: SelectionSource) -> None:
        """Replace the selection. Unknown ids are dropped silently (stale UI).
        ``current`` defaults to the last id. Emits only when the state changed."""
        ...

    def toggle(self, node_id: NodeId, *, source: SelectionSource) -> None:
        """Ctrl/Shift-click semantics. Removing ``current`` makes the last remaining
        id current."""
        ...

    def clear(self, *, source: SelectionSource) -> None:
        ...

    def apply_changeset(self, changeset: ChangeSet, restore: Optional[SelectionState]) -> None:
        """Called by FormSession at PRIORITY_SELECTION. When ``restore`` is given
        (the entry's selection_after on do/redo, selection_before on undo) it is
        applied, filtered to present ids. Otherwise removed ids are pruned; if
        ``current`` was removed, current becomes the nearest surviving ancestor of
        the removed node that was in the set's ``structure_dirty``, else None.
        Emits once with source COMMAND/UNDO/PRUNE."""
        ...

    def subscribe(self, listener: Callable[[SelectionChange], None]) -> Callable[[], None]:
        """Listeners run synchronously in subscription order. A listener must not
        move keyboard focus because of a change whose source is another view
        (CONTRACTS.md 6.3)."""
        ...
