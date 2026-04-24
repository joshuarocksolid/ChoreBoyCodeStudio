"""Pure helpers for writing local-history checkpoints from save flows.

These functions encapsulate the persistence-layer side of the editor save
pipeline so it can be exercised without the Qt shell.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Mapping, Optional

from app.persistence.local_history_store import LocalHistoryStore


def resolve_local_history_context(
    file_path: str,
    *,
    project_id: Optional[str],
    project_root: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Return ``(project_id, project_root)`` if ``file_path`` lives under ``project_root``.

    Files outside the project root (or when no project is loaded) get ``(None, None)``
    so the history store skips project-aware bookkeeping.
    """
    if project_id is None or project_root is None:
        return (None, None)
    try:
        resolved_file = Path(file_path).expanduser().resolve()
        resolved_root = Path(project_root).expanduser().resolve()
        resolved_file.relative_to(resolved_root)
    except (OSError, ValueError):
        return (None, None)
    return (project_id, str(resolved_root))


def record_local_history_checkpoint(
    history_store: Optional[LocalHistoryStore],
    *,
    file_path: str,
    content: str,
    project_id: Optional[str],
    project_root: Optional[str],
    source: str,
    label: str = "",
    transaction_id: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> Optional[object]:
    """Write a single checkpoint, swallowing/logging persistence errors.

    Returns the created checkpoint or ``None`` when the store skipped or failed.
    """
    if history_store is None:
        return None
    project_id, project_root = resolve_local_history_context(
        file_path,
        project_id=project_id,
        project_root=project_root,
    )
    try:
        return history_store.create_checkpoint(
            file_path,
            content,
            project_id=project_id,
            project_root=project_root,
            source=source,
            label=label,
            transaction_id=transaction_id,
        )
    except Exception:
        if logger is not None:
            logger.warning("Local history checkpoint failed for %s", file_path, exc_info=True)
        return None


def record_local_history_transaction(
    history_store: Optional[LocalHistoryStore],
    payloads_by_path: Mapping[str, str],
    *,
    project_id: Optional[str],
    project_root: Optional[str],
    source: str,
    label: str,
    logger: Optional[logging.Logger] = None,
) -> None:
    """Group multi-file checkpoints under a shared transaction id.

    Single-file payloads use ``transaction_id=None``; >1 entries get a fresh
    ``txn_<uuid>`` so consumers can group related restores.
    """
    normalized = {path: payload for path, payload in payloads_by_path.items() if payload is not None}
    if not normalized:
        return
    transaction_id = f"txn_{uuid.uuid4().hex}" if len(normalized) > 1 else None
    for file_path, payload in normalized.items():
        record_local_history_checkpoint(
            history_store,
            file_path=file_path,
            content=payload,
            project_id=project_id,
            project_root=project_root,
            source=source,
            label=label,
            transaction_id=transaction_id,
            logger=logger,
        )

