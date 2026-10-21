"""The command log: the only writer of a document (CONTRACTS.md section 3).

One ``CommandLog`` per open form tab, owned by its ``FormSession``. It is not
thread-safe; all calls happen on the Qt GUI thread.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, ContextManager, Optional, Tuple

from app.features.form_builder.engine.commands.base import Command, CommandOutcome
from app.features.form_builder.engine.commands.ops import Op
from app.features.form_builder.engine.events import ChangeSet
from app.features.form_builder.engine.ids import IdAllocator, NodeId
from app.features.form_builder.engine.ui4.document import UiDocument

#: Entries kept for undo. When exceeded, the oldest entry is dropped; if the
#: save point was at or below it, the save point becomes unreachable.
DEFAULT_UNDO_LIMIT = 2000


@dataclass(frozen=True)
class SelectionSnapshot:
    ids: Tuple[NodeId, ...]
    current: Optional[NodeId]


@dataclass(frozen=True)
class Entry:
    """One undo step.

    ``commands``: the commands executed in it, in order (one, several merged, or a
    transaction's). ``ops``/``inverse_ops``: the applied ops and their inverses,
    same length, application order. ``allocated``: ids allocated, in order
    (replay seed). ``selection_before``/``selection_after``: restored by undo/redo.
    """

    label: str
    commands: Tuple[Command, ...]
    ops: Tuple[Op, ...]
    inverse_ops: Tuple[Op, ...]
    allocated: Tuple[NodeId, ...]
    selection_before: SelectionSnapshot
    selection_after: SelectionSnapshot
    merge_key: Optional[object] = None
    merge_token: Optional[str] = None


class Subscription:
    def close(self) -> None:
        """Idempotent."""
        ...


class CommandLog:
    def __init__(
        self,
        doc: UiDocument,
        allocator: IdAllocator,
        *,
        selection_provider: Callable[[], SelectionSnapshot],
        undo_limit: int = DEFAULT_UNDO_LIMIT,
    ) -> None:
        ...

    @property
    def document(self) -> UiDocument:
        ...

    # ----------------------------------------------------------- execution
    def execute(self, command: Command) -> CommandOutcome:
        """Apply ``command`` as one entry (or inside the open transaction).

        Steps: refuse when called from a listener (ReentrantCommandError); run
        ``command.apply``; on any exception roll back the ops applied so far,
        emit nothing and re-raise (CommandRejected passes through unchanged,
        any other exception is wrapped in CommandRejected with code FB999 after
        logging); if zero ops were applied return ``noop=True`` and push
        nothing; otherwise try to merge (rules below), else push a new entry,
        clear the redo stack, and emit one ChangeSet.

        Merge rules: merge into the top entry iff (a) not inside a transaction,
        (b) both have the same non-None ``merge_key()`` and the same non-None
        ``merge_token``, (c) the top entry is not the save point, (d) the redo
        stack is empty. A merged entry keeps the first entry's inverse ops and
        selection_before and appends the new ops. If after merging the entry's
        net effect is nil (every property/field back to its original value) the
        entry is popped; the ChangeSet is still emitted (the document changed
        back).
        """
        ...

    def transaction(self, label: str) -> ContextManager["Transaction"]:
        """Group commands into one entry. Nested transactions join the outermost.
        Exiting normally commits one entry and emits one ChangeSet; exiting by
        exception rolls back every op of the transaction, emits nothing and
        re-raises. A transaction with zero ops pushes nothing."""
        ...

    # --------------------------------------------------------- undo / redo
    def can_undo(self) -> bool:
        ...

    def can_redo(self) -> bool:
        ...

    def undo(self) -> bool:
        """Apply the top entry's inverse ops in reverse order; emit a ChangeSet with
        ``origin="undo"``; restore ``selection_before``. False when nothing to undo."""
        ...

    def redo(self) -> bool:
        """Re-apply the recorded ops (``apply`` is not re-run); emit ``origin="redo"``;
        restore ``selection_after``."""
        ...

    def undo_label(self) -> Optional[str]:
        ...

    def redo_label(self) -> Optional[str]:
        ...

    def entries(self) -> Tuple[Entry, ...]:
        """The applied entries (the undo stack), oldest first."""
        ...

    # ---------------------------------------------------------- save point
    def is_dirty(self) -> bool:
        """True unless the undo position equals the save point. Undoing past the
        save point and executing a new command makes the save point unreachable
        (dirty until the next ``mark_saved``)."""
        ...

    def mark_saved(self) -> None:
        ...

    # ------------------------------------------------------------- events
    def subscribe(self, listener: Callable[[ChangeSet], None], *, priority: int) -> Subscription:
        """Listeners run synchronously after each entry, undo and redo, in
        ascending priority (``engine.events.PRIORITY_*``), then subscription
        order. A listener exception is logged and does not stop later listeners
        or undo the entry. Listeners must not call execute/undo/redo
        (ReentrantCommandError); they may schedule work for later."""
        ...


class Transaction:
    def execute(self, command: Command) -> Any:
        """Same as ``CommandLog.execute`` inside the transaction; returns the result."""
        ...


def replay(initial_text: str, entries: Tuple[Entry, ...]) -> UiDocument:
    """Test helper and the replay contract: read ``initial_text`` with a fresh
    allocator, then for each entry re-run every command's ``apply`` with a replay
    allocator seeded from ``entry.allocated``; assert the produced op sequence
    equals ``entry.ops`` exactly; return the document. The result's
    ``fingerprint()`` must equal the live document's."""
    ...
