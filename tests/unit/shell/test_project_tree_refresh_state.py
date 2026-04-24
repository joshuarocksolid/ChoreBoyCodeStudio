"""Unit tests for project tree expansion/selection preservation."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication, QTreeWidgetItem  # noqa: E402

from app.core.models import LoadedProject, ProjectFileEntry, ProjectMetadata  # noqa: E402
from app.shell.main_window import MainWindow, TREE_ROLE_RELATIVE_PATH  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


def _find_item_by_relative_path(window: MainWindow, relative_path: str) -> QTreeWidgetItem | None:
    for item in window._iter_project_tree_items():  # noqa: SLF001 - intentional tree-state verification
        if str(item.data(0, TREE_ROLE_RELATIVE_PATH) or "") == relative_path:
            return item
    return None


def test_populate_project_tree_preserves_expansion_and_selection(tmp_path: Path) -> None:
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
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
    window._populate_project_tree(loaded_project)  # noqa: SLF001 - direct tree population for state test

    src_item = _find_item_by_relative_path(window, "src")
    docs_readme_item = _find_item_by_relative_path(window, "docs/readme.md")
    assert src_item is not None
    assert docs_readme_item is not None

    src_item.setExpanded(False)
    docs_readme_item.setSelected(True)

    window._populate_project_tree(loaded_project, preserve_state=True)  # noqa: SLF001

    restored_src = _find_item_by_relative_path(window, "src")
    restored_docs_readme = _find_item_by_relative_path(window, "docs/readme.md")
    assert restored_src is not None
    assert restored_docs_readme is not None
    assert restored_src.isExpanded() is False
    assert restored_docs_readme.isSelected() is True

    window.close()


def test_poll_external_file_changes_reloads_project_tree_on_structure_change() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._editor_manager = SimpleNamespace(
        stale_open_paths=lambda: [],
        active_tab=lambda: None,
    )
    loaded_project = LoadedProject(
        project_root="/tmp/project",
        manifest_path="/tmp/project/cbcs/project.json",
        metadata=ProjectMetadata(schema_version=1, name="Tree"),
        entries=[],
    )
    window_any._loaded_project = loaded_project
    window_any._project_tree_structure_signature = ("src", "src/main.py")
    reload_calls: list[bool] = []
    window_any._reload_current_project = lambda: reload_calls.append(True)
    window_any._scan_project_tree_signature = lambda _project: ("src", "src/main.py", "docs")

    MainWindow._poll_external_file_changes(window)

    assert reload_calls == [True]
