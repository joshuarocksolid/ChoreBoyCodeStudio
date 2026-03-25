"""Structured models for local history drafts, checkpoints, and file identity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

HISTORY_ENTRY_KIND_DRAFT = "draft"
HISTORY_ENTRY_KIND_CHECKPOINT = "checkpoint"


@dataclass(frozen=True)
class ResolvedHistorySubject:
    """Normalized file identity used by the local-history store."""

    project_id: str
    project_root: Optional[str]
    file_path: str
    relative_path: str
    display_path: str


@dataclass(frozen=True)
class HistoryFileRecord:
    """Current logical-file state tracked by local history."""

    file_key: str
    project_id: str
    file_path: str
    relative_path: str
    is_deleted: bool
    created_at: str
    updated_at: str
    deleted_at: Optional[str] = None


@dataclass(frozen=True)
class LocalHistoryDraft:
    """Transient crash-recovery draft entry."""

    file_key: str
    project_id: str
    file_path: str
    relative_path: str
    blob_sha256: str
    content: str
    saved_at: str


@dataclass(frozen=True)
class LocalHistoryCheckpoint:
    """Durable local-history checkpoint metadata."""

    revision_id: int
    file_key: str
    project_id: str
    file_path: str
    relative_path: str
    blob_sha256: str
    created_at: str
    source: str
    label: str = ""
    transaction_id: Optional[str] = None


@dataclass(frozen=True)
class LocalHistoryFileSummary:
    """Global searchable summary for one logical file timeline."""

    file_key: str
    project_id: str
    project_root: Optional[str]
    file_path: str
    relative_path: str
    display_path: str
    is_deleted: bool
    deleted_at: Optional[str]
    latest_revision_id: int
    latest_checkpoint_at: str
    latest_label: str
    latest_source: str
    checkpoint_count: int
    path_aliases: tuple[str, ...] = ()
