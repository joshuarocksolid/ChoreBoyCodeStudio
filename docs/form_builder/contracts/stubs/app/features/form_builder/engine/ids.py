"""Node identity (CONTRACTS.md section 2.1)."""

from __future__ import annotations

from typing import NewType

#: In-memory node identity. A positive int, unique within one FormSession for the
#: whole session (never reused, including after undo, redo and ReplaceDocument).
#: Never written to the .ui file, the generated module or the preview IPC.
NodeId = NewType("NodeId", int)

#: The ``<ui>`` document node itself. Form-level fields (author, class, tab stops,
#: connectslotsbyname...) are fields of this node.
DOCUMENT_ID = NodeId(0)


class IdAllocator:
    """Monotonic allocator owned by a FormSession.

    ``next_id`` starts at 1. The reader and every command allocate through the
    session's allocator, so ids are never reused. During replay the
    PlanContext replaces the allocator with ``ReplayAllocator`` (see
    ``engine.commands.base``).
    """

    def __init__(self, start: int = 1) -> None:
        ...

    def alloc(self) -> NodeId:
        """Return the next id and advance."""
        ...

    @property
    def high_water(self) -> int:
        """The next id that ``alloc`` would return."""
        ...
