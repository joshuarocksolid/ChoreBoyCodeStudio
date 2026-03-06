"""Snapshot-backed command stack for designer mutations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class SnapshotCommand:
    """Represents one reversible mutation snapshot."""

    description: str
    before_xml: str
    after_xml: str


class CommandStack:
    """Simple undo/redo stack that replays XML snapshots."""

    def __init__(self, apply_snapshot: Callable[[str], None]) -> None:
        self._apply_snapshot = apply_snapshot
        self._commands: list[SnapshotCommand] = []
        self._cursor = -1

    @property
    def can_undo(self) -> bool:
        return self._cursor >= 0

    @property
    def can_redo(self) -> bool:
        return self._cursor < len(self._commands) - 1

    def push(self, command: SnapshotCommand) -> None:
        if command.before_xml == command.after_xml:
            return
        if self.can_redo:
            self._commands = self._commands[: self._cursor + 1]
        self._commands.append(command)
        self._cursor = len(self._commands) - 1

    def undo(self) -> bool:
        if not self.can_undo:
            return False
        command = self._commands[self._cursor]
        self._apply_snapshot(command.before_xml)
        self._cursor -= 1
        return True

    def redo(self) -> bool:
        if not self.can_redo:
            return False
        self._cursor += 1
        command = self._commands[self._cursor]
        self._apply_snapshot(command.after_xml)
        return True
