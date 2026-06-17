"""Unit tests for project tree expansion/selection preservation."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication, QTreeWidgetItem  # noqa: E402

from app.core.models import LoadedProject, ProjectFileEntry, ProjectMetadata  # noqa: E402
from app.shell.editor_tab_workflow import EditorTabWorkflow
from app.shell.editor_tab_content_registry import EditorTabContentRegistry
from app.shell.main_window_editor_tab_host import MainWindowEditorTabHost
from app.shell.main_window import MainWindow  # noqa: E402
from app.shell.project_tree_utils import filter_tree_signature_entries  # noqa: E402
from app.shell.tree_item_roles import TREE_ROLE_IS_DIRECTORY, TREE_ROLE_RELATIVE_PATH  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


def _find_item_by_relative_path(window: MainWindow, relative_path: str) -> QTreeWidgetItem | None:
    for item in window._project_tree_ui_workflow.iter_project_tree_items():  # noqa: SLF001 - intentional tree-state verification
        if str(item.data(0, TREE_ROLE_RELATIVE_PATH) or "") == relative_path:
            return item
    return None


def test_populate_project_tree_defaults_to_collapsed(tmp_path: Path, _qapp: QApplication) -> None:
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        project_root = tmp_path / "project"
        loaded_project = LoadedProject(
            project_root=str(project_root.resolve()),
            manifest_path=str((project_root / "cbcs" / "project.json").resolve()),
            metadata=ProjectMetadata(schema_version=1, name="Tree", default_entry="src/main.py"),
            entries=[
                ProjectFileEntry(relative_path="src", absolute_path=str((project_root / "src").resolve()), is_directory=True),
                ProjectFileEntry(relative_path="src/main.py", absolute_path=str((project_root / "src/main.py").resolve()), is_directory=False),
                ProjectFileEntry(relative_path="docs", absolute_path=str((project_root / "docs").resolve()), is_directory=True),
                ProjectFileEntry(relative_path="docs/readme.md", absolute_path=str((project_root / "docs/readme.md").resolve()), is_directory=False),
            ],
        )
        window._loaded_project = loaded_project  # noqa: SLF001 - test harness setup
        window._project_tree_ui_workflow.populate_project_tree(loaded_project)  # noqa: SLF001

        for item in window._project_tree_ui_workflow.iter_project_tree_items():  # noqa: SLF001
            if bool(item.data(0, TREE_ROLE_IS_DIRECTORY)):
                assert item.isExpanded() is False
    finally:
        shutdown_main_window_for_test(window, _qapp)


def test_populate_project_tree_preserves_expansion_and_selection(tmp_path: Path, _qapp: QApplication) -> None:
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        project_root = tmp_path / "project"
        loaded_project = LoadedProject(
            project_root=str(project_root.resolve()),
            manifest_path=str((project_root / "cbcs" / "project.json").resolve()),
            metadata=ProjectMetadata(schema_version=1, name="Tree", default_entry="src/main.py"),
            entries=[
                ProjectFileEntry(relative_path="src", absolute_path=str((project_root / "src").resolve()), is_directory=True),
                ProjectFileEntry(relative_path="src/main.py", absolute_path=str((project_root / "src/main.py").resolve()), is_directory=False),
                ProjectFileEntry(relative_path="docs", absolute_path=str((project_root / "docs").resolve()), is_directory=True),
                ProjectFileEntry(relative_path="docs/readme.md", absolute_path=str((project_root / "docs/readme.md").resolve()), is_directory=False),
            ],
        )
        window._loaded_project = loaded_project  # noqa: SLF001 - test harness setup
        window._project_tree_ui_workflow.populate_project_tree(loaded_project)  # noqa: SLF001 - direct tree population for state test

        docs_item = _find_item_by_relative_path(window, "docs")
        assert docs_item is not None
        docs_item.setExpanded(True)
        window._project_tree_presenter.ensure_children_loaded(docs_item)  # noqa: SLF001

        src_item = _find_item_by_relative_path(window, "src")
        docs_readme_item = _find_item_by_relative_path(window, "docs/readme.md")
        assert src_item is not None
        assert docs_readme_item is not None

        src_item.setExpanded(False)
        docs_readme_item.setSelected(True)

        window._project_tree_ui_workflow.populate_project_tree(loaded_project, preserve_state=True)  # noqa: SLF001

        restored_src = _find_item_by_relative_path(window, "src")
        restored_docs_readme = _find_item_by_relative_path(window, "docs/readme.md")
        assert restored_src is not None
        assert restored_docs_readme is not None
        assert restored_src.isExpanded() is False
        assert restored_docs_readme.isSelected() is True
    finally:
        shutdown_main_window_for_test(window, _qapp)


def _attach_poll_editor_tab_workflow(window_any: Any) -> EditorTabWorkflow:
    workflow = EditorTabWorkflow(
        host=MainWindowEditorTabHost(window_any),
        editor_manager=window_any._editor_manager,
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
    window_any._editor_tab_workflow = workflow
    return workflow


def test_poll_external_file_changes_reloads_project_tree_on_structure_change(tmp_path: Path) -> None:
    window_any = SimpleNamespace(
        _editor_manager=SimpleNamespace(
            stale_open_paths=lambda: [],
            active_tab=lambda: None,
        ),
    )
    project_root = tmp_path / "project"
    project_root.mkdir()
    loaded_project = LoadedProject(
        project_root=str(project_root),
        manifest_path=str(project_root / "cbcs" / "project.json"),
        metadata=ProjectMetadata(schema_version=1, name="Tree"),
        entries=[],
    )
    window_any._loaded_project = loaded_project
    window_any._project_tree_structure_signature = ("src", "src/main.py")
    rescan_calls: list[tuple[bool, bool]] = []
    reindex_calls: list[bool] = []
    window_any._project_inventory_orchestrator = SimpleNamespace(
        python_paths_fingerprint=lambda: ("src/main.py",),
        generation=1,
        tree_structure_signature=lambda: ("src", "src/main.py", "docs"),
        set_tree_structure_signature=lambda _sig: None,
    )
    window_any._markdown_panes_by_path = {}
    window_any._tab_content_registry = EditorTabContentRegistry(window_any._markdown_panes_by_path)
    window_any._editor_tab_factory = SimpleNamespace()
    window_any._file_project_commands_workflow = SimpleNamespace(
        load_effective_exclude_patterns=lambda _root: [],
    )
    window_any._intelligence_cache_workflow = SimpleNamespace(
        start_symbol_indexing=lambda *_args, **_kwargs: reindex_calls.append(True),
    )
    host = MainWindowEditorTabHost(window_any)
    host.rescan_project_from_disk = (  # type: ignore[method-assign]
        lambda *, reload_plugins, reindex: rescan_calls.append((reload_plugins, reindex))
    )
    host.start_symbol_indexing_for_loaded_project = (  # type: ignore[method-assign]
        lambda: reindex_calls.append(True)
    )
    workflow = EditorTabWorkflow(
        host=host,
        editor_manager=window_any._editor_manager,
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
    window_any._editor_tab_workflow = workflow

    workflow.poll_external_file_changes()

    assert rescan_calls == [(False, False)]
    assert reindex_calls == []


def test_poll_external_file_changes_ignores_run_artifact_writes(tmp_path: Path) -> None:
    """Run/debug sessions write under cbcs/runs/ and cbcs/logs/ on every start.
    Those writes must not trigger the project reload cascade (which clears the
    file tree, restarts the symbol indexer, etc.) — otherwise the file
    explorer's scroll position is reset every time the user runs a file.
    """
    window_any = SimpleNamespace(
        _editor_manager=SimpleNamespace(
            stale_open_paths=lambda: [],
            active_tab=lambda: None,
        ),
    )
    project_root = tmp_path / "project"
    project_root.mkdir()
    loaded_project = LoadedProject(
        project_root=str(project_root),
        manifest_path=str(project_root / "cbcs" / "project.json"),
        metadata=ProjectMetadata(schema_version=1, name="Tree"),
        entries=[],
    )
    window_any._loaded_project = loaded_project
    window_any._markdown_panes_by_path = {}
    window_any._tab_content_registry = EditorTabContentRegistry(window_any._markdown_panes_by_path)
    window_any._editor_tab_factory = SimpleNamespace()
    window_any._file_project_commands_workflow = SimpleNamespace(
        load_effective_exclude_patterns=lambda _root: [],
    )
    baseline = ("cbcs/project.json", "src", "src/main.py")
    window_any._project_tree_structure_signature = baseline
    window_any._project_inventory_orchestrator = SimpleNamespace(
        generation=1,
        tree_structure_signature=lambda: baseline,
        set_tree_structure_signature=lambda _sig: None,
    )
    reload_calls: list[bool] = []
    window_any._project_tree_ui_workflow = SimpleNamespace(
        reload_current_project=lambda: reload_calls.append(True)
    )

    workflow = _attach_poll_editor_tab_workflow(window_any)

    workflow.poll_external_file_changes()

    assert reload_calls == []
    assert window_any._project_tree_structure_signature == baseline


def testfilter_tree_signature_entries_strips_run_and_cache_artifacts() -> None:
    raw = (
        "cbcs/project.json",
        "cbcs/runs/run_1.json",
        "cbcs/runs/nested/sub.json",
        "cbcs/logs/run_1.log",
        "cbcs/cache/index.bin",
        "src/main.py",
        "logs/keepme.txt",
    )

    filtered = filter_tree_signature_entries(raw)

    assert filtered == (
        "cbcs/project.json",
        "src/main.py",
        "logs/keepme.txt",
    )
