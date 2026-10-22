"""The command log: the only writer of a document (CONTRACTS.md section 3).

One log per open form tab. It is not thread-safe. Callers use the Qt GUI thread.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, ContextManager, Iterator, List, Optional, Tuple

from app.features.form_builder.engine.commands.base import (
    Command,
    CommandOutcome,
    CommandRejected,
    ReentrantCommandError,
    ReplayAllocator,
)
from app.features.form_builder.engine.commands.context import ApplyContext
from app.features.form_builder.engine.commands.ops import (
    InsertNodeOp,
    MoveNodeOp,
    Op,
    RemoveNodeOp,
    ReplaceRootOp,
    SetFieldOp,
    SetPropertyOp,
)
from app.features.form_builder.engine.commands.participants import default_registry
from app.features.form_builder.engine.events import (
    Change,
    ChangeSet,
    DocumentReplaced,
    NodeInserted,
    NodeRemoved,
    assemble,
    change_from_op,
)
from app.features.form_builder.engine.ids import IdAllocator, NodeId
from app.features.form_builder.engine.ui4 import mutate
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.values import semantic_equal

logger = logging.getLogger(__name__)

#: Entries kept for undo. Past this, the oldest entry is dropped. If that entry
#: was the save point, the save point becomes unreachable.
DEFAULT_UNDO_LIMIT = 2000


@dataclass(frozen=True)
class SelectionSnapshot:
    ids: Tuple[NodeId, ...]
    current: Optional[NodeId]


@dataclass(frozen=True)
class Entry:
    """One undo step. ``inverse_ops`` lines up with ``ops``, in application order."""

    label: str
    commands: Tuple[Command, ...]
    ops: Tuple[Op, ...]
    inverse_ops: Tuple[Op, ...]
    allocated: Tuple[NodeId, ...]
    selection_before: SelectionSnapshot
    selection_after: SelectionSnapshot
    merge_key: Optional[object] = None
    merge_token: Optional[str] = None
    #: Set by ``execute(..., continue_gesture=True)``. Later commands with the
    #: same token join this step whatever their merge key is.
    continue_gesture: bool = False


class Subscription:
    def __init__(self, log: "CommandLog", key: int) -> None:
        self._log = log
        self._key = key
        self._closed = False

    def close(self) -> None:
        """Idempotent."""
        if self._closed:
            return
        self._closed = True
        self._log._drop_listener(self._key)


class Transaction:
    def __init__(self, log: "CommandLog") -> None:
        self._log = log

    def execute(self, command: Command) -> Any:
        """Apply ``command`` inside the open transaction. Returns its result."""
        return self._log._execute_open(command)


class CommandLog:
    def __init__(
        self,
        doc: UiDocument,
        allocator: IdAllocator,
        *,
        selection_provider: Callable[[], SelectionSnapshot],
        undo_limit: int = DEFAULT_UNDO_LIMIT,
    ) -> None:
        self._doc = doc
        self._allocator = allocator
        self._provider = selection_provider
        self._limit = undo_limit
        self._undo: List[Entry] = []
        self._redo: List[Entry] = []
        self._tokens: List[int] = []
        self._redo_tokens: List[int] = []
        self._next_token = 1
        self._save_token: Optional[int] = 0
        self._listeners: List[Tuple[int, int, Callable[[ChangeSet], None]]] = []
        self._listener_seq = 0
        self._in_listener = False
        self._txn: Optional[_OpenTxn] = None
        self._txn_depth = 0
        self.selection = selection_provider()

    @property
    def document(self) -> UiDocument:
        return self._doc

    def execute(self, command: Command, *, continue_gesture: bool = False) -> CommandOutcome:
        """Apply ``command`` as one undo step, or inside the open transaction."""
        self._reject_reentry()
        if self._txn is not None:
            before_ops = len(self._txn.ctx.ops)
            result = self._execute_open(command)
            added = len(self._txn.ctx.ops) - before_ops
            return CommandOutcome(result, self._doc.revision, noop=added == 0)
        ctx = self._new_context()
        before = self._provider()
        ctx.selection_before = before
        result = self._apply(command, ctx)
        ctx.commands.append(command)
        if not ctx.ops:
            return CommandOutcome(result, self._doc.revision, noop=True)
        merged = self._store(ctx, before, command, continue_gesture)
        return CommandOutcome(result, self._doc.revision, merged=merged, noop=False)

    def transaction(self, label: str) -> ContextManager[Transaction]:
        """Group commands into one undo step. Nested transactions join this one."""
        return self._transaction(label)

    @contextmanager
    def _transaction(self, label: str) -> Iterator[Transaction]:
        self._reject_reentry()
        outermost = self._txn is None
        if outermost:
            ctx = self._new_context()
            ctx.selection_before = self._provider()
            self._txn = _OpenTxn(label, ctx)
        self._txn_depth += 1
        try:
            yield Transaction(self)
        except CommandRejected:
            self._txn_depth -= 1
            if outermost:
                self._abort_txn()
            raise
        except Exception as exc:
            self._txn_depth -= 1
            if outermost:
                self._abort_txn()
            logger.exception("form builder transaction failed")
            raise CommandRejected(
                "The edit could not be completed.",
                code="FB999",
                error=exc,
            ) from exc
        except BaseException:
            self._txn_depth -= 1
            if outermost:
                self._abort_txn()
            raise
        else:
            self._txn_depth -= 1
            if outermost:
                self._commit_txn()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> bool:
        """Apply the top step's inverses in reverse. False when the stack is empty."""
        self._reject_reentry()
        if not self._undo:
            return False
        entry = self._undo.pop()
        token = self._tokens.pop()
        changes = _apply_ops(self._doc, reversed(entry.inverse_ops))
        self._redo.append(entry)
        self._redo_tokens.append(token)
        self.selection = _present(self._doc, entry.selection_before)
        self._emit(assemble(changes, self._doc.revision, "undo", entry.label))
        return True

    def redo(self) -> bool:
        """Re-apply the recorded ops. ``apply`` is not re-run."""
        self._reject_reentry()
        if not self._redo:
            return False
        entry = self._redo.pop()
        token = self._redo_tokens.pop()
        changes = _apply_ops(self._doc, entry.ops)
        self._undo.append(entry)
        self._tokens.append(token)
        self._trim()
        self.selection = _present(self._doc, entry.selection_after)
        self._emit(assemble(changes, self._doc.revision, "redo", entry.label))
        return True

    def undo_label(self) -> Optional[str]:
        if not self._undo:
            return None
        return self._undo[-1].label

    def redo_label(self) -> Optional[str]:
        if not self._redo:
            return None
        return self._redo[-1].label

    def entries(self) -> Tuple[Entry, ...]:
        """Applied steps, oldest first."""
        return tuple(self._undo)

    def is_dirty(self) -> bool:
        """O(1). True unless the undo position is the save point."""
        if self._save_token is None:
            return True
        return self._tip_token() != self._save_token

    def mark_saved(self) -> None:
        self._save_token = self._tip_token()

    def subscribe(self, listener: Callable[[ChangeSet], None], *, priority: int) -> Subscription:
        """Run ``listener`` after each committed step, undo and redo."""
        self._listener_seq += 1
        key = self._listener_seq
        self._listeners.append((priority, key, listener))
        return Subscription(self, key)

    def _execute_open(self, command: Command) -> Any:
        txn = self._txn
        if txn is None:
            raise CommandRejected("There is no open transaction.")
        result = self._apply(command, txn.ctx)
        txn.ctx.commands.append(command)
        return result

    def _apply(self, command: Command, ctx: ApplyContext) -> Any:
        start = len(ctx.inverses)
        try:
            return command.apply(self._doc, ctx)
        except CommandRejected:
            self._rollback_from(ctx, start)
            raise
        except Exception as exc:
            self._rollback_from(ctx, start)
            logger.exception("form builder command failed")
            raise CommandRejected(
                "The edit could not be completed.",
                code="FB999",
                error=exc,
            ) from exc
        except BaseException:
            self._rollback_from(ctx, start)
            raise

    def _store(
        self,
        ctx: ApplyContext,
        before: SelectionSnapshot,
        command: Command,
        continue_gesture: bool,
    ) -> bool:
        after = _selection_after(self._doc, before, ctx)
        merged = self._can_merge(command)
        if merged:
            top = self._undo[-1]
            entry = Entry(
                label=top.label,
                commands=top.commands + tuple(ctx.commands),
                ops=top.ops + tuple(ctx.ops),
                inverse_ops=top.inverse_ops + tuple(ctx.inverses),
                allocated=top.allocated + tuple(ctx.allocated),
                selection_before=top.selection_before,
                selection_after=after,
                merge_key=command.merge_key() if command.merge_key() is not None else top.merge_key,
                merge_token=top.merge_token,
                continue_gesture=top.continue_gesture or continue_gesture,
            )
            self._undo[-1] = entry
        else:
            self._drop_redo()
            entry = Entry(
                label=command.label,
                commands=tuple(ctx.commands),
                ops=tuple(ctx.ops),
                inverse_ops=tuple(ctx.inverses),
                allocated=tuple(ctx.allocated),
                selection_before=before,
                selection_after=after,
                merge_key=command.merge_key(),
                merge_token=command.merge_token,
                continue_gesture=continue_gesture,
            )
            token = self._next_token
            self._next_token += 1
            self._undo.append(entry)
            self._tokens.append(token)
            self._trim()
        self.selection = after
        label = self._undo[-1].label if self._undo else command.label
        if self._undo and _is_net_nil(self._undo[-1], self._doc):
            popped = self._undo.pop()
            token = self._tokens.pop()
            if token == self._save_token:
                self._save_token = None
            label = popped.label
        self._emit(assemble(ctx.changes, self._doc.revision, "do", label))
        return merged

    def _can_merge(self, command: Command) -> bool:
        if self._txn is not None or self._redo or not self._undo:
            return False
        top = self._undo[-1]
        if self._save_token is not None and self._tokens[-1] == self._save_token:
            return False
        token = command.merge_token
        if token is None or token != top.merge_token:
            return False
        if top.continue_gesture:
            return True
        key = command.merge_key()
        return key is not None and key == top.merge_key

    def _commit_txn(self) -> None:
        txn = self._txn
        self._txn = None
        if txn is None or not txn.ctx.ops:
            return
        before = txn.ctx.selection_before
        if not isinstance(before, SelectionSnapshot):
            before = self._provider()
        after = _selection_after(self._doc, before, txn.ctx)
        self._drop_redo()
        entry = Entry(
            label=txn.label,
            commands=tuple(txn.ctx.commands),
            ops=tuple(txn.ctx.ops),
            inverse_ops=tuple(txn.ctx.inverses),
            allocated=tuple(txn.ctx.allocated),
            selection_before=before,
            selection_after=after,
            merge_key=None,
            merge_token=None,
            continue_gesture=False,
        )
        token = self._next_token
        self._next_token += 1
        self._undo.append(entry)
        self._tokens.append(token)
        self._trim()
        self.selection = after
        if _is_net_nil(entry, self._doc):
            self._undo.pop()
            dropped = self._tokens.pop()
            if dropped == self._save_token:
                self._save_token = None
        self._emit(assemble(txn.ctx.changes, self._doc.revision, "do", txn.label))

    def _abort_txn(self) -> None:
        txn = self._txn
        self._txn = None
        if txn is not None:
            self._rollback(txn.ctx)

    def _rollback(self, ctx: ApplyContext) -> None:
        self._rollback_from(ctx, 0)

    def _rollback_from(self, ctx: ApplyContext, start: int) -> None:
        for op in reversed(ctx.inverses[start:]):
            mutate.apply(self._doc, op)
        ctx.forget_tail(start)

    def _new_context(self) -> ApplyContext:
        return ApplyContext(
            self._doc,
            self._allocator,
            default_registry().all(),
            check_freshness=True,
        )

    def _drop_redo(self) -> None:
        if not self._redo:
            return
        self._redo.clear()
        self._redo_tokens.clear()
        if self._save_token not in (None, 0) and self._save_token not in self._tokens:
            self._save_token = None

    def _trim(self) -> None:
        while len(self._undo) > self._limit:
            token = self._tokens.pop(0)
            self._undo.pop(0)
            if token == self._save_token:
                self._save_token = None

    def _tip_token(self) -> int:
        if not self._tokens:
            return 0
        return self._tokens[-1]

    def _emit(self, change_set: ChangeSet) -> None:
        listeners = sorted(self._listeners, key=lambda item: (item[0], item[1]))
        self._in_listener = True
        try:
            for _priority, key, listener in listeners:
                if not any(item[1] == key for item in self._listeners):
                    continue
                try:
                    listener(change_set)
                except Exception:
                    logger.exception("form builder listener failed")
        finally:
            self._in_listener = False

    def _drop_listener(self, key: int) -> None:
        self._listeners = [item for item in self._listeners if item[1] != key]

    def _reject_reentry(self) -> None:
        if self._in_listener:
            raise ReentrantCommandError("A change listener cannot edit the form.")


