"""Unit tests for editor tab inventory polling tiers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from app.core.models import LoadedProject, ProjectMetadata
from app.editors.editor_manager import EditorManager
from app.shell.editor_tab_workflow import EditorTabWorkflow

pytestmark = pytest.mark.unit


def _loaded_project(tmp_path: Path) -> LoadedProject:
    metadata = ProjectMetadata(schema_version=2, name="demo")
    return LoadedProject(
        project_root=str(tmp_path),
        manifest_path=str(tmp_path / "cbcs" / "project.json"),
        metadata=metadata,
        entries=(),
    )


def _workflow(host: MagicMock) -> EditorTabWorkflow:
    editor_manager = cast(EditorManager, SimpleNamespace(stale_open_paths=lambda: []))
    return EditorTabWorkflow(
        host=host,
        editor_manager=editor_manager,
        editor_tabs_coordinator=cast(
            Any,
            SimpleNamespace(
                buffer_revision=lambda _path: None,
                advance_buffer_revision=lambda _path: 0,
                tab_index_for_path=lambda _path: -1,
                refresh_tab_presentation=lambda _path: None,
            ),
        ),
        save_workflow=SimpleNamespace(),
        debug_control_workflow=SimpleNamespace(breakpoint_store=SimpleNamespace()),
        external_file_change_workflow=SimpleNamespace(check_and_handle=lambda *_args, **_kwargs: None),
        editor_sync_workflow=SimpleNamespace(apply_disk_content=lambda *_args, **_kwargs: None),
    )


def test_poll_skips_reindex_when_tree_changes_but_python_fingerprint_is_stable(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text("print('hi')\n", encoding="utf-8")
    loaded = _loaded_project(project_root)

    host = MagicMock()
    host.loaded_project.return_value = loaded
    host.project_tree_structure_signature.return_value = ("main.py",)
    host.project_inventory_generation.return_value = 1
    host.project_inventory_tree_signature.return_value = ("main.py",)
    host.project_python_paths_fingerprint.side_effect = [
        (str((project_root / "main.py").resolve()),),
        (str((project_root / "main.py").resolve()),),
    ]
    host.load_effective_exclude_patterns.return_value = []

    workflow = _workflow(host)
    workflow._poll_workflow.scan_project_tree_signature = MagicMock(  # type: ignore[method-assign]
        return_value=("main.py", "docs/readme.md"),
    )

    workflow.poll_external_file_changes()

    host.rescan_project_from_disk.assert_called_once_with(reload_plugins=False, reindex=False)
    host.start_symbol_indexing_for_loaded_project.assert_not_called()


def test_poll_ignores_cbcs_cache_churn_without_rescan(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text("print('hi')\n", encoding="utf-8")
    loaded = _loaded_project(project_root)

    host = MagicMock()
    host.loaded_project.return_value = loaded
    host.project_tree_structure_signature.return_value = ("main.py",)
    host.project_inventory_generation.return_value = 1
    host.project_inventory_tree_signature.return_value = ("main.py",)
    host.project_python_paths_fingerprint.return_value = (str((project_root / "main.py").resolve()),)
    host.load_effective_exclude_patterns.return_value = []

    workflow = _workflow(host)
    workflow._poll_workflow.reset_poll_state()
    workflow._poll_workflow.scan_project_tree_signature = MagicMock(  # type: ignore[method-assign]
        return_value=("main.py",),
    )

    workflow.poll_external_file_changes()

    host.rescan_project_from_disk.assert_not_called()
    host.start_symbol_indexing_for_loaded_project.assert_not_called()


def test_poll_skips_tree_walk_when_orchestrator_signature_is_stable(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    loaded = _loaded_project(project_root)

    host = MagicMock()
    host.loaded_project.return_value = loaded
    stable_signature = ("main.py",)
    host.project_tree_structure_signature.return_value = stable_signature
    host.project_inventory_generation.return_value = 3
    host.project_inventory_tree_signature.return_value = stable_signature
    host.project_python_paths_fingerprint.return_value = ()
    host.load_effective_exclude_patterns.return_value = []

    workflow = _workflow(host)
    workflow._poll_workflow.reset_poll_state()
    workflow._poll_workflow._poll_signature_stable = True
    workflow._poll_workflow._last_poll_inventory_generation = 3
    workflow._poll_workflow._last_poll_project_mtime = Path(loaded.project_root).stat().st_mtime
    scan_mock = MagicMock()
    workflow._poll_workflow.scan_project_tree_signature = scan_mock  # type: ignore[method-assign]

    workflow.poll_external_file_changes()

    scan_mock.assert_not_called()


def test_poll_reindexes_when_python_fingerprint_changes(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text("print('hi')\n", encoding="utf-8")
    loaded = _loaded_project(project_root)

    host = MagicMock()
    host.loaded_project.return_value = loaded
    host.project_tree_structure_signature.return_value = ("main.py",)
    host.project_inventory_generation.return_value = 1
    host.project_inventory_tree_signature.return_value = ("main.py",)
    host.project_python_paths_fingerprint.side_effect = [
        (str((project_root / "main.py").resolve()),),
        (
            str((project_root / "main.py").resolve()),
            str((project_root / "new_module.py").resolve()),
        ),
    ]
    host.load_effective_exclude_patterns.return_value = []

    workflow = _workflow(host)
    workflow._poll_workflow.scan_project_tree_signature = MagicMock(  # type: ignore[method-assign]
        return_value=("main.py", "new_module.py"),
    )

    workflow.poll_external_file_changes()

    host.rescan_project_from_disk.assert_called_once_with(reload_plugins=False, reindex=False)
    host.start_symbol_indexing_for_loaded_project.assert_called_once()


def test_scan_project_tree_signature_uses_inventory_walk(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text("print('hi')\n", encoding="utf-8")
    loaded = _loaded_project(project_root)

    host = MagicMock()
    host.load_effective_exclude_patterns.return_value = ["vendor"]
    host.project_inventory_tree_signature.return_value = None

    workflow = _workflow(host)
    with patch("app.shell.editor_tab_poll_workflow.iter_project_entries") as iter_mock:
        from app.core.models import ProjectFileEntry

        iter_mock.return_value = [
            ProjectFileEntry(
                relative_path="main.py",
                absolute_path=str(project_root / "main.py"),
                is_directory=False,
            )
        ]
        signature = workflow.scan_project_tree_signature(loaded)

    assert "main.py" in signature
    iter_mock.assert_called_once()
    host.load_effective_exclude_patterns.assert_called_once_with(str(project_root))
