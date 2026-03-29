"""Integration tests for MainWindow local-history checkpoint capture."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.editors.editor_manager import EditorManager
from app.persistence.autosave_store import AutosaveStore
from app.persistence.local_history_store import LocalHistoryStore
from app.project.project_service import create_blank_project, open_project
from app.shell.main_window import MainWindow

pytestmark = pytest.mark.integration


def test_main_window_save_creates_local_history_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = tmp_path / "state"
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="History Save Project")
    file_path = project_root / "main.py"
    file_path.write_text("print('original')\n", encoding="utf-8")
    loaded_project = open_project(str(project_root.resolve()))
    local_history_store = LocalHistoryStore(state_root=state_root)
    autosave_store = AutosaveStore(state_root=state_root, history_store=local_history_store)
    manager = EditorManager()
    manager.open_file(str(file_path))
    manager.update_tab_content(str(file_path), "print('saved')\n")
    autosave_store.save_draft(
        str(file_path),
        "print('saved')\n",
        project_id=loaded_project.metadata.project_id,
        project_root=loaded_project.project_root,
    )

    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = loaded_project
    window_any._local_history_store = local_history_store
    window_any._autosave_store = autosave_store
    window_any._editor_manager = manager
    window_any._editor_tabs_widget = None
    window_any._pending_autosave_payloads = {}
    window_any._refresh_save_action_states = lambda: None
    window_any._update_editor_status_for_path = lambda *_args, **_kwargs: None
    window_any._render_lint_diagnostics_for_file = lambda *_args, **_kwargs: None
    window_any._start_symbol_indexing = lambda *_args, **_kwargs: None
    window_any._logger = SimpleNamespace(info=lambda *_a, **_kw: None, warning=lambda *_a, **_kw: None)
    window_any._tab_index_for_path = lambda _path: -1
    window_any._apply_save_transforms = lambda *_args, **_kwargs: None
    window_any._intelligence_runtime_settings = SimpleNamespace()
    window_any._background_tasks = SimpleNamespace(run=lambda **_kwargs: None)
    window_any._test_explorer_panel = None
    window_any._test_outcomes_by_node_id = {}

    monkeypatch.setattr("app.shell.main_window.should_refresh_index_after_save", lambda *_args, **_kwargs: False)
    monkeypatch.setattr("app.shell.main_window.QMessageBox.warning", lambda *_args, **_kwargs: None)

    assert MainWindow._save_tab(window, str(file_path)) is True

    checkpoints = local_history_store.list_checkpoints(
        str(file_path),
        project_id=loaded_project.metadata.project_id,
        project_root=loaded_project.project_root,
    )
    assert len(checkpoints) == 1
    assert local_history_store.load_checkpoint_content(checkpoints[0].revision_id) == "print('saved')\n"
    assert (
        autosave_store.load_draft(
            str(file_path),
            project_id=loaded_project.metadata.project_id,
            project_root=loaded_project.project_root,
        )
        is None
    )


def test_record_local_history_transaction_groups_multi_file_entries(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="History Transaction Project")
    alpha = project_root / "alpha.py"
    beta = project_root / "beta.py"
    alpha.write_text("ALPHA = 1\n", encoding="utf-8")
    beta.write_text("BETA = 1\n", encoding="utf-8")
    loaded_project = open_project(str(project_root.resolve()))
    local_history_store = LocalHistoryStore(state_root=state_root)

    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = loaded_project
    window_any._local_history_store = local_history_store
    window_any._logger = SimpleNamespace(info=lambda *_a, **_kw: None, warning=lambda *_a, **_kw: None)

    MainWindow._record_local_history_transaction(
        window,
        {
            str(alpha): "ALPHA = 2\n",
            str(beta): "BETA = 2\n",
        },
        source="quick_fix",
        label="Apply Safe Fixes",
    )

    alpha_checkpoints = local_history_store.list_checkpoints(
        str(alpha),
        project_id=loaded_project.metadata.project_id,
        project_root=loaded_project.project_root,
    )
    beta_checkpoints = local_history_store.list_checkpoints(
        str(beta),
        project_id=loaded_project.metadata.project_id,
        project_root=loaded_project.project_root,
    )

    assert len(alpha_checkpoints) == 1
    assert len(beta_checkpoints) == 1
    assert alpha_checkpoints[0].transaction_id is not None
    assert alpha_checkpoints[0].transaction_id == beta_checkpoints[0].transaction_id
