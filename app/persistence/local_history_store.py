"""SQLite + blob-backed local history store for drafts and checkpoints."""

from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
import sqlite3
from typing import Iterable, Optional
import uuid

from app.bootstrap.paths import (
    PathInput,
    ensure_directory,
    global_history_blobs_dir,
    global_history_dir,
    global_history_index_path,
    project_manifest_path,
)
from app.persistence.atomic_write import atomic_write_text
from app.persistence.history_models import (
    HistoryFileRecord,
    LocalHistoryCheckpoint,
    LocalHistoryDraft,
    LocalHistoryFileSummary,
    ResolvedHistorySubject,
)
from app.persistence.history_retention import (
    LocalHistoryRetentionPolicy,
    checkpoint_skip_reason,
    checkpoint_ids_to_prune,
    default_local_history_retention_policy,
)
from app.project.project_manifest import ensure_project_id

LOCAL_HISTORY_SCHEMA_VERSION = 1


class LocalHistoryStore:
    """Persist local history metadata in SQLite and contents in blob files."""

    def __init__(
        self,
        state_root: Optional[PathInput] = None,
        retention_policy: Optional[LocalHistoryRetentionPolicy] = None,
    ) -> None:
        self._history_root = ensure_directory(global_history_dir(state_root))
        self._blobs_root = ensure_directory(global_history_blobs_dir(state_root))
        self._db_path = global_history_index_path(state_root)
        self._retention_policy = retention_policy or default_local_history_retention_policy()
        self._initialize_schema()

    @property
    def db_path(self) -> str:
        return str(self._db_path)

    @property
    def history_root(self) -> Path:
        return self._history_root

    @property
    def blobs_root(self) -> Path:
        return self._blobs_root

    @property
    def retention_policy(self) -> LocalHistoryRetentionPolicy:
        return self._retention_policy

    def blob_path(self, blob_sha256: str) -> Path:
        """Return the blob path for a content digest."""
        digest = blob_sha256.strip().lower()
        return self._blobs_root / digest[:2] / digest[2:4] / digest

    def save_draft(
        self,
        file_path: str,
        content: str,
        *,
        project_id: Optional[str] = None,
        project_root: Optional[str] = None,
        saved_at: Optional[str] = None,
    ) -> LocalHistoryDraft:
        """Persist or update the latest draft head for a file."""
        subject = self._resolve_subject(file_path, project_id=project_id, project_root=project_root)
        timestamp = saved_at or _now_iso()
        blob_sha256 = self._store_blob(content)
        content_size_bytes = len(content.encode("utf-8"))

        with self._connect() as connection:
            self._upsert_project(connection, subject.project_id, subject.project_root, timestamp)
            file_record = self._resolve_or_create_file_record(connection, subject, timestamp)
            connection.execute(
                """
                INSERT INTO drafts(
                    file_key,
                    project_id,
                    absolute_path,
                    relative_path,
                    blob_sha256,
                    content_size_bytes,
                    saved_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_key) DO UPDATE SET
                    absolute_path=excluded.absolute_path,
                    relative_path=excluded.relative_path,
                    blob_sha256=excluded.blob_sha256,
                    content_size_bytes=excluded.content_size_bytes,
                    saved_at=excluded.saved_at
                """,
                (
                    file_record.file_key,
                    subject.project_id,
                    subject.file_path,
                    subject.relative_path,
                    blob_sha256,
                    content_size_bytes,
                    timestamp,
                ),
            )
            connection.commit()

        return LocalHistoryDraft(
            file_key=file_record.file_key,
            project_id=subject.project_id,
            file_path=subject.file_path,
            relative_path=subject.relative_path,
            blob_sha256=blob_sha256,
            content=content,
            saved_at=timestamp,
        )

    def load_draft(
        self,
        file_path: str,
        *,
        project_id: Optional[str] = None,
        project_root: Optional[str] = None,
    ) -> Optional[LocalHistoryDraft]:
        """Return the current draft head for a file, if one exists."""
        subject = self._resolve_subject(file_path, project_id=project_id, project_root=project_root)
        with self._connect() as connection:
            file_record = self._lookup_file_record(connection, subject, include_deleted=True)
            if file_record is None:
                return None
            row = connection.execute(
                """
                SELECT file_key, project_id, absolute_path, relative_path, blob_sha256, saved_at
                FROM drafts
                WHERE file_key = ?
                """,
                (file_record.file_key,),
            ).fetchone()
        if row is None:
            return None
        content = self._load_blob(str(row["blob_sha256"]))
        if content is None:
            return None
        return LocalHistoryDraft(
            file_key=str(row["file_key"]),
            project_id=str(row["project_id"]),
            file_path=str(row["absolute_path"]),
            relative_path=str(row["relative_path"]),
            blob_sha256=str(row["blob_sha256"]),
            content=content,
            saved_at=str(row["saved_at"]),
        )

    def delete_draft(
        self,
        file_path: str,
        *,
        project_id: Optional[str] = None,
        project_root: Optional[str] = None,
    ) -> None:
        """Delete the current draft head for a file."""
        subject = self._resolve_subject(file_path, project_id=project_id, project_root=project_root)
        with self._connect() as connection:
            file_record = self._lookup_file_record(connection, subject, include_deleted=True)
            if file_record is not None:
                connection.execute("DELETE FROM drafts WHERE file_key = ?", (file_record.file_key,))
            else:
                connection.execute(
                    "DELETE FROM drafts WHERE project_id = ? AND absolute_path = ?",
                    (subject.project_id, subject.file_path),
                )
            connection.commit()

    def list_drafts(self) -> list[LocalHistoryDraft]:
        """Return all valid draft heads in deterministic order."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT file_key, project_id, absolute_path, relative_path, blob_sha256, saved_at
                FROM drafts
                ORDER BY absolute_path
                """
            ).fetchall()

        drafts: list[LocalHistoryDraft] = []
        for row in rows:
            content = self._load_blob(str(row["blob_sha256"]))
            if content is None:
                continue
            drafts.append(
                LocalHistoryDraft(
                    file_key=str(row["file_key"]),
                    project_id=str(row["project_id"]),
                    file_path=str(row["absolute_path"]),
                    relative_path=str(row["relative_path"]),
                    blob_sha256=str(row["blob_sha256"]),
                    content=content,
                    saved_at=str(row["saved_at"]),
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
        subject = self._resolve_subject(file_path, project_id=project_id, project_root=project_root)
        if checkpoint_skip_reason(
            subject.file_path,
            content,
            self._retention_policy,
            project_root=subject.project_root,
        ):
            return None
        timestamp = created_at or _now_iso()
        blob_sha256 = self._store_blob(content)
        content_size_bytes = len(content.encode("utf-8"))

        with self._connect() as connection:
            self._upsert_project(connection, subject.project_id, subject.project_root, timestamp)
            file_record = self._resolve_or_create_file_record(connection, subject, timestamp)
            if transaction_id:
                self._ensure_transaction(
                    connection,
                    project_id=subject.project_id,
                    transaction_id=transaction_id,
                    kind=source,
                    label=label,
                    created_at=timestamp,
                )
            cursor = connection.execute(
                """
                INSERT INTO checkpoints(
                    file_key,
                    project_id,
                    absolute_path,
                    relative_path,
                    blob_sha256,
                    content_size_bytes,
                    created_at,
                    source,
                    label,
                    transaction_id
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_record.file_key,
                    subject.project_id,
                    subject.file_path,
                    subject.relative_path,
                    blob_sha256,
                    content_size_bytes,
                    timestamp,
                    source,
                    label,
                    transaction_id,
                ),
            )
            row_id = cursor.lastrowid
            if row_id is None:
                raise RuntimeError("sqlite did not return a revision id for the inserted checkpoint")
            revision_id = int(row_id)
            self._prune_file_checkpoints(connection, file_record.file_key)
            connection.commit()

        return LocalHistoryCheckpoint(
            revision_id=revision_id,
            file_key=file_record.file_key,
            project_id=subject.project_id,
            file_path=subject.file_path,
            relative_path=subject.relative_path,
            blob_sha256=blob_sha256,
            created_at=timestamp,
            source=source,
            label=label,
            transaction_id=transaction_id,
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
        subject = self._resolve_subject(file_path, project_root=project_root)
        return checkpoint_skip_reason(
            subject.file_path,
            content,
            self._retention_policy,
            project_root=subject.project_root,
        )

    def prune_all_checkpoints(self) -> None:
        """Apply the current retention policy to every logical file."""
        with self._connect() as connection:
            rows = connection.execute("SELECT file_key FROM files").fetchall()
            for row in rows:
                self._prune_file_checkpoints(connection, str(row["file_key"]))
            connection.commit()

    def list_checkpoints(
        self,
        file_path: str,
        *,
        project_id: Optional[str] = None,
        project_root: Optional[str] = None,
        include_deleted: bool = False,
    ) -> list[LocalHistoryCheckpoint]:
        """List checkpoints for one logical file from newest to oldest."""
        subject = self._resolve_subject(file_path, project_id=project_id, project_root=project_root)
        with self._connect() as connection:
            file_record = self._lookup_file_record(connection, subject, include_deleted=include_deleted)
            if file_record is None:
                return []
            rows = connection.execute(
                """
                SELECT
                    revision_id,
                    file_key,
                    project_id,
                    absolute_path,
                    relative_path,
                    blob_sha256,
                    created_at,
                    source,
                    label,
                    transaction_id
                FROM checkpoints
                WHERE file_key = ?
                ORDER BY created_at DESC, revision_id DESC
                """,
                (file_record.file_key,),
            ).fetchall()
        return [
            LocalHistoryCheckpoint(
                revision_id=int(row["revision_id"]),
                file_key=str(row["file_key"]),
                project_id=str(row["project_id"]),
                file_path=str(row["absolute_path"]),
                relative_path=str(row["relative_path"]),
                blob_sha256=str(row["blob_sha256"]),
                created_at=str(row["created_at"]),
                source=str(row["source"]),
                label=str(row["label"] or ""),
                transaction_id=None if row["transaction_id"] is None else str(row["transaction_id"]),
            )
            for row in rows
        ]

    def load_checkpoint_content(self, revision_id: int) -> Optional[str]:
        """Load checkpoint content by revision id."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT blob_sha256 FROM checkpoints WHERE revision_id = ?",
                (int(revision_id),),
            ).fetchone()
        if row is None:
            return None
        return self._load_blob(str(row["blob_sha256"]))

    def get_file_record(
        self,
        file_path: str,
        *,
        project_id: Optional[str] = None,
        project_root: Optional[str] = None,
        include_deleted: bool = False,
    ) -> Optional[HistoryFileRecord]:
        """Return the current logical-file record for a path."""
        subject = self._resolve_subject(file_path, project_id=project_id, project_root=project_root)
        with self._connect() as connection:
            return self._lookup_file_record(connection, subject, include_deleted=include_deleted)

    def list_global_history_files(self, *, project_id: Optional[str] = None) -> list[LocalHistoryFileSummary]:
        """Return global file summaries for timelines that have durable checkpoints."""
        query = """
            SELECT
                f.file_key,
                f.project_id,
                p.project_root,
                f.current_absolute_path,
                f.current_relative_path,
                f.current_display_path,
                f.is_deleted,
                f.deleted_at,
                (
                    SELECT c.revision_id
                    FROM checkpoints c
                    WHERE c.file_key = f.file_key
                    ORDER BY c.created_at DESC, c.revision_id DESC
                    LIMIT 1
                ) AS latest_revision_id,
                (
                    SELECT c.created_at
                    FROM checkpoints c
                    WHERE c.file_key = f.file_key
                    ORDER BY c.created_at DESC, c.revision_id DESC
                    LIMIT 1
                ) AS latest_checkpoint_at,
                (
                    SELECT c.label
                    FROM checkpoints c
                    WHERE c.file_key = f.file_key
                    ORDER BY c.created_at DESC, c.revision_id DESC
                    LIMIT 1
                ) AS latest_label,
                (
                    SELECT c.source
                    FROM checkpoints c
                    WHERE c.file_key = f.file_key
                    ORDER BY c.created_at DESC, c.revision_id DESC
                    LIMIT 1
                ) AS latest_source,
                (
                    SELECT COUNT(*)
                    FROM checkpoints c
                    WHERE c.file_key = f.file_key
                ) AS checkpoint_count
            FROM files f
            LEFT JOIN projects p ON p.project_id = f.project_id
            WHERE EXISTS(
                SELECT 1
                FROM checkpoints c
                WHERE c.file_key = f.file_key
            )
        """
        parameters: list[str] = []
        if project_id is not None and project_id.strip():
            query += " AND f.project_id = ?"
            parameters.append(project_id.strip())
        query += " ORDER BY latest_checkpoint_at DESC, latest_revision_id DESC"

        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
            summaries: list[LocalHistoryFileSummary] = []
            for row in rows:
                latest_revision_id = row["latest_revision_id"]
                latest_checkpoint_at = row["latest_checkpoint_at"]
                latest_source = row["latest_source"]
                if latest_revision_id is None or latest_checkpoint_at is None or latest_source is None:
                    continue
                summaries.append(
                    LocalHistoryFileSummary(
                        file_key=str(row["file_key"]),
                        project_id=str(row["project_id"]),
                        project_root=None if row["project_root"] is None else str(row["project_root"]),
                        file_path=str(row["current_absolute_path"]),
                        relative_path=str(row["current_relative_path"]),
                        display_path=str(row["current_display_path"]),
                        is_deleted=bool(int(row["is_deleted"])),
                        deleted_at=None if row["deleted_at"] is None else str(row["deleted_at"]),
                        latest_revision_id=int(latest_revision_id),
                        latest_checkpoint_at=str(latest_checkpoint_at),
                        latest_label=str(row["latest_label"] or ""),
                        latest_source=str(latest_source),
                        checkpoint_count=int(row["checkpoint_count"]),
                        path_aliases=self._path_aliases_for_file_key(connection, str(row["file_key"])),
                    )
                )
        return summaries

    def remap_file_lineage(
        self,
        *,
        project_id: str,
        path_mapping: dict[str, str],
        project_root: Optional[str] = None,
        changed_at: Optional[str] = None,
    ) -> None:
        """Update logical-file current paths after app-driven move/rename operations."""
        if not path_mapping:
            return
        timestamp = changed_at or _now_iso()
        with self._connect() as connection:
            self._upsert_project(connection, project_id, project_root, timestamp)
            for old_path, new_path in path_mapping.items():
                old_subject = self._resolve_subject(old_path, project_id=project_id, project_root=project_root)
                new_subject = self._resolve_subject(new_path, project_id=project_id, project_root=project_root)
                file_record = self._lookup_file_record(connection, old_subject, include_deleted=True)
                if file_record is None:
                    continue
                connection.execute(
                    """
                    UPDATE files
                    SET
                        current_absolute_path = ?,
                        current_relative_path = ?,
                        current_display_path = ?,
                        is_deleted = 0,
                        deleted_at = NULL,
                        updated_at = ?
                    WHERE file_key = ?
                    """,
                    (
                        new_subject.file_path,
                        new_subject.relative_path,
                        new_subject.display_path,
                        timestamp,
                        file_record.file_key,
                    ),
                )
                connection.execute(
                    """
                    UPDATE drafts
                    SET absolute_path = ?, relative_path = ?
                    WHERE file_key = ?
                    """,
                    (
                        new_subject.file_path,
                        new_subject.relative_path,
                        file_record.file_key,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO file_lineage(
                        file_key,
                        project_id,
                        event_kind,
                        previous_absolute_path,
                        absolute_path,
                        previous_relative_path,
                        relative_path,
                        changed_at
                    ) VALUES(?, ?, 'move', ?, ?, ?, ?, ?)
                    """,
                    (
                        file_record.file_key,
                        project_id,
                        old_subject.file_path,
                        new_subject.file_path,
                        old_subject.relative_path,
                        new_subject.relative_path,
                        timestamp,
                    ),
                )
            connection.commit()

    def record_deleted_path(
        self,
        *,
        project_id: str,
        deleted_path: str,
        project_root: Optional[str] = None,
        deleted_at: Optional[str] = None,
    ) -> None:
        """Mark one path or directory subtree as deleted in local-history metadata."""
        subject = self._resolve_subject(deleted_path, project_id=project_id, project_root=project_root)
        timestamp = deleted_at or _now_iso()
        absolute_prefix = subject.file_path
        relative_prefix = subject.relative_path
        absolute_glob = f"{absolute_prefix}/%"
        relative_glob = f"{relative_prefix}/%"

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT file_key, current_absolute_path, current_relative_path
                FROM files
                WHERE project_id = ?
                  AND (
                    current_absolute_path = ?
                    OR current_absolute_path LIKE ?
                    OR current_relative_path = ?
                    OR current_relative_path LIKE ?
                  )
                """,
                (
                    project_id,
                    absolute_prefix,
                    absolute_glob,
                    relative_prefix,
                    relative_glob,
                ),
            ).fetchall()
            for row in rows:
                connection.execute(
                    """
                    UPDATE files
                    SET is_deleted = 1, deleted_at = ?, updated_at = ?
                    WHERE file_key = ?
                    """,
                    (timestamp, timestamp, str(row["file_key"])),
                )
                connection.execute(
                    """
                    INSERT INTO file_lineage(
                        file_key,
                        project_id,
                        event_kind,
                        previous_absolute_path,
                        absolute_path,
                        previous_relative_path,
                        relative_path,
                        changed_at
                    ) VALUES(?, ?, 'delete', ?, ?, ?, ?, ?)
                    """,
                    (
                        str(row["file_key"]),
                        project_id,
                        str(row["current_absolute_path"]),
                        str(row["current_absolute_path"]),
                        str(row["current_relative_path"]),
                        str(row["current_relative_path"]),
                        timestamp,
                    ),
                )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize_schema(self) -> None:
        ensure_directory(self._db_path.parent)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_meta(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS projects(
                    project_id TEXT PRIMARY KEY,
                    project_root TEXT,
                    last_seen_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS files(
                    file_key TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    current_absolute_path TEXT NOT NULL,
                    current_relative_path TEXT NOT NULL,
                    current_display_path TEXT NOT NULL,
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS file_lineage(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_key TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    event_kind TEXT NOT NULL,
                    previous_absolute_path TEXT,
                    absolute_path TEXT NOT NULL,
                    previous_relative_path TEXT,
                    relative_path TEXT NOT NULL,
                    changed_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS drafts(
                    file_key TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    absolute_path TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    blob_sha256 TEXT NOT NULL,
                    content_size_bytes INTEGER NOT NULL,
                    saved_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS transactions(
                    transaction_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    label TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints(
                    revision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_key TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    absolute_path TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    blob_sha256 TEXT NOT NULL,
                    content_size_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    label TEXT NOT NULL DEFAULT '',
                    transaction_id TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_files_project_absolute ON files(project_id, current_absolute_path)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_files_project_relative ON files(project_id, current_relative_path)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_lineage_project_absolute ON file_lineage(project_id, absolute_path)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_lineage_project_relative ON file_lineage(project_id, relative_path)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_drafts_project_absolute ON drafts(project_id, absolute_path)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_checkpoints_file_created ON checkpoints(file_key, created_at DESC, revision_id DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_checkpoints_project_absolute ON checkpoints(project_id, absolute_path, created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_checkpoints_transaction ON checkpoints(transaction_id)"
            )
            connection.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)",
                ("schema_version", str(LOCAL_HISTORY_SCHEMA_VERSION)),
            )
            connection.commit()

    def _store_blob(self, content: str) -> str:
        blob_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        blob_path = self.blob_path(blob_sha256)
        if blob_path.exists():
            return blob_sha256
        ensure_directory(blob_path.parent)
        atomic_write_text(blob_path, content)
        return blob_sha256

    def _load_blob(self, blob_sha256: str) -> Optional[str]:
        blob_path = self.blob_path(blob_sha256)
        try:
            return blob_path.read_text(encoding="utf-8")
        except OSError:
            return None

    def _resolve_subject(
        self,
        file_path: str,
        *,
        project_id: Optional[str] = None,
        project_root: Optional[str] = None,
    ) -> ResolvedHistorySubject:
        normalized_path = str(Path(file_path).expanduser().resolve())
        inferred_project_id = project_id.strip() if isinstance(project_id, str) and project_id.strip() else None
        inferred_project_root = None
        if project_root is not None:
            candidate_root = Path(project_root).expanduser().resolve()
            try:
                relative_path = Path(normalized_path).relative_to(candidate_root).as_posix()
                inferred_project_root = str(candidate_root)
                display_path = relative_path
                if inferred_project_id is None:
                    inferred_project_id = self._fallback_project_id_for_root(inferred_project_root)
                return ResolvedHistorySubject(
                    project_id=inferred_project_id,
                    project_root=inferred_project_root,
                    file_path=normalized_path,
                    relative_path=relative_path,
                    display_path=display_path,
                )
            except ValueError:
                inferred_project_root = None

        if inferred_project_id is None or inferred_project_root is None:
            discovered = self._discover_project_context(Path(normalized_path))
            if discovered is not None:
                discovered_project_id, discovered_project_root = discovered
                if inferred_project_id is None:
                    inferred_project_id = discovered_project_id
                if inferred_project_root is None:
                    inferred_project_root = discovered_project_root

        if inferred_project_root is not None:
            relative_path = Path(normalized_path).relative_to(Path(inferred_project_root)).as_posix()
            display_path = relative_path
            return ResolvedHistorySubject(
                project_id=inferred_project_id or self._fallback_project_id_for_root(inferred_project_root),
                project_root=inferred_project_root,
                file_path=normalized_path,
                relative_path=relative_path,
                display_path=display_path,
            )

        external_project_id = inferred_project_id or self._fallback_project_id_for_path(normalized_path)
        return ResolvedHistorySubject(
            project_id=external_project_id,
            project_root=None,
            file_path=normalized_path,
            relative_path=normalized_path,
            display_path=normalized_path,
        )

    def _discover_project_context(self, file_path: Path) -> Optional[tuple[str, str]]:
        for parent in [file_path.parent, *file_path.parents]:
            manifest_path = project_manifest_path(parent)
            if not manifest_path.exists() or not manifest_path.is_file():
                continue
            metadata = ensure_project_id(manifest_path)
            return metadata.project_id, str(parent.resolve())
        return None

    def _resolve_or_create_file_record(
        self,
        connection: sqlite3.Connection,
        subject: ResolvedHistorySubject,
        timestamp: str,
    ) -> HistoryFileRecord:
        existing = self._lookup_file_record(connection, subject, include_deleted=True)
        if existing is not None:
            self._refresh_file_record(connection, existing.file_key, subject, timestamp)
            refreshed = self._lookup_file_record(connection, subject, include_deleted=True)
            return refreshed if refreshed is not None else existing

        file_key = f"file_{uuid.uuid4().hex}"
        connection.execute(
            """
            INSERT INTO files(
                file_key,
                project_id,
                current_absolute_path,
                current_relative_path,
                current_display_path,
                is_deleted,
                created_at,
                updated_at,
                deleted_at
            ) VALUES(?, ?, ?, ?, ?, 0, ?, ?, NULL)
            """,
            (
                file_key,
                subject.project_id,
                subject.file_path,
                subject.relative_path,
                subject.display_path,
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            """
            INSERT INTO file_lineage(
                file_key,
                project_id,
                event_kind,
                previous_absolute_path,
                absolute_path,
                previous_relative_path,
                relative_path,
                changed_at
            ) VALUES(?, ?, 'create', NULL, ?, NULL, ?, ?)
            """,
            (
                file_key,
                subject.project_id,
                subject.file_path,
                subject.relative_path,
                timestamp,
            ),
        )
        return HistoryFileRecord(
            file_key=file_key,
            project_id=subject.project_id,
            file_path=subject.file_path,
            relative_path=subject.relative_path,
            is_deleted=False,
            created_at=timestamp,
            updated_at=timestamp,
            deleted_at=None,
        )

    def _lookup_file_record(
        self,
        connection: sqlite3.Connection,
        subject: ResolvedHistorySubject,
        *,
        include_deleted: bool,
    ) -> Optional[HistoryFileRecord]:
        row = connection.execute(
            """
            SELECT
                file_key,
                project_id,
                current_absolute_path,
                current_relative_path,
                is_deleted,
                created_at,
                updated_at,
                deleted_at
            FROM files
            WHERE project_id = ?
              AND (
                current_absolute_path = ?
                OR current_relative_path = ?
              )
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (subject.project_id, subject.file_path, subject.relative_path),
        ).fetchone()
        if row is None:
            row = connection.execute(
                """
                SELECT
                    f.file_key,
                    f.project_id,
                    f.current_absolute_path,
                    f.current_relative_path,
                    f.is_deleted,
                    f.created_at,
                    f.updated_at,
                    f.deleted_at
                FROM file_lineage fl
                JOIN files f ON f.file_key = fl.file_key
                WHERE fl.project_id = ?
                  AND (
                    fl.absolute_path = ?
                    OR fl.relative_path = ?
                  )
                ORDER BY fl.changed_at DESC, fl.event_id DESC
                LIMIT 1
                """,
                (subject.project_id, subject.file_path, subject.relative_path),
            ).fetchone()
        if row is None:
            return None
        record = self._row_to_file_record(row)
        if record.is_deleted and not include_deleted:
            return None
        return record

    def _row_to_file_record(self, row: sqlite3.Row) -> HistoryFileRecord:
        return HistoryFileRecord(
            file_key=str(row["file_key"]),
            project_id=str(row["project_id"]),
            file_path=str(row["current_absolute_path"]),
            relative_path=str(row["current_relative_path"]),
            is_deleted=bool(int(row["is_deleted"])),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            deleted_at=None if row["deleted_at"] is None else str(row["deleted_at"]),
        )

    def _path_aliases_for_file_key(self, connection: sqlite3.Connection, file_key: str) -> tuple[str, ...]:
        aliases: list[str] = []
        seen: set[str] = set()

        current_row = connection.execute(
            """
            SELECT current_absolute_path, current_relative_path, current_display_path
            FROM files
            WHERE file_key = ?
            """,
            (file_key,),
        ).fetchone()
        if current_row is not None:
            for value in (
                current_row["current_relative_path"],
                current_row["current_display_path"],
                current_row["current_absolute_path"],
            ):
                normalized = str(value).strip()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                aliases.append(normalized)

        lineage_rows = connection.execute(
            """
            SELECT previous_absolute_path, absolute_path, previous_relative_path, relative_path
            FROM file_lineage
            WHERE file_key = ?
            ORDER BY changed_at DESC, event_id DESC
            """,
            (file_key,),
        ).fetchall()
        for row in lineage_rows:
            for value in (
                row["previous_relative_path"],
                row["relative_path"],
                row["previous_absolute_path"],
                row["absolute_path"],
            ):
                if value is None:
                    continue
                normalized = str(value).strip()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                aliases.append(normalized)
        return tuple(aliases)

    def _refresh_file_record(
        self,
        connection: sqlite3.Connection,
        file_key: str,
        subject: ResolvedHistorySubject,
        timestamp: str,
    ) -> None:
        existing = connection.execute(
            """
            SELECT current_absolute_path, current_relative_path
            FROM files
            WHERE file_key = ?
            """,
            (file_key,),
        ).fetchone()
        if existing is None:
            return
        previous_absolute_path = str(existing["current_absolute_path"])
        previous_relative_path = str(existing["current_relative_path"])
        if (
            previous_absolute_path == subject.file_path
            and previous_relative_path == subject.relative_path
        ):
            connection.execute(
                """
                UPDATE files
                SET is_deleted = 0, deleted_at = NULL, updated_at = ?
                WHERE file_key = ?
                """,
                (timestamp, file_key),
            )
            return

        connection.execute(
            """
            UPDATE files
            SET
                current_absolute_path = ?,
                current_relative_path = ?,
                current_display_path = ?,
                is_deleted = 0,
                deleted_at = NULL,
                updated_at = ?
            WHERE file_key = ?
            """,
            (
                subject.file_path,
                subject.relative_path,
                subject.display_path,
                timestamp,
                file_key,
            ),
        )
        connection.execute(
            """
            UPDATE drafts
            SET absolute_path = ?, relative_path = ?
            WHERE file_key = ?
            """,
            (subject.file_path, subject.relative_path, file_key),
        )
        connection.execute(
            """
            INSERT INTO file_lineage(
                file_key,
                project_id,
                event_kind,
                previous_absolute_path,
                absolute_path,
                previous_relative_path,
                relative_path,
                changed_at
            ) VALUES(?, ?, 'move', ?, ?, ?, ?, ?)
            """,
            (
                file_key,
                subject.project_id,
                previous_absolute_path,
                subject.file_path,
                previous_relative_path,
                subject.relative_path,
                timestamp,
            ),
        )

    def _prune_file_checkpoints(self, connection: sqlite3.Connection, file_key: str) -> None:
        rows = connection.execute(
            """
            SELECT revision_id, created_at
            FROM checkpoints
            WHERE file_key = ?
            ORDER BY created_at DESC, revision_id DESC
            """,
            (file_key,),
        ).fetchall()
        prune_ids = checkpoint_ids_to_prune(
            [(int(row["revision_id"]), str(row["created_at"])) for row in rows],
            self._retention_policy,
        )
        if not prune_ids:
            return
        placeholders = ",".join("?" for _ in prune_ids)
        connection.execute(
            f"DELETE FROM checkpoints WHERE revision_id IN ({placeholders})",
            prune_ids,
        )

    def _upsert_project(
        self,
        connection: sqlite3.Connection,
        project_id: str,
        project_root: Optional[str],
        timestamp: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO projects(project_id, project_root, last_seen_at)
            VALUES(?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                project_root=excluded.project_root,
                last_seen_at=excluded.last_seen_at
            """,
            (project_id, project_root, timestamp),
        )

    def _ensure_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        transaction_id: str,
        kind: str,
        label: str,
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT OR IGNORE INTO transactions(
                transaction_id,
                project_id,
                kind,
                label,
                created_at
            ) VALUES(?, ?, ?, ?, ?)
            """,
            (transaction_id, project_id, kind, label, created_at),
        )

    @staticmethod
    def _fallback_project_id_for_root(project_root: str) -> str:
        digest = hashlib.sha256(project_root.encode("utf-8")).hexdigest()[:16]
        return f"proj_root_{digest}"

    @staticmethod
    def _fallback_project_id_for_path(file_path: str) -> str:
        parent_path = str(Path(file_path).expanduser().resolve().parent)
        digest = hashlib.sha256(parent_path.encode("utf-8")).hexdigest()[:16]
        return f"proj_external_{digest}"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
