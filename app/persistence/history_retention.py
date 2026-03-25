"""Retention defaults and pruning helpers for local history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Optional

from app.core import constants

DEFAULT_LOCAL_HISTORY_MERGE_WINDOW_SECONDS = 30
DEFAULT_LOCAL_HISTORY_MAX_CHECKPOINTS_PER_FILE = constants.UI_LOCAL_HISTORY_MAX_CHECKPOINTS_PER_FILE_DEFAULT
DEFAULT_LOCAL_HISTORY_RETENTION_DAYS = constants.UI_LOCAL_HISTORY_RETENTION_DAYS_DEFAULT
DEFAULT_LOCAL_HISTORY_MAX_TRACKED_FILE_BYTES = constants.UI_LOCAL_HISTORY_MAX_TRACKED_FILE_BYTES_DEFAULT


@dataclass(frozen=True)
class LocalHistoryRetentionPolicy:
    """Bounded storage policy for local history."""

    merge_window_seconds: int = DEFAULT_LOCAL_HISTORY_MERGE_WINDOW_SECONDS
    max_checkpoints_per_file: int = DEFAULT_LOCAL_HISTORY_MAX_CHECKPOINTS_PER_FILE
    retention_days: int = DEFAULT_LOCAL_HISTORY_RETENTION_DAYS
    max_tracked_file_bytes: int = DEFAULT_LOCAL_HISTORY_MAX_TRACKED_FILE_BYTES
    excluded_glob_patterns: tuple[str, ...] = constants.UI_LOCAL_HISTORY_EXCLUDE_PATTERNS_DEFAULT


def default_local_history_retention_policy() -> LocalHistoryRetentionPolicy:
    """Return the default retention policy."""
    return LocalHistoryRetentionPolicy()


def should_track_text(content: str, policy: LocalHistoryRetentionPolicy) -> bool:
    """Return True when content fits the configured size guardrail."""
    return len(content.encode("utf-8")) <= max(0, int(policy.max_tracked_file_bytes))


def should_track_path(
    file_path: str,
    policy: LocalHistoryRetentionPolicy,
    *,
    project_root: Optional[str] = None,
) -> bool:
    """Return True when a file path is not excluded from local history."""
    normalized_patterns = [pattern.strip() for pattern in policy.excluded_glob_patterns if pattern.strip()]
    if not normalized_patterns:
        return True

    resolved_path = Path(file_path).expanduser().resolve()
    candidates = {
        resolved_path.as_posix(),
        resolved_path.name,
    }
    if project_root is not None:
        try:
            relative_path = resolved_path.relative_to(Path(project_root).expanduser().resolve()).as_posix()
        except ValueError:
            relative_path = None
        if relative_path:
            candidates.add(relative_path)

    for pattern in normalized_patterns:
        if any(fnmatchcase(candidate, pattern) for candidate in candidates):
            return False
    return True


def checkpoint_skip_reason(
    file_path: str,
    content: str,
    policy: LocalHistoryRetentionPolicy,
    *,
    project_root: Optional[str] = None,
) -> str:
    """Return a machine-readable reason when checkpoint capture should be skipped."""
    if not should_track_path(file_path, policy, project_root=project_root):
        return "excluded"
    if not should_track_text(content, policy):
        return "too_large"
    return ""


def checkpoint_ids_to_prune(
    revisions_newest_first: list[tuple[int, str]],
    policy: LocalHistoryRetentionPolicy,
    *,
    now: Optional[datetime] = None,
) -> list[int]:
    """Return checkpoint revision ids that should be pruned."""
    prune_ids: list[int] = []
    max_entries = max(0, int(policy.max_checkpoints_per_file))
    if max_entries and len(revisions_newest_first) > max_entries:
        prune_ids.extend(revision_id for revision_id, _created_at in revisions_newest_first[max_entries:])

    retention_days = max(0, int(policy.retention_days))
    if retention_days <= 0:
        return sorted(set(prune_ids))

    reference_time = now or datetime.now()
    cutoff = reference_time - timedelta(days=retention_days)
    for revision_id, created_at in revisions_newest_first:
        try:
            created_dt = datetime.fromisoformat(created_at)
        except ValueError:
            continue
        if created_dt < cutoff:
            prune_ids.append(revision_id)
    return sorted(set(prune_ids))
