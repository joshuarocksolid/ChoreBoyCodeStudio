"""Draft autosave persistence for unsaved editor buffers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.bootstrap.paths import PathInput
from app.persistence.local_history_store import LocalHistoryStore


@dataclass(frozen=True)
class DraftEntry:
    """Persisted draft payload for one file path."""

    file_path: str
    content: str
    saved_at: str


class AutosaveStore:
    """Compatibility wrapper over the unified local-history draft store."""

    def __init__(
        self,
        state_root: Optional[PathInput] = None,
        history_store: Optional[LocalHistoryStore] = None,
    ) -> None:
        self._history_store = history_store or LocalHistoryStore(state_root=state_root)
        # Legacy per-file JSON under ``<cache>/autosave_drafts`` was removed after L04;
        # drafts live only in the local-history store.

    def save_draft(
        self,
        file_path: str,
        content: str,
        *,
        project_id: Optional[str] = None,
        project_root: Optional[str] = None,
    ) -> DraftEntry:
        """Persist a draft for file path and return stored metadata."""
        normalized_path = str(Path(file_path).expanduser().resolve())
        stored = self._history_store.save_draft(
            normalized_path,
            content,
            project_id=project_id,
            project_root=project_root,
        )
        return DraftEntry(file_path=stored.file_path, content=stored.content, saved_at=stored.saved_at)

    def load_draft(
        self,
        file_path: str,
        *,
        project_id: Optional[str] = None,
        project_root: Optional[str] = None,
    ) -> Optional[DraftEntry]:
        """Load draft for file path, if present and valid."""
        normalized_path = str(Path(file_path).expanduser().resolve())
        stored = self._history_store.load_draft(
            normalized_path,
            project_id=project_id,
            project_root=project_root,
        )
        if stored is None:
            return None
        return DraftEntry(file_path=stored.file_path, content=stored.content, saved_at=stored.saved_at)

    def delete_draft(
        self,
        file_path: str,
        *,
        project_id: Optional[str] = None,
        project_root: Optional[str] = None,
    ) -> None:
        """Delete persisted draft for file path if present."""
        normalized_path = str(Path(file_path).expanduser().resolve())
        self._history_store.delete_draft(
            normalized_path,
            project_id=project_id,
            project_root=project_root,
        )

    def list_drafts(self) -> list[DraftEntry]:
        """List all valid draft entries in deterministic order."""
        return [
            DraftEntry(file_path=draft.file_path, content=draft.content, saved_at=draft.saved_at)
            for draft in self._history_store.list_drafts()
        ]
