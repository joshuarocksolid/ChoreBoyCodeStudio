"""SQLite schema and connection management for local history."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Optional

from app.bootstrap.paths import PathInput, ensure_directory, global_history_dir, global_history_index_path

LOCAL_HISTORY_SCHEMA_VERSION = 1


class LocalHistorySchema:
    """Own the local-history SQLite database lifecycle."""

    def __init__(self, state_root: Optional[PathInput] = None) -> None:
        self._history_root = ensure_directory(global_history_dir(state_root))
        self._db_path = global_history_index_path(state_root)
        self.initialize()

    @property
    def history_root(self) -> Path:
        return self._history_root

    @property
    def db_path(self) -> Path:
        return self._db_path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self._db_path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def initialize(self) -> None:
        ensure_directory(self._db_path.parent)
        with self.connect() as connection:
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
