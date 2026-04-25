"""File identity and alias helpers for local history."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
from typing import Optional

from app.bootstrap.paths import project_manifest_path
from app.persistence.history_models import ResolvedHistorySubject
from app.project.project_manifest import ensure_project_id


def resolve_history_subject(
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
            if inferred_project_id is None:
                inferred_project_id = fallback_project_id_for_root(inferred_project_root)
            return ResolvedHistorySubject(
                project_id=inferred_project_id,
                project_root=inferred_project_root,
                file_path=normalized_path,
                relative_path=relative_path,
                display_path=relative_path,
            )
        except ValueError:
            inferred_project_root = None

    if inferred_project_id is None or inferred_project_root is None:
        discovered = discover_project_context(Path(normalized_path))
        if discovered is not None:
            discovered_project_id, discovered_project_root = discovered
            if inferred_project_id is None:
                inferred_project_id = discovered_project_id
            if inferred_project_root is None:
                inferred_project_root = discovered_project_root

    if inferred_project_root is not None:
        relative_path = Path(normalized_path).relative_to(Path(inferred_project_root)).as_posix()
        return ResolvedHistorySubject(
            project_id=inferred_project_id or fallback_project_id_for_root(inferred_project_root),
            project_root=inferred_project_root,
            file_path=normalized_path,
            relative_path=relative_path,
            display_path=relative_path,
        )

    external_project_id = inferred_project_id or fallback_project_id_for_path(normalized_path)
    return ResolvedHistorySubject(
        project_id=external_project_id,
        project_root=None,
        file_path=normalized_path,
        relative_path=normalized_path,
        display_path=normalized_path,
    )


def discover_project_context(file_path: Path) -> Optional[tuple[str, str]]:
    for parent in [file_path.parent, *file_path.parents]:
        manifest_path = project_manifest_path(parent)
        if not manifest_path.exists() or not manifest_path.is_file():
            continue
        metadata = ensure_project_id(manifest_path)
        return metadata.project_id, str(parent.resolve())
    return None


def path_aliases_for_file_keys(
    connection: sqlite3.Connection,
    file_keys: list[str],
) -> dict[str, tuple[str, ...]]:
    if not file_keys:
        return {}
    unique_file_keys = list(dict.fromkeys(file_keys))
    alias_lists: dict[str, list[str]] = {file_key: [] for file_key in unique_file_keys}
    alias_seen: dict[str, set[str]] = {file_key: set() for file_key in unique_file_keys}
    placeholders = ", ".join("?" for _ in unique_file_keys)
    current_rows = connection.execute(
        f"""
        SELECT file_key, current_absolute_path, current_relative_path, current_display_path
        FROM files
        WHERE file_key IN ({placeholders})
        """,
        unique_file_keys,
    ).fetchall()
    for row in current_rows:
        _append_alias_values(
            alias_lists=alias_lists,
            alias_seen=alias_seen,
            file_key=str(row["file_key"]),
            values=(row["current_relative_path"], row["current_display_path"], row["current_absolute_path"]),
        )

    lineage_rows = connection.execute(
        f"""
        SELECT file_key, previous_absolute_path, absolute_path, previous_relative_path, relative_path
        FROM file_lineage
        WHERE file_key IN ({placeholders})
        ORDER BY file_key, changed_at DESC, event_id DESC
        """,
        unique_file_keys,
    ).fetchall()
    for row in lineage_rows:
        _append_alias_values(
            alias_lists=alias_lists,
            alias_seen=alias_seen,
            file_key=str(row["file_key"]),
            values=(row["previous_relative_path"], row["relative_path"], row["previous_absolute_path"], row["absolute_path"]),
        )
    return {file_key: tuple(alias_lists.get(file_key, ())) for file_key in unique_file_keys}


def fallback_project_id_for_root(project_root: str) -> str:
    digest = hashlib.sha256(project_root.encode("utf-8")).hexdigest()[:16]
    return f"proj_root_{digest}"


def fallback_project_id_for_path(file_path: str) -> str:
    parent_path = str(Path(file_path).expanduser().resolve().parent)
    digest = hashlib.sha256(parent_path.encode("utf-8")).hexdigest()[:16]
    return f"proj_external_{digest}"


def _append_alias_values(
    *,
    alias_lists: dict[str, list[str]],
    alias_seen: dict[str, set[str]],
    file_key: str,
    values: tuple[object, ...],
) -> None:
    aliases = alias_lists.setdefault(file_key, [])
    seen = alias_seen.setdefault(file_key, set())
    for value in values:
        if value is None:
            continue
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        aliases.append(normalized)
