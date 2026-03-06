"""Unit tests for autosave draft persistence."""

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
