"""SQLite row adapters for local-history models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import sqlite3

from app.persistence.history_models import (
    HistoryFileRecord,
    LocalHistoryCheckpoint,
    LocalHistoryFileSummary,
)


@dataclass(frozen=True)
class LocalHistoryDraftRecord:
    file_key: str
    project_id: str
    file_path: str
    relative_path: str
    blob_sha256: str
    saved_at: str


def draft_record_from_row(row: sqlite3.Row | None) -> Optional[LocalHistoryDraftRecord]:
    if row is None:
        return None
    return LocalHistoryDraftRecord(
        file_key=str(row["file_key"]),
        project_id=str(row["project_id"]),
        file_path=str(row["absolute_path"]),
        relative_path=str(row["relative_path"]),
        blob_sha256=str(row["blob_sha256"]),
        saved_at=str(row["saved_at"]),
    )


def file_record_from_row(row: sqlite3.Row) -> HistoryFileRecord:
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


def checkpoint_from_row(row: sqlite3.Row) -> LocalHistoryCheckpoint:
    return LocalHistoryCheckpoint(
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


def summary_from_row(
    row: sqlite3.Row,
    alias_map: dict[str, tuple[str, ...]],
) -> LocalHistoryFileSummary:
    file_key = str(row["file_key"])
    return LocalHistoryFileSummary(
        file_key=file_key,
        project_id=str(row["project_id"]),
        project_root=None if row["project_root"] is None else str(row["project_root"]),
        file_path=str(row["current_absolute_path"]),
        relative_path=str(row["current_relative_path"]),
        display_path=str(row["current_display_path"]),
        is_deleted=bool(int(row["is_deleted"])),
        deleted_at=None if row["deleted_at"] is None else str(row["deleted_at"]),
        latest_revision_id=int(row["latest_revision_id"]),
        latest_checkpoint_at=str(row["latest_checkpoint_at"]),
        latest_label=str(row["latest_label"] or ""),
        latest_source=str(row["latest_source"]),
        checkpoint_count=int(row["checkpoint_count"]),
        path_aliases=alias_map.get(file_key, ()),
    )
