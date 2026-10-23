"""Editor tab state model and helpers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from app.editors.generated_banner import GeneratedLock
from app.editors.tab_content_source import TabContentSource


DISK_CONFLICT_CHANGED = "changed"
DISK_CONFLICT_MISSING = "missing"


@dataclass(frozen=True)
class DiskConflict:
    """Unresolved divergence between a buffer and its file on disk."""

    kind: str
    conflict_mtime: float | None


@dataclass(init=False)
class EditorTabState:
    """In-memory state for a single opened file tab.

    Tabs are identified by ``buffer_id``. ``current_content`` reads
    ``content_source.current_text()`` when a source is attached, otherwise the
    stored string. ``is_dirty`` delegates the same way.
    """

    file_path: str
    display_name: str
    original_content: str
    last_known_mtime: float | None
    is_preview: bool
    buffer_id: str
    disk_conflict: Optional[DiskConflict]
    content_source: Optional[TabContentSource]
    content_source_unsubscribe: Optional[Callable[[], None]] = field(compare=False)
    generated: Optional[GeneratedLock]
    _current_content: str = field(repr=False)

    def __init__(
        self,
        file_path: str,
        display_name: str,
        original_content: str,
        current_content: str,
        last_known_mtime: float | None = None,
        is_preview: bool = False,
        content_source: Optional[TabContentSource] = None,
        content_source_unsubscribe: Optional[Callable[[], None]] = None,
        buffer_id: Optional[str] = None,
        disk_conflict: Optional[DiskConflict] = None,
    ) -> None:
        self.file_path = file_path
        self.display_name = display_name
        self.original_content = original_content
        self._current_content = current_content
        self.last_known_mtime = last_known_mtime
        self.is_preview = is_preview
        self.buffer_id = uuid.uuid4().hex if buffer_id is None else buffer_id
        self.disk_conflict = disk_conflict
        self.content_source = content_source
        self.content_source_unsubscribe = content_source_unsubscribe
        self.generated = None

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
    def current_content(self) -> str:
        """Text Save would write. Serializes only when a content source is attached."""
        if self.content_source is not None:
            return self.content_source.current_text()
        return self._current_content

    @current_content.setter
    def current_content(self, content: str) -> None:
        if self.content_source is not None:
            raise ValueError("update_content is not valid when a content source is attached")
        self._current_content = content

    @property
    def is_dirty(self) -> bool:
        """Return True when tab content differs from saved content."""
        if self.content_source is not None:
            return self.content_source.is_dirty()
        return self._current_content != self.original_content

    def update_content(self, content: str) -> None:
        """Replace current editor content."""
        self.current_content = content

    def mark_saved(
        self,
        *,
        last_known_mtime: float | None = None,
        saved_text: Optional[str] = None,
    ) -> None:
        """Mark the persisted baseline. ``saved_text`` is the bytes just written."""
        if self.content_source is not None:
            text = self.content_source.current_text() if saved_text is None else saved_text
            self.content_source.mark_saved(text)
            self.original_content = text
            self._current_content = text
        else:
            self.original_content = self._current_content if saved_text is None else saved_text
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

    def drop_content_source_subscription(self) -> None:
        """Detach the source change listener. Safe to call more than once."""
        unsubscribe = self.content_source_unsubscribe
        self.content_source_unsubscribe = None
        if unsubscribe is not None:
            unsubscribe()
