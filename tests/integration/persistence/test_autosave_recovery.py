"""Integration test for draft recovery semantics after simulated crash."""

from pathlib import Path

import pytest

from app.editors.editor_manager import EditorManager
from app.persistence.autosave_store import AutosaveStore

pytestmark = pytest.mark.integration


def test_autosave_recovery_restores_unsaved_draft_after_simulated_crash(tmp_path: Path) -> None:
    """Unsaved edits should be recoverable on next session startup."""
    state_root = tmp_path / "state"
    file_path = tmp_path / "project" / "run.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("print('original')\n", encoding="utf-8")

    store = AutosaveStore(state_root=state_root)
    manager = EditorManager()
    opened = manager.open_file(str(file_path))
    manager.update_tab_content(str(file_path), "print('unsaved change')\n")
    store.save_draft(str(file_path), opened.tab.current_content)

    # Simulate abnormal crash: no save, process exits.
    restarted_manager = EditorManager()
    restarted_opened = restarted_manager.open_file(str(file_path))
    recovered_draft = store.load_draft(str(file_path))

    assert restarted_opened.tab.current_content == "print('original')\n"
    assert recovered_draft is not None
    assert recovered_draft.content == "print('unsaved change')\n"