@dataclass
class _OpenTxn:
    label: str
    ctx: ApplyContext


def replay(initial_text: str, entries: Tuple[Entry, ...]) -> UiDocument:
    """Re-run every command. The op sequence must match the recorded one."""
    doc = read_ui(initial_text, allocator=IdAllocator()).document
    for entry in entries:
        ctx = ApplyContext(
            doc,
            ReplayAllocator(entry.allocated),
            default_registry().all(),
            check_freshness=True,
        )
        for command in entry.commands:
            command.apply(doc, ctx)
        if tuple(ctx.ops) != tuple(entry.ops):
            raise AssertionError("replay produced a different op sequence")
    return doc


def _apply_ops(doc: UiDocument, ops: Any) -> Tuple[Change, ...]:
    changes = []
    for op in ops:
        changes.append(change_from_op(doc, op))
        mutate.apply(doc, op)
    return tuple(changes)


def _selection_after(
    doc: UiDocument,
    before: SelectionSnapshot,
    ctx: ApplyContext,
) -> SelectionSnapshot:
    if ctx.chose_selection and ctx.selection_ids is not None:
        return _present(doc, SelectionSnapshot(ctx.selection_ids, ctx.selection_current))
    removed = set()
    added = set()
    for change in ctx.changes:
        if isinstance(change, NodeRemoved):
            removed.update(change.subtree)
        elif isinstance(change, DocumentReplaced):
            removed.update(change.removed)
        elif isinstance(change, NodeInserted):
            added.update(change.subtree)
    gone = removed - added
    ids = tuple(node_id for node_id in before.ids if node_id not in gone and doc.contains(node_id))
    current = before.current if before.current in ids else None
    return SelectionSnapshot(ids, current)


