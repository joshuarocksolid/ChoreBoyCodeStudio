"""Draft autosave persistence for unsaved editor buffers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Optional

from app.bootstrap.paths import PathInput, ensure_directory, global_cache_dir
from app.persistence.local_history_store import LocalHistoryStore

AUTOSAVE_DIRECTORY_NAME = "autosave_drafts"


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
        cache_root = global_cache_dir(state_root)
        self._legacy_draft_root = ensure_directory(cache_root / AUTOSAVE_DIRECTORY_NAME)
        self._history_store = history_store or LocalHistoryStore(state_root=state_root)

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
        self._delete_legacy_draft(normalized_path)
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
        self._migrate_legacy_draft(normalized_path, project_id=project_id, project_root=project_root)
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
        self._delete_legacy_draft(normalized_path)

    def list_drafts(self) -> list[DraftEntry]:
        """List all valid draft entries in deterministic order."""
        self._migrate_all_legacy_drafts()
        return [
            DraftEntry(file_path=draft.file_path, content=draft.content, saved_at=draft.saved_at)
            for draft in self._history_store.list_drafts()
        ]

    def _legacy_draft_path(self, file_path: str) -> Path:
        digest = hashlib.sha256(file_path.encode("utf-8")).hexdigest()
        return self._legacy_draft_root / f"{digest}.json"

    def _delete_legacy_draft(self, file_path: str) -> None:
        legacy_path = self._legacy_draft_path(file_path)
        if legacy_path.exists():
            legacy_path.unlink()

    def _migrate_legacy_draft(
        self,
        file_path: str,
        *,
        project_id: Optional[str] = None,
        project_root: Optional[str] = None,
    ) -> None:
        legacy_entry = self._load_legacy_draft(file_path)
        if legacy_entry is None:
            return
        self._history_store.save_draft(
            legacy_entry.file_path,
            legacy_entry.content,
            project_id=project_id,
            project_root=project_root,
            saved_at=legacy_entry.saved_at,
        )
        self._delete_legacy_draft(file_path)

    def _migrate_all_legacy_drafts(self) -> None:
        for legacy_path in sorted(self._legacy_draft_root.glob("*.json")):
            legacy_entry = self._load_legacy_draft_payload(legacy_path)
            if legacy_entry is None:
                continue
            self._history_store.save_draft(
                legacy_entry.file_path,
                legacy_entry.content,
                saved_at=legacy_entry.saved_at,
            )
            try:
                legacy_path.unlink()
            except OSError:
                continue

    def _load_legacy_draft(self, file_path: str) -> Optional[DraftEntry]:
        return self._load_legacy_draft_payload(self._legacy_draft_path(file_path))

    def _load_legacy_draft_payload(self, draft_path: Path) -> Optional[DraftEntry]:
        if not draft_path.exists():
            return None
        try:
            payload = json.loads(draft_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(payload, dict):
            return None
        file_path = payload.get("file_path")
        content = payload.get("content")
        saved_at = payload.get("saved_at")
        if not isinstance(file_path, str) or not isinstance(content, str) or not isinstance(saved_at, str):
            return None
        return DraftEntry(
            file_path=str(Path(file_path).expanduser().resolve()),
            content=content,
            saved_at=saved_at,
        )
