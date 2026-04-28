"""Unit tests for the local history persistence layer."""

from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from app.persistence.history_retention import LocalHistoryRetentionPolicy
from app.persistence.history_models import (
    DRAFT_RECOVERY_POLICY_RESTORE_SILENTLY,
    DRAFT_SOURCE_KEPT_ON_EXIT,
)
from app.persistence.local_history_store import LocalHistoryStore

pytestmark = pytest.mark.unit


def test_local_history_store_save_and_load_draft_round_trip(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("print('original')\n", encoding="utf-8")
    store = LocalHistoryStore(state_root=state_root)

    saved = store.save_draft(
        str(file_path),
        "print('draft')\n",
        project_id="proj_demo",
        project_root=str(project_root),
    )
    loaded = store.load_draft(
        str(file_path),
        project_id="proj_demo",
        project_root=str(project_root),
    )

    assert loaded is not None
    assert loaded.file_key == saved.file_key
    assert loaded.project_id == "proj_demo"
    assert loaded.relative_path == "main.py"
    assert loaded.file_path == str(file_path.resolve())
    assert loaded.content == "print('draft')\n"
    assert store.list_drafts()[0].file_path == str(file_path.resolve())


def test_local_history_store_persists_draft_recovery_metadata(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("print('original')\n", encoding="utf-8")
    store = LocalHistoryStore(state_root=state_root)

    store.save_draft(
        str(file_path),
        "print('draft')\n",
        project_id="proj_demo",
        project_root=str(project_root),
        recovery_policy=DRAFT_RECOVERY_POLICY_RESTORE_SILENTLY,
        source=DRAFT_SOURCE_KEPT_ON_EXIT,
        last_known_mtime=123.5,
        session_id="session_1",
    )
    loaded = store.load_draft(
        str(file_path),
        project_id="proj_demo",
        project_root=str(project_root),
    )

    assert loaded is not None
    assert loaded.recovery_policy == DRAFT_RECOVERY_POLICY_RESTORE_SILENTLY
    assert loaded.source == DRAFT_SOURCE_KEPT_ON_EXIT
    assert loaded.last_known_mtime == 123.5
    assert loaded.session_id == "session_1"


def test_local_history_schema_migrates_v1_drafts_table(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    history_dir = state_root / "history"
    history_dir.mkdir(parents=True)
    db_path = history_dir / "index.sqlite3"
    with sqlite3.connect(str(db_path)) as connection:
        connection.execute("CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute(
            """
            CREATE TABLE drafts(
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
        connection.commit()

    store = LocalHistoryStore(state_root=state_root)

    with sqlite3.connect(str(store.db_path)) as connection:
        draft_columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(drafts)").fetchall()}
        schema_version = connection.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()[0]
    assert "recovery_policy" in draft_columns
    assert "source" in draft_columns
    assert schema_version == "2"


def test_local_history_store_creates_deduplicated_checkpoint_blobs(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("print('original')\n", encoding="utf-8")
    store = LocalHistoryStore(
        state_root=state_root,
        retention_policy=LocalHistoryRetentionPolicy(
            max_checkpoints_per_file=50,
            retention_days=365,
            max_tracked_file_bytes=1_000_000,
        ),
    )

    first = store.create_checkpoint(
        str(file_path),
        "print('saved')\n",
        project_id="proj_demo",
        project_root=str(project_root),
        source="save",
        created_at="2026-03-24T10:00:00",
    )
    second = store.create_checkpoint(
        str(file_path),
        "print('saved')\n",
        project_id="proj_demo",
        project_root=str(project_root),
        source="save",
        created_at="2026-03-24T10:01:00",
    )

    assert first is not None
    assert second is not None
    assert first.blob_sha256 == second.blob_sha256
    assert store.load_checkpoint_content(first.revision_id) == "print('saved')\n"
    assert store.blob_path(first.blob_sha256).exists()
    assert len([path for path in store.blobs_root.rglob("*") if path.is_file()]) == 1


def test_local_history_store_remaps_file_lineage_and_tracks_deletion(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    project_root = tmp_path / "project"
    project_root.mkdir()
    original_path = project_root / "pkg" / "module.py"
    renamed_path = project_root / "pkg" / "renamed.py"
    original_path.parent.mkdir(parents=True)
    original_path.write_text("VALUE = 1\n", encoding="utf-8")
    store = LocalHistoryStore(
        state_root=state_root,
        retention_policy=LocalHistoryRetentionPolicy(
            max_checkpoints_per_file=50,
            retention_days=365,
            max_tracked_file_bytes=1_000_000,
        ),
    )

    original_checkpoint = store.create_checkpoint(
        str(original_path),
        "VALUE = 1\n",
        project_id="proj_demo",
        project_root=str(project_root),
        source="save",
        created_at="2026-03-24T10:00:00",
    )
    assert original_checkpoint is not None

    store.remap_file_lineage(
        project_id="proj_demo",
        project_root=str(project_root),
        path_mapping={str(original_path): str(renamed_path)},
        changed_at="2026-03-24T10:05:00",
    )

    renamed_checkpoint = store.create_checkpoint(
        str(renamed_path),
        "VALUE = 2\n",
        project_id="proj_demo",
        project_root=str(project_root),
        source="save",
        created_at="2026-03-24T10:06:00",
    )
    assert renamed_checkpoint is not None
    assert renamed_checkpoint.file_key == original_checkpoint.file_key

    checkpoints = store.list_checkpoints(
        str(renamed_path),
        project_id="proj_demo",
        project_root=str(project_root),
    )
    assert [entry.relative_path for entry in checkpoints] == ["pkg/renamed.py", "pkg/module.py"]

    store.record_deleted_path(
        project_id="proj_demo",
        project_root=str(project_root),
        deleted_path=str(renamed_path),
        deleted_at="2026-03-24T10:07:00",
    )

    file_record = store.get_file_record(
        str(renamed_path),
        project_id="proj_demo",
        project_root=str(project_root),
        include_deleted=True,
    )
    assert file_record is not None
    assert file_record.is_deleted is True


def test_local_history_store_prunes_old_checkpoints_per_file(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("print('v1')\n", encoding="utf-8")
    store = LocalHistoryStore(
        state_root=state_root,
        retention_policy=LocalHistoryRetentionPolicy(
            max_checkpoints_per_file=2,
            retention_days=365,
            max_tracked_file_bytes=1024,
        ),
    )

    store.create_checkpoint(
        str(file_path),
        "print('v1')\n",
        project_id="proj_demo",
        project_root=str(project_root),
        source="save",
        created_at="2026-03-24T10:00:00",
    )
    store.create_checkpoint(
        str(file_path),
        "print('v2')\n",
        project_id="proj_demo",
        project_root=str(project_root),
        source="save",
        created_at="2026-03-24T10:01:00",
    )
    store.create_checkpoint(
        str(file_path),
        "print('v3')\n",
        project_id="proj_demo",
        project_root=str(project_root),
        source="save",
        created_at="2026-03-24T10:02:00",
    )

    checkpoints = store.list_checkpoints(
        str(file_path),
        project_id="proj_demo",
        project_root=str(project_root),
    )

    assert [store.load_checkpoint_content(entry.revision_id) for entry in checkpoints] == [
        "print('v3')\n",
        "print('v2')\n",
    ]


def test_local_history_store_lists_global_history_files_with_aliases_and_deleted_state(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    project_root = tmp_path / "project"
    project_root.mkdir()
    original_path = project_root / "pkg" / "module.py"
    renamed_path = project_root / "pkg" / "renamed.py"
    original_path.parent.mkdir(parents=True)
    original_path.write_text("VALUE = 1\n", encoding="utf-8")
    store = LocalHistoryStore(
        state_root=state_root,
        retention_policy=LocalHistoryRetentionPolicy(
            max_checkpoints_per_file=50,
            retention_days=365,
            max_tracked_file_bytes=1_000_000,
        ),
    )

    store.create_checkpoint(
        str(original_path),
        "VALUE = 1\n",
        project_id="proj_demo",
        project_root=str(project_root),
        source="save",
        label="Original Save",
        created_at="2026-03-24T10:00:00",
    )
    store.remap_file_lineage(
        project_id="proj_demo",
        project_root=str(project_root),
        path_mapping={str(original_path): str(renamed_path)},
        changed_at="2026-03-24T10:05:00",
    )
    store.create_checkpoint(
        str(renamed_path),
        "VALUE = 2\n",
        project_id="proj_demo",
        project_root=str(project_root),
        source="save",
        label="Renamed Save",
        created_at="2026-03-24T10:06:00",
    )
    store.record_deleted_path(
        project_id="proj_demo",
        project_root=str(project_root),
        deleted_path=str(renamed_path),
        deleted_at="2026-03-24T10:07:00",
    )

    summaries = store.list_global_history_files(project_id="proj_demo")

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.project_root == str(project_root.resolve())
    assert summary.file_path == str(renamed_path.resolve())
    assert summary.relative_path == "pkg/renamed.py"
    assert summary.is_deleted is True
    assert summary.latest_label == "Renamed Save"
    assert summary.latest_checkpoint_at == "2026-03-24T10:06:00"
    assert summary.checkpoint_count == 2
    assert "pkg/module.py" in summary.path_aliases
    assert "pkg/renamed.py" in summary.path_aliases


def test_local_history_store_skips_excluded_and_oversized_checkpoints(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    project_root = tmp_path / "project"
    project_root.mkdir()
    excluded_path = project_root / "skip.py"
    excluded_path.write_text("print('skip')\n", encoding="utf-8")
    large_path = project_root / "large.py"
    large_path.write_text("x" * 32, encoding="utf-8")
    store = LocalHistoryStore(
        state_root=state_root,
        retention_policy=LocalHistoryRetentionPolicy(
            max_checkpoints_per_file=10,
            retention_days=30,
            max_tracked_file_bytes=16,
            excluded_glob_patterns=("skip.py",),
        ),
    )

    assert store.checkpoint_skip_reason(
        str(excluded_path),
        "print('skip')\n",
        project_root=str(project_root),
    ) == "excluded"
    assert store.create_checkpoint(
        str(excluded_path),
        "print('skip')\n",
        project_id="proj_demo",
        project_root=str(project_root),
        source="save",
    ) is None

    assert store.checkpoint_skip_reason(
        str(large_path),
        "x" * 32,
        project_root=str(project_root),
    ) == "too_large"
    assert store.create_checkpoint(
        str(large_path),
        "x" * 32,
        project_id="proj_demo",
        project_root=str(project_root),
        source="save",
    ) is None


def test_local_history_store_set_retention_policy_can_prune_existing_history(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("print('v1')\n", encoding="utf-8")
    store = LocalHistoryStore(
        state_root=state_root,
        retention_policy=LocalHistoryRetentionPolicy(
            max_checkpoints_per_file=10,
            retention_days=365,
            max_tracked_file_bytes=1024,
        ),
    )

    for index in range(3):
        store.create_checkpoint(
            str(file_path),
            f"print('v{index}')\n",
            project_id="proj_demo",
            project_root=str(project_root),
            source="save",
            created_at=f"2026-03-24T10:0{index}:00",
        )

    store.set_retention_policy(
        LocalHistoryRetentionPolicy(
            max_checkpoints_per_file=2,
            retention_days=365,
            max_tracked_file_bytes=1024,
        ),
        apply_now=True,
    )

    checkpoints = store.list_checkpoints(
        str(file_path),
        project_id="proj_demo",
        project_root=str(project_root),
    )
    assert len(checkpoints) == 2
