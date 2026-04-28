"""SQLite + blob-backed local history store for drafts and checkpoints."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from app.bootstrap.paths import PathInput
from app.persistence.history_models import (
    DRAFT_RECOVERY_POLICY_PROMPT,
    DRAFT_SOURCE_LIVE_DIRTY_BACKUP,
    HistoryFileRecord,
    LocalHistoryCheckpoint,
    LocalHistoryDraft,
    LocalHistoryFileSummary,
)
from app.persistence.history_retention import (
    LocalHistoryRetentionPolicy,
    checkpoint_skip_reason,
    default_local_history_retention_policy,
)
from app.persistence.local_history_blob_store import LocalHistoryBlobStore
from app.persistence.local_history_repository import LocalHistoryRepository
from app.persistence.local_history_schema import LocalHistorySchema


class LocalHistoryStore:
    """Facade for local-history metadata and content blobs."""

    def __init__(
        self,
        state_root: Optional[PathInput] = None,
        retention_policy: Optional[LocalHistoryRetentionPolicy] = None,
    ) -> None:
        self._schema = LocalHistorySchema(state_root=state_root)
        self._blob_store = LocalHistoryBlobStore(state_root=state_root)
        self._repository = LocalHistoryRepository(self._schema)
        self._retention_policy = retention_policy or default_local_history_retention_policy()

    @property
    def db_path(self) -> str:
        return str(self._schema.db_path)

    @property
    def history_root(self) -> Path:
        return self._schema.history_root

    @property
    def blobs_root(self) -> Path:
        return self._blob_store.blobs_root

    @property
    def retention_policy(self) -> LocalHistoryRetentionPolicy:
        return self._retention_policy

    def blob_path(self, blob_sha256: str) -> Path:
        """Return the blob path for a content digest."""
        return self._blob_store.blob_path(blob_sha256)

    def save_draft(
        self,
        file_path: str,
        content: str,
        *,
        project_id: Optional[str] = None,
        project_root: Optional[str] = None,
        saved_at: Optional[str] = None,
        recovery_policy: str = DRAFT_RECOVERY_POLICY_PROMPT,
        source: str = DRAFT_SOURCE_LIVE_DIRTY_BACKUP,
        base_blob_sha256: Optional[str] = None,
        last_known_mtime: Optional[float] = None,
        session_id: Optional[str] = None,
    ) -> LocalHistoryDraft:
        """Persist or update the latest draft head for a file."""
        subject = self._repository.resolve_subject(file_path, project_id=project_id, project_root=project_root)
        timestamp = saved_at or _now_iso()
        blob_sha256 = self._blob_store.store_blob(content)
        record = self._repository.save_draft(
            subject,
            blob_sha256=blob_sha256,
            content_size_bytes=len(content.encode("utf-8")),
            saved_at=timestamp,
            recovery_policy=recovery_policy,
            source=source,
            base_blob_sha256=base_blob_sha256,
            last_known_mtime=last_known_mtime,
            session_id=session_id,
        )
        return LocalHistoryDraft(
            file_key=record.file_key,
            project_id=record.project_id,
            file_path=record.file_path,
            relative_path=record.relative_path,
            blob_sha256=record.blob_sha256,
            content=content,
            saved_at=record.saved_at,
            recovery_policy=record.recovery_policy,
            source=record.source,
            base_blob_sha256=record.base_blob_sha256,
            last_known_mtime=record.last_known_mtime,
            session_id=record.session_id,
        )

    def load_draft(
        self,
        file_path: str,
        *,
        project_id: Optional[str] = None,
        project_root: Optional[str] = None,
    ) -> Optional[LocalHistoryDraft]:
        """Return the current draft head for a file, if one exists."""
        subject = self._repository.resolve_subject(file_path, project_id=project_id, project_root=project_root)
        record = self._repository.load_draft(subject)
        if record is None:
            return None
        content = self._blob_store.load_blob(record.blob_sha256)
        if content is None:
            return None
        return LocalHistoryDraft(
            file_key=record.file_key,
            project_id=record.project_id,
            file_path=record.file_path,
            relative_path=record.relative_path,
            blob_sha256=record.blob_sha256,
            content=content,
            saved_at=record.saved_at,
            recovery_policy=record.recovery_policy,
            source=record.source,
            base_blob_sha256=record.base_blob_sha256,
            last_known_mtime=record.last_known_mtime,
            session_id=record.session_id,
        )

    def delete_draft(
        self,
        file_path: str,
        *,
        project_id: Optional[str] = None,
        project_root: Optional[str] = None,
    ) -> None:
        """Delete the current draft head for a file."""
        subject = self._repository.resolve_subject(file_path, project_id=project_id, project_root=project_root)
        self._repository.delete_draft(subject)

    def list_drafts(self) -> list[LocalHistoryDraft]:
        """Return all current drafts from newest to oldest."""
        drafts: list[LocalHistoryDraft] = []
        for record in self._repository.list_drafts():
            content = self._blob_store.load_blob(record.blob_sha256)
            if content is None:
                continue
            drafts.append(
                LocalHistoryDraft(
                    file_key=record.file_key,
                    project_id=record.project_id,
                    file_path=record.file_path,
                    relative_path=record.relative_path,
                    blob_sha256=record.blob_sha256,
                    content=content,
                    saved_at=record.saved_at,
                    recovery_policy=record.recovery_policy,
                    source=record.source,
                    base_blob_sha256=record.base_blob_sha256,
                    last_known_mtime=record.last_known_mtime,
                    session_id=record.session_id,
                )
            )
        return drafts

    def create_checkpoint(
        self,
        file_path: str,
        content: str,
        *,
        project_id: Optional[str] = None,
        project_root: Optional[str] = None,
        source: str,
        label: str = "",
        transaction_id: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> Optional[LocalHistoryCheckpoint]:
        """Create a durable checkpoint for a file."""
        subject = self._repository.resolve_subject(file_path, project_id=project_id, project_root=project_root)
        if checkpoint_skip_reason(
            subject.file_path,
            content,
            self._retention_policy,
            project_root=subject.project_root,
        ):
            return None
        timestamp = created_at or _now_iso()
        blob_sha256 = self._blob_store.store_blob(content)
        return self._repository.create_checkpoint(
            subject,
            blob_sha256=blob_sha256,
            content_size_bytes=len(content.encode("utf-8")),
            source=source,
            label=label,
            transaction_id=transaction_id,
            created_at=timestamp,
            retention_policy=self._retention_policy,
        )

    def set_retention_policy(self, policy: LocalHistoryRetentionPolicy, *, apply_now: bool = False) -> None:
        """Replace the active retention policy and optionally prune immediately."""
        self._retention_policy = policy
        if apply_now:
            self.prune_all_checkpoints()

    def checkpoint_skip_reason(
        self,
        file_path: str,
        content: str,
        *,
        project_root: Optional[str] = None,
    ) -> str:
        """Explain why checkpoint capture would be skipped for a file."""
        subject = self._repository.resolve_subject(file_path, project_root=project_root)
        return checkpoint_skip_reason(
            subject.file_path,
            content,
            self._retention_policy,
            project_root=subject.project_root,
        )

    def prune_all_checkpoints(self) -> None:
        """Apply the current retention policy to every logical file."""
        self._repository.prune_all_checkpoints(self._retention_policy)

    def list_checkpoints(
        self,
        file_path: str,
        *,
        project_id: Optional[str] = None,
        project_root: Optional[str] = None,
        include_deleted: bool = False,
    ) -> list[LocalHistoryCheckpoint]:
        """List checkpoints for one logical file from newest to oldest."""
        subject = self._repository.resolve_subject(file_path, project_id=project_id, project_root=project_root)
        return self._repository.list_checkpoints(subject, include_deleted=include_deleted)

    def load_checkpoint_content(self, revision_id: int) -> Optional[str]:
        """Load checkpoint content by revision id."""
        blob_sha256 = self._repository.checkpoint_blob_sha(revision_id)
        if blob_sha256 is None:
            return None
        return self._blob_store.load_blob(blob_sha256)

    def get_file_record(
        self,
        file_path: str,
        *,
        project_id: Optional[str] = None,
        project_root: Optional[str] = None,
        include_deleted: bool = False,
    ) -> Optional[HistoryFileRecord]:
        """Return the current logical-file record for a path."""
        subject = self._repository.resolve_subject(file_path, project_id=project_id, project_root=project_root)
        return self._repository.get_file_record(subject, include_deleted=include_deleted)

    def list_global_history_files(self, *, project_id: Optional[str] = None) -> list[LocalHistoryFileSummary]:
        """Return global file summaries for timelines that have durable checkpoints."""
        return self._repository.list_global_history_files(project_id=project_id)

    def remap_file_lineage(
        self,
        *,
        project_id: str,
        path_mapping: dict[str, str],
        project_root: Optional[str] = None,
        changed_at: Optional[str] = None,
    ) -> None:
        """Update logical-file current paths after app-driven move/rename operations."""
        self._repository.remap_file_lineage(
            project_id=project_id,
            path_mapping=path_mapping,
            project_root=project_root,
            changed_at=changed_at or _now_iso(),
        )

    def record_deleted_path(
        self,
        *,
        project_id: str,
        deleted_path: str,
        project_root: Optional[str] = None,
        deleted_at: Optional[str] = None,
    ) -> None:
        """Mark one path or directory subtree as deleted in local-history metadata."""
        self._repository.record_deleted_path(
            project_id=project_id,
            deleted_path=deleted_path,
            project_root=project_root,
            deleted_at=deleted_at or _now_iso(),
        )


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
