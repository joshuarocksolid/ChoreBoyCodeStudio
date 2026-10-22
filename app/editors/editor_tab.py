"""Editor tab state model and helpers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path


DISK_CONFLICT_CHANGED = "changed"
DISK_CONFLICT_MISSING = "missing"


@dataclass(frozen=True)
class DiskConflict:
    """Unresolved divergence between a buffer and its file on disk."""

    kind: str
    conflict_mtime: float | None


@dataclass
class EditorTabState:
    """In-memory state for a single opened file tab."""

    file_path: str
    display_name: str
    original_content: str
    current_content: str
    last_known_mtime: float | None = None
    is_preview: bool = False
    buffer_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    disk_conflict: DiskConflict | None = None

    @classmethod
    def from_file(
        cls,
        file_path: str,
        content: str,
        *,
        last_known_mtime: float | None = None,
        is_preview: bool = False,
    ) -> "EditorTabState":
        """Create a new tab state from file content."""
        return cls(
            file_path=file_path,
            display_name=Path(file_path).name,
            original_content=content,
            current_content=content,
            last_known_mtime=last_known_mtime,
            is_preview=is_preview,
        )

    @property
    def is_dirty(self) -> bool:
        """Return True when tab content differs from saved content."""
        return self.current_content != self.original_content

    def update_content(self, content: str) -> None:
        """Replace current editor content."""
        self.current_content = content

    def mark_saved(self, *, last_known_mtime: float | None = None) -> None:
        """Mark current content as the persisted baseline."""
        self.original_content = self.current_content
        self.last_known_mtime = last_known_mtime
        self.disk_conflict = None

    def set_last_known_mtime(self, mtime: float | None) -> None:
        """Record most recently observed on-disk mtime."""
        self.last_known_mtime = mtime

    def set_disk_conflict(self, kind: str, conflict_mtime: float | None) -> None:
        self.disk_conflict = DiskConflict(kind=kind, conflict_mtime=conflict_mtime)

    def clear_disk_conflict(self) -> None:
        self.disk_conflict = None

    def promote(self) -> None:
        """Mark a preview tab as permanent."""
        self.is_preview = False
