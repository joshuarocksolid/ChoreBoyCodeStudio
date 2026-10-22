"""The Command protocol (CONTRACTS.md section 3.1-3.2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Hashable, Optional, Protocol, Sequence, Tuple

from app.features.form_builder.engine.commands.ops import Op
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument


class CommandRejected(Exception):
    """``apply`` refused the command. The log rolls the entry back and emits nothing.

    ``code`` is an FB code when the refusal is something the user can act on.
    ``error`` carries a reader error for ReplaceDocument, when there is one.
    """

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        error: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.error = error


class ReentrantCommandError(RuntimeError):
    """A change listener tried to execute, undo or redo synchronously."""


class PlanContext(Protocol):
    """What ``Command.apply`` may use."""

    @property
    def classes(self) -> QtClassTable:
        ...

    def do(self, op: Op) -> None:
        """Apply ``op`` now and record it and its inverse."""
        ...

    def alloc(self) -> NodeId:
        """A fresh id. Replay returns the ids the original run allocated, in order."""
        ...

    def run(self, command: "Command") -> Any:
        """Apply a sub-command inside the same entry."""
        ...

    def select(self, ids: Sequence[NodeId], current: Optional[NodeId] = None) -> None:
        """Selection after the entry. The default drops removed ids."""
        ...

    def participants(self) -> "Tuple[object, ...]":
        """Rename and delete participants, sorted by ``participant_id``."""
        ...


class Command(Protocol):
    """A frozen parameter record. ``apply`` plans ops; it does not touch Qt."""

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

    ``merged`` is true when the command joined the previous undo step.
    ``noop`` is true when nothing changed and no change set was emitted.
    """

    result: Any
    revision: int
    merged: bool = False
    noop: bool = False


class ReplayAllocator:
    """Hands back the ids an entry recorded, in the same order."""

    def __init__(self, allocated: Tuple[NodeId, ...]) -> None:
        self._ids = allocated
        self._index = 0

    def alloc(self) -> NodeId:
        if self._index >= len(self._ids):
            raise AssertionError("replay asked for more ids than were recorded")
        value = self._ids[self._index]
        self._index += 1
        return value
