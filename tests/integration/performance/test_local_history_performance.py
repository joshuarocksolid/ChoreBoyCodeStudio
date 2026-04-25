"""Performance checks for local-history query hot paths."""

from __future__ import annotations

from pathlib import Path
import time

import pytest

from app.persistence.history_retention import LocalHistoryRetentionPolicy
from app.persistence.local_history_store import LocalHistoryStore

pytestmark = [pytest.mark.integration, pytest.mark.performance, pytest.mark.timeout(180)]


def test_list_global_history_files_500_timelines_under_250ms(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    project_root = tmp_path / "project"
    project_root.mkdir()
    store = LocalHistoryStore(
        state_root=state_root,
        retention_policy=LocalHistoryRetentionPolicy(
            max_checkpoints_per_file=20,
            retention_days=365,
            max_tracked_file_bytes=1_000_000,
        ),
    )

    for file_index in range(500):
        file_path = project_root / f"file_{file_index:03d}.py"
        for revision in range(10):
            checkpoint = store.create_checkpoint(
                str(file_path),
                f"VALUE = {revision}\n",
                project_id="proj_perf",
                project_root=str(project_root),
                source="save",
                label=f"Revision {revision}",
                created_at=f"2026-04-24T10:{file_index % 60:02d}:{revision:02d}",
            )
            assert checkpoint is not None

    start = time.perf_counter()
    summaries = store.list_global_history_files(project_id="proj_perf")
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert len(summaries) == 500
    assert summaries[0].latest_revision_id is not None
    assert elapsed_ms <= 250.0
