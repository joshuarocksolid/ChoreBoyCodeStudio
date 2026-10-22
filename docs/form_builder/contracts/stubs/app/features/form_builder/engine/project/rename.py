"""Rename and move a form. [M1.4]"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class FileMove:
    source: str
    destination: str


@dataclass(frozen=True)
class TextEdit:
    path: str
    old: str
    new: str


@dataclass(frozen=True)
class RegeneratedFile:
    path: str
    text: str


@dataclass(frozen=True)
class RenamePlan:
    """Preview. ``reason`` is set when the rename is refused. ``adopted`` is None when the list is unchanged."""

    project_root: str
    reason: Optional[str]
    moves: Tuple[FileMove, ...]
    edits: Tuple[TextEdit, ...]
    regenerated: Tuple[RegeneratedFile, ...]
    removed: Tuple[str, ...]
    adopted: Optional[Tuple[str, ...]]

    def preview(self) -> Tuple[str, ...]:
        ...


def plan_rename(project_root: str, old_ui: str, new_ui: str, fs: object) -> RenamePlan:
    """Read the project and return the moves, the regenerated module, and the import edits."""
    ...


def apply(plan: RenamePlan, fs: object) -> None:
    """Apply the plan. Restore the previous files if a step fails. Refuse a path outside the project."""
    ...
