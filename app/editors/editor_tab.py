"""Editor tab state model and helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class EditorTabState:
    """In-memory state for a single opened file tab."""

    file_path: str
    display_name: str
    original_content: str
    current_content: str

    @classmethod
    def from_file(cls, file_path: str, content: str) -> "EditorTabState":
        """Create a new tab state from file content."""
        return cls(
            file_path=file_path,
            display_name=Path(file_path).name,
            original_content=content,
            current_content=content,
        )

    @property
    def is_dirty(self) -> bool:
        """Return True when tab content differs from saved content."""
        return self.current_content != self.original_content

    def update_content(self, content: str) -> None:
        """Replace current editor content."""
        self.current_content = content

    def mark_saved(self) -> None:
        """Mark current content as the persisted baseline."""
        self.original_content = self.current_content