def _present(doc: UiDocument, snapshot: SelectionSnapshot) -> SelectionSnapshot:
    ids = tuple(node_id for node_id in snapshot.ids if doc.contains(node_id))
    current = snapshot.current if snapshot.current in ids else None
    return SelectionSnapshot(ids, current)


def _is_net_nil(entry: Entry, doc: UiDocument) -> bool:
    """True when the step only edited properties or fields and each is back where it started."""
    for op in entry.ops:
        if isinstance(op, (InsertNodeOp, RemoveNodeOp, MoveNodeOp, ReplaceRootOp)):
            return False
    first_property = {}
    first_field = {}
    for inverse in entry.inverse_ops:
        if isinstance(inverse, SetPropertyOp):
            key = (inverse.owner, inverse.kind, inverse.name)
            if key not in first_property:
                first_property[key] = inverse
        elif isinstance(inverse, SetFieldOp):
            key = (inverse.node, inverse.field)
            if key not in first_field:
                first_field[key] = inverse
    for (owner, kind, name), inverse in first_property.items():
        node = doc.get(owner)
        if node is None:
            return False
        current = node.prop(name) if kind == "property" else node.attr(name)
        if not _same_property(current, inverse.entry):
            return False
    for (node_id, field_name), inverse in first_field.items():
        node = doc.get(node_id)
        if node is None or node.field(field_name) != inverse.value:
            return False
    return True


def _same_property(current: Any, restored: Any) -> bool:
    if current is None or restored is None:
        return current is restored
    return (
        current.stdset == restored.stdset
        and current.extra_attrs == restored.extra_attrs
        and semantic_equal(current.value, restored.value)
    )
