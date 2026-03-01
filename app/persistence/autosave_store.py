"""Draft autosave persistence for unsaved editor buffers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path

from app.bootstrap.paths import PathInput, ensure_directory, global_cache_dir

AUTOSAVE_DIRECTORY_NAME = "autosave_drafts"


@dataclass(frozen=True)
class DraftEntry:
    """Persisted draft payload for one file path."""

    file_path: str
    content: str
    saved_at: str


class AutosaveStore:
    """Filesystem-backed draft store keyed by absolute file path."""

    def __init__(self, state_root: PathInput | None = None) -> None:
        cache_root = global_cache_dir(state_root)
        self._draft_root = ensure_directory(cache_root / AUTOSAVE_DIRECTORY_NAME)

    def save_draft(self, file_path: str, content: str) -> DraftEntry:
        """Persist a draft for file path and return stored metadata."""
        normalized_path = str(Path(file_path).expanduser().resolve())
        draft_entry = DraftEntry(
            file_path=normalized_path,
            content=content,
            saved_at=datetime.now().isoformat(timespec="seconds"),
        )
        draft_path = self._draft_path(normalized_path)
        draft_path.write_text(json.dumps(draft_entry.__dict__, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return draft_entry

    def load_draft(self, file_path: str) -> DraftEntry | None:
        """Load draft for file path, if present and valid."""
        normalized_path = str(Path(file_path).expanduser().resolve())
        draft_path = self._draft_path(normalized_path)
        if not draft_path.exists():
            return None

        try:
            payload = json.loads(draft_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        if not isinstance(payload, dict):
            return None
        if payload.get("file_path") != normalized_path:
            return None
        content = payload.get("content")
        saved_at = payload.get("saved_at")
        if not isinstance(content, str) or not isinstance(saved_at, str):
            return None
        return DraftEntry(file_path=normalized_path, content=content, saved_at=saved_at)

    def delete_draft(self, file_path: str) -> None:
        """Delete persisted draft for file path if present."""
        draft_path = self._draft_path(str(Path(file_path).expanduser().resolve()))
        if draft_path.exists():
            draft_path.unlink()

    def list_drafts(self) -> list[DraftEntry]:
        """List all valid draft entries in deterministic order."""
        drafts: list[DraftEntry] = []
        for draft_path in sorted(self._draft_root.glob("*.json")):
            try:
                payload = json.loads(draft_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(payload, dict):
                continue
            file_path = payload.get("file_path")
            content = payload.get("content")
            saved_at = payload.get("saved_at")
            if isinstance(file_path, str) and isinstance(content, str) and isinstance(saved_at, str):
                drafts.append(DraftEntry(file_path=file_path, content=content, saved_at=saved_at))
        return drafts

    def _draft_path(self, file_path: str) -> Path:
        digest = hashlib.sha256(file_path.encode("utf-8")).hexdigest()
        return self._draft_root / f"{digest}.json"
