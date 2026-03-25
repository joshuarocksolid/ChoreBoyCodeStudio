"""Unit tests for autosave draft persistence."""

import hashlib
import json
from pathlib import Path

import pytest

from app.persistence.autosave_store import AutosaveStore

pytestmark = pytest.mark.unit


def test_autosave_store_save_load_delete_cycle(tmp_path: Path) -> None:
    """Drafts should persist and be removable by file path."""
    file_path = tmp_path / "project" / "run.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("print('hello')\n", encoding="utf-8")
    store = AutosaveStore(state_root=tmp_path / "state")

    saved = store.save_draft(str(file_path), "print('draft')\n")
    loaded = store.load_draft(str(file_path))
    assert loaded is not None
    assert loaded.file_path == str(file_path.resolve())
    assert loaded.content == "print('draft')\n"
    assert loaded.saved_at == saved.saved_at

    store.delete_draft(str(file_path))
    assert store.load_draft(str(file_path)) is None


def test_autosave_store_lists_multiple_drafts(tmp_path: Path) -> None:
    """Draft listing should return deterministic persisted entries."""
    store = AutosaveStore(state_root=tmp_path / "state")
    alpha = tmp_path / "alpha.py"
    beta = tmp_path / "beta.py"
    alpha.write_text("a\n", encoding="utf-8")
    beta.write_text("b\n", encoding="utf-8")

    store.save_draft(str(alpha), "draft alpha")
    store.save_draft(str(beta), "draft beta")

    drafts = store.list_drafts()
    assert sorted(draft.file_path for draft in drafts) == sorted([str(alpha.resolve()), str(beta.resolve())])


def test_autosave_store_migrates_legacy_json_draft_on_load(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    file_path = tmp_path / "project" / "legacy.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("print('hello')\n", encoding="utf-8")
    normalized_path = str(file_path.resolve())
    digest = hashlib.sha256(normalized_path.encode("utf-8")).hexdigest()
    legacy_dir = state_root / "cache" / "autosave_drafts"
    legacy_dir.mkdir(parents=True)
    legacy_path = legacy_dir / f"{digest}.json"
    legacy_path.write_text(
        json.dumps(
            {
                "file_path": normalized_path,
                "content": "print('legacy draft')\n",
                "saved_at": "2026-03-24T10:00:00",
            }
        ),
        encoding="utf-8",
    )

    store = AutosaveStore(state_root=state_root)
    loaded = store.load_draft(str(file_path))

    assert loaded is not None
    assert loaded.content == "print('legacy draft')\n"
    assert legacy_path.exists() is False
    assert store.list_drafts()[0].file_path == normalized_path
