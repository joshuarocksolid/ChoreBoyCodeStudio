"""Runtime-parity coverage for local history state creation."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.persistence.local_history_store import LocalHistoryStore

pytestmark = pytest.mark.runtime_parity


def test_local_history_store_creates_visible_history_state_under_state_root(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("print('hello')\n", encoding="utf-8")
    store = LocalHistoryStore(state_root=state_root)

    store.save_draft(
        str(file_path),
        "print('draft')\n",
        project_id="proj_demo",
        project_root=str(project_root),
    )
    checkpoint = store.create_checkpoint(
        str(file_path),
        "print('saved')\n",
        project_id="proj_demo",
        project_root=str(project_root),
        source="save",
    )

    assert checkpoint is not None
    assert (state_root / "history").is_dir()
    assert (state_root / "history" / "index.sqlite3").exists()
    assert any(path.is_file() for path in (state_root / "history" / "blobs").rglob("*"))
