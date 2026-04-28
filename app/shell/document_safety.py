"""Shared document-safety models for dirty-buffer lifecycle decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class DocumentCloseIntent(str, Enum):
    """User intent when dirty buffers block a lifecycle action."""

    PROCEED = "proceed"
    SAVE = "save"
    DISCARD = "discard"
    KEEP_FOR_NEXT_LAUNCH = "keep_for_next_launch"
    CANCEL = "cancel"


class DocumentScope(str, Enum):
    """Scope of the lifecycle action that is asking about dirty buffers."""

    TAB = "tab"
    PROJECT = "project"
    APPLICATION = "application"
    EXTERNAL_RELOAD = "external_reload"


@dataclass(frozen=True)
class DirtyBufferSnapshot:
    """Minimal stable snapshot of a dirty editor buffer."""

    file_path: str
    display_name: str
    current_content: str
    original_content: str
    last_known_mtime: float | None = None


@dataclass(frozen=True)
class DocumentSafetyDecision:
    """Result of an unsaved-buffer prompt or policy decision."""

    intent: DocumentCloseIntent
    scope: DocumentScope
    dirty_buffers: tuple[DirtyBufferSnapshot, ...] = ()
    failed_paths: tuple[str, ...] = ()

    @property
    def affected_paths(self) -> tuple[str, ...]:
        """Return dirty file paths in deterministic prompt order."""
        return tuple(buffer.file_path for buffer in self.dirty_buffers)

    @property
    def should_continue(self) -> bool:
        """Return True when the lifecycle action should proceed."""
        return self.intent is not DocumentCloseIntent.CANCEL and not self.failed_paths


def dirty_buffer_snapshots(tabs: Sequence[object]) -> tuple[DirtyBufferSnapshot, ...]:
    """Build snapshots from dirty tab-like objects without importing editor classes."""
    snapshots: list[DirtyBufferSnapshot] = []
    for tab in tabs:
        if not bool(getattr(tab, "is_dirty", False)):
            continue
        snapshots.append(
            DirtyBufferSnapshot(
                file_path=str(getattr(tab, "file_path")),
                display_name=str(getattr(tab, "display_name", getattr(tab, "file_path", ""))),
                current_content=str(getattr(tab, "current_content", "")),
                original_content=str(getattr(tab, "original_content", "")),
                last_known_mtime=getattr(tab, "last_known_mtime", None),
            )
        )
    return tuple(snapshots)
