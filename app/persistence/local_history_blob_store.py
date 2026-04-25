"""Content-addressed blob storage for local history."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from app.bootstrap.paths import PathInput, ensure_directory, global_history_blobs_dir
from app.persistence.atomic_write import atomic_write_text


class LocalHistoryBlobStore:
    """Store full-text history payloads by SHA-256 digest."""

    def __init__(self, state_root: Optional[PathInput] = None) -> None:
        self._blobs_root = ensure_directory(global_history_blobs_dir(state_root))

    @property
    def blobs_root(self) -> Path:
        return self._blobs_root

    def blob_path(self, blob_sha256: str) -> Path:
        digest = blob_sha256.strip().lower()
        return self._blobs_root / digest[:2] / digest[2:4] / digest

    def store_blob(self, content: str) -> str:
        blob_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        blob_path = self.blob_path(blob_sha256)
        if blob_path.exists():
            return blob_sha256
        ensure_directory(blob_path.parent)
        atomic_write_text(blob_path, content)
        return blob_sha256

    def load_blob(self, blob_sha256: str) -> Optional[str]:
        blob_path = self.blob_path(blob_sha256)
        try:
            return blob_path.read_text(encoding="utf-8")
        except OSError:
            return None
