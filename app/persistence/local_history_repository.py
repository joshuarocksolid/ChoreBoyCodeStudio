"""SQL repository for local-history metadata."""

from __future__ import annotations

import sqlite3
from typing import Optional
import uuid

from app.persistence.history_models import (
    HistoryFileRecord,
    LocalHistoryCheckpoint,
    LocalHistoryFileSummary,
    ResolvedHistorySubject,
)
from app.persistence.history_retention import LocalHistoryRetentionPolicy, checkpoint_ids_to_prune
from app.persistence.local_history_identity import path_aliases_for_file_keys, resolve_history_subject
from app.persistence.local_history_rows import (
    LocalHistoryDraftRecord,
    checkpoint_from_row,
    draft_record_from_row,
    file_record_from_row,
    summary_from_row,
)
from app.persistence.local_history_schema import LocalHistorySchema


class LocalHistoryRepository:
    """Read and write local-history metadata in SQLite."""

    def __init__(self, schema: LocalHistorySchema) -> None:
        self._schema = schema

    def resolve_subject(
        self,
        file_path: str,
        *,
        project_id: Optional[str] = None,
        project_root: Optional[str] = None,
    ) -> ResolvedHistorySubject:
        return resolve_history_subject(file_path, project_id=project_id, project_root=project_root)

    def save_draft(
        self,
        subject: ResolvedHistorySubject,
        *,
        blob_sha256: str,
        content_size_bytes: int,
        saved_at: str,
    ) -> LocalHistoryDraftRecord:
        with self._schema.connect() as connection:
            self._upsert_project(connection, subject.project_id, subject.project_root, saved_at)
            file_record = self._resolve_or_create_file_record(connection, subject, saved_at)
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
                    saved_at,
                ),
            )
            connection.commit()
        return LocalHistoryDraftRecord(
            file_key=file_record.file_key,
            project_id=subject.project_id,
            file_path=subject.file_path,
            relative_path=subject.relative_path,
            blob_sha256=blob_sha256,
            saved_at=saved_at,
        )

    def load_draft(self, subject: ResolvedHistorySubject) -> Optional[LocalHistoryDraftRecord]:
        with self._schema.connect() as connection:
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
        return draft_record_from_row(row)

    def delete_draft(self, subject: ResolvedHistorySubject) -> None:
        with self._schema.connect() as connection:
            file_record = self._lookup_file_record(connection, subject, include_deleted=True)
            if file_record is None:
                return
            connection.execute("DELETE FROM drafts WHERE file_key = ?", (file_record.file_key,))
            connection.commit()

    def list_drafts(self) -> list[LocalHistoryDraftRecord]:
        with self._schema.connect() as connection:
            rows = connection.execute(
                """
                SELECT file_key, project_id, absolute_path, relative_path, blob_sha256, saved_at
                FROM drafts
                ORDER BY saved_at DESC, absolute_path ASC
                """
            ).fetchall()
        return [record for row in rows if (record := draft_record_from_row(row)) is not None]

    def create_checkpoint(
        self,
        subject: ResolvedHistorySubject,
        *,
        blob_sha256: str,
        content_size_bytes: int,
        source: str,
        label: str,
        transaction_id: Optional[str],
        created_at: str,
        retention_policy: LocalHistoryRetentionPolicy,
    ) -> LocalHistoryCheckpoint:
        with self._schema.connect() as connection:
            self._upsert_project(connection, subject.project_id, subject.project_root, created_at)
            file_record = self._resolve_or_create_file_record(connection, subject, created_at)
            if transaction_id:
                self._ensure_transaction(
                    connection,
                    project_id=subject.project_id,
                    transaction_id=transaction_id,
                    kind=source,
                    label=label,
                    created_at=created_at,
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
                    created_at,
                    source,
                    label,
                    transaction_id,
                ),
            )
            row_id = cursor.lastrowid
            if row_id is None:
                raise RuntimeError("sqlite did not return a revision id for the inserted checkpoint")
            revision_id = int(row_id)
            self._prune_file_checkpoints(connection, file_record.file_key, retention_policy)
            connection.commit()
        return LocalHistoryCheckpoint(
            revision_id=revision_id,
            file_key=file_record.file_key,
            project_id=subject.project_id,
            file_path=subject.file_path,
            relative_path=subject.relative_path,
            blob_sha256=blob_sha256,
            created_at=created_at,
            source=source,
            label=label,
            transaction_id=transaction_id,
        )

    def prune_all_checkpoints(self, retention_policy: LocalHistoryRetentionPolicy) -> None:
        with self._schema.connect() as connection:
            rows = connection.execute("SELECT file_key FROM files").fetchall()
            for row in rows:
                self._prune_file_checkpoints(connection, str(row["file_key"]), retention_policy)
            connection.commit()

    def list_checkpoints(
        self,
        subject: ResolvedHistorySubject,
        *,
        include_deleted: bool = False,
    ) -> list[LocalHistoryCheckpoint]:
        with self._schema.connect() as connection:
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
        return [checkpoint_from_row(row) for row in rows]

    def checkpoint_blob_sha(self, revision_id: int) -> Optional[str]:
        with self._schema.connect() as connection:
            row = connection.execute(
                "SELECT blob_sha256 FROM checkpoints WHERE revision_id = ?",
                (int(revision_id),),
            ).fetchone()
        return None if row is None else str(row["blob_sha256"])

    def get_file_record(
        self,
        subject: ResolvedHistorySubject,
        *,
        include_deleted: bool = False,
    ) -> Optional[HistoryFileRecord]:
        with self._schema.connect() as connection:
            return self._lookup_file_record(connection, subject, include_deleted=include_deleted)

    def list_global_history_files(self, *, project_id: Optional[str] = None) -> list[LocalHistoryFileSummary]:
        query = """
            WITH ranked AS (
                SELECT
                    c.file_key,
                    c.revision_id,
                    c.created_at,
                    c.label,
                    c.source,
                    ROW_NUMBER() OVER (
                        PARTITION BY c.file_key
                        ORDER BY c.created_at DESC, c.revision_id DESC
                    ) AS rn
                FROM checkpoints c
            ),
            latest AS (
                SELECT file_key, revision_id, created_at, label, source
                FROM ranked
                WHERE rn = 1
            ),
            counts AS (
                SELECT file_key, COUNT(*) AS checkpoint_count
                FROM checkpoints
                GROUP BY file_key
            )
            SELECT
                f.file_key,
                f.project_id,
                p.project_root,
                f.current_absolute_path,
                f.current_relative_path,
                f.current_display_path,
                f.is_deleted,
                f.deleted_at,
                latest.revision_id AS latest_revision_id,
                latest.created_at AS latest_checkpoint_at,
                latest.label AS latest_label,
                latest.source AS latest_source,
                counts.checkpoint_count AS checkpoint_count
            FROM files f
            LEFT JOIN projects p ON p.project_id = f.project_id
            JOIN latest ON latest.file_key = f.file_key
            JOIN counts ON counts.file_key = f.file_key
        """
        parameters: list[str] = []
        if project_id is not None and project_id.strip():
            query += " WHERE f.project_id = ?"
            parameters.append(project_id.strip())
        query += " ORDER BY latest.created_at DESC, latest.revision_id DESC"

        with self._schema.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
            file_keys = [str(row["file_key"]) for row in rows]
            alias_map = path_aliases_for_file_keys(connection, file_keys)
        return [summary_from_row(row, alias_map) for row in rows]

    def remap_file_lineage(
        self,
        *,
        project_id: str,
        path_mapping: dict[str, str],
        project_root: Optional[str] = None,
        changed_at: str,
    ) -> None:
        if not path_mapping:
            return
        with self._schema.connect() as connection:
            self._upsert_project(connection, project_id, project_root, changed_at)
            for old_path, new_path in path_mapping.items():
                old_subject = self.resolve_subject(old_path, project_id=project_id, project_root=project_root)
                new_subject = self.resolve_subject(new_path, project_id=project_id, project_root=project_root)
                file_record = self._lookup_file_record(connection, old_subject, include_deleted=True)
                if file_record is None:
                    continue
                self._move_file_record(connection, file_record.file_key, project_id, old_subject, new_subject, changed_at)
            connection.commit()

    def record_deleted_path(
        self,
        *,
        project_id: str,
        deleted_path: str,
        project_root: Optional[str] = None,
        deleted_at: str,
    ) -> None:
        subject = self.resolve_subject(deleted_path, project_id=project_id, project_root=project_root)
        absolute_glob = f"{subject.file_path}/%"
        relative_glob = f"{subject.relative_path}/%"
        with self._schema.connect() as connection:
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
                    subject.file_path,
                    absolute_glob,
                    subject.relative_path,
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
                    (deleted_at, deleted_at, str(row["file_key"])),
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
                        deleted_at,
                    ),
                )
            connection.commit()

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
            (file_key, subject.project_id, subject.file_path, subject.relative_path, timestamp),
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
        record = file_record_from_row(row)
        if record.is_deleted and not include_deleted:
            return None
        return record

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
        if previous_absolute_path == subject.file_path and previous_relative_path == subject.relative_path:
            connection.execute(
                """
                UPDATE files
                SET is_deleted = 0, deleted_at = NULL, updated_at = ?
                WHERE file_key = ?
                """,
                (timestamp, file_key),
            )
            return
        old_subject = ResolvedHistorySubject(
            project_id=subject.project_id,
            project_root=subject.project_root,
            file_path=previous_absolute_path,
            relative_path=previous_relative_path,
            display_path=previous_relative_path,
        )
        self._move_file_record(connection, file_key, subject.project_id, old_subject, subject, timestamp)

    def _move_file_record(
        self,
        connection: sqlite3.Connection,
        file_key: str,
        project_id: str,
        old_subject: ResolvedHistorySubject,
        new_subject: ResolvedHistorySubject,
        timestamp: str,
    ) -> None:
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
            (new_subject.file_path, new_subject.relative_path, new_subject.display_path, timestamp, file_key),
        )
        connection.execute(
            """
            UPDATE drafts
            SET absolute_path = ?, relative_path = ?
            WHERE file_key = ?
            """,
            (new_subject.file_path, new_subject.relative_path, file_key),
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
                project_id,
                old_subject.file_path,
                new_subject.file_path,
                old_subject.relative_path,
                new_subject.relative_path,
                timestamp,
            ),
        )

    def _prune_file_checkpoints(
        self,
        connection: sqlite3.Connection,
        file_key: str,
        retention_policy: LocalHistoryRetentionPolicy,
    ) -> None:
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
            retention_policy,
        )
        if not prune_ids:
            return
        placeholders = ",".join("?" for _ in prune_ids)
        connection.execute(
            f"DELETE FROM checkpoints WHERE revision_id IN ({placeholders})",
            prune_ids,
        )

    @staticmethod
    def _upsert_project(
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

    @staticmethod
    def _ensure_transaction(
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


