"""The Command protocol (CONTRACTS.md section 3.1-3.2).

A command is a frozen dataclass of plain parameters. Executing it runs
``apply(doc, ctx)``, which reads the document and calls ``ctx.do(op)`` for each
primitive change (each op is applied immediately, so later reads see it). The
log records the ops. Redo re-applies the recorded ops; it never re-runs
``apply``. Replay re-runs ``apply`` with a replay allocator and must produce the
identical op sequence.

Anything measured from Qt (rects, size hints, the visual order of a grid) enters
a command as a parameter, never by calling Qt from ``apply``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Hashable, Optional, Protocol, Sequence, Tuple

from app.features.form_builder.engine.commands.ops import Op
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument


class CommandRejected(Exception):
    """``apply`` refused the command (stale ids, illegal target, nothing to do
    when ``strict``). Raised before or after some ``ctx.do`` calls; the log rolls
    back every op of the entry (or of the whole transaction) and emits nothing.

    ``code``: optional FB code when the rejection is user-meaningful (shown as a
    status message, never as a Problems row). ``message`` is plain words.
    """

    def __init__(self, message: str, code: Optional[str] = None) -> None:
        ...


class ReentrantCommandError(RuntimeError):
    """A change listener tried to execute, undo or redo synchronously."""


class PlanContext(Protocol):
    """What ``Command.apply`` may use."""

    @property
    def classes(self) -> QtClassTable:
        ...

    def do(self, op: Op) -> None:
        """Apply ``op`` now and record it (and its inverse)."""
        ...

    def alloc(self) -> NodeId:
        """A fresh id. During replay, returns the ids the original run allocated,
        in order; asking for more than were recorded raises AssertionError."""
        ...

    def run(self, command: "Command") -> Any:
        """Apply a sub-command inside the same entry; returns its result."""
        ...

    def select(self, ids: Sequence[NodeId], current: Optional[NodeId] = None) -> None:
        """Selection after the entry (default: unchanged, minus removed ids)."""
        ...

    def participants(self) -> "Tuple[object, ...]":
        """Registered RenameParticipant/DeleteParticipant objects
        (``engine.commands.participants``), sorted by module name."""
        ...


class Command(Protocol):
    """Every command class is a ``@dataclass(frozen=True)`` with JSON-able fields
    (ints, strs, bools, None, tuples, frozen values, NodeSpecs, Placements) and:

    * ``command_type``: unique, stable string; the registry key for traces.
    * ``label``: plain-word undo text (``"Move okButton"``).
    * ``merge_key()``: a hashable key or None (see ``CommandLog`` merge rules).
    * ``merge_token``: the UI gesture token, or None.
    * ``apply``: as described above; returns an optional result (created ids...).
    """

    command_type: ClassVar[str]

    @property
    def label(self) -> str:
        ...

    @property
    def merge_token(self) -> Optional[str]:
        ...

    def merge_key(self) -> Optional[Hashable]:
        ...

    def apply(self, doc: UiDocument, ctx: PlanContext) -> Any:
        ...


@dataclass(frozen=True)
class CommandOutcome:
    """Returned by ``CommandLog.execute``.

    ``merged``: the command was merged into the previous entry.
    ``noop``: it applied zero ops (no entry was pushed, no ChangeSet emitted).
    """

    result: Any
    revision: int
    merged: bool = False
    noop: bool = False
