"""Opening a code tab must not stat every project-tree path."""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core.models import LoadedProject, ProjectFileEntry, ProjectMetadata  # noqa: E402
from app.qt.QtWidgets import QApplication  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from app.shell.tree_item_roles import TREE_ROLE_RELATIVE_PATH  # noqa: E402
from app.treesitter.loader import initialize_tree_sitter_runtime  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


def test_open_file_at_line_does_not_stat_every_tree_path(tmp_path: Path, _qapp: QApplication) -> None:
    initialize_tree_sitter_runtime()
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        project_root = tmp_path / "project"
        source_dir = project_root / "src"
        source_dir.mkdir(parents=True)
        target = source_dir / "opened.py"
        target.write_text("print('opened')\n", encoding="utf-8")
        entries = [
            ProjectFileEntry(
                relative_path="src",
                absolute_path=str(source_dir.resolve()),
                is_directory=True,
            )
        ]
        for index in range(30):
            path = source_dir / ("file_%d.py" % index)
            path.write_text("x = %d\n" % index, encoding="utf-8")
            entries.append(
                ProjectFileEntry(
                    relative_path="src/file_%d.py" % index,
                    absolute_path=str(path.resolve()),
                    is_directory=False,
                )
            )
        entries.append(
            ProjectFileEntry(
                relative_path="src/opened.py",
                absolute_path=str(target.resolve()),
                is_directory=False,
            )
        )
        loaded = LoadedProject(
            project_root=str(project_root.resolve()),
            manifest_path=str((project_root / "cbcs" / "project.json").resolve()),
            metadata=ProjectMetadata(schema_version=1, name="Tree", default_entry="src/opened.py"),
            entries=entries,
        )
        window._loaded_project = loaded  # noqa: SLF001
        window._project_tree_ui_workflow.populate_project_tree(loaded)  # noqa: SLF001
        lstat_calls = {"n": 0}
        sibling_lstats = {"n": 0}
        resolve_calls = {"n": 0, "paths": []}
        sibling_resolves = {"n": 0}
        reveal_calls = {"n": 0}
        real_lstat = os.lstat
        real_resolve = Path.resolve
        real_reveal = window._project_tree_presenter.reveal_path  # noqa: SLF001

        source_prefix = str(source_dir.resolve()) + "/"

        def _under_source(path: object) -> bool:
            text = str(path)
            return text.startswith(source_prefix) or text.startswith(str(source_dir) + "/")

        def counting_lstat(path, *args, **kwargs):  # type: ignore[no-untyped-def]
            lstat_calls["n"] += 1
            name = str(path).rsplit("/", 1)[-1]
            if _under_source(path) and name.startswith("file_") and name.endswith(".py"):
                sibling_lstats["n"] += 1
            return real_lstat(path, *args, **kwargs)

        def counting_resolve(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            text = str(self)
            resolve_calls["n"] += 1
            resolve_calls["paths"].append(text)
            name = text.rsplit("/", 1)[-1]
            if _under_source(text) and name.startswith("file_") and name[5:6].isdigit():
                sibling_resolves["n"] += 1
            return real_resolve(self, *args, **kwargs)

        def counting_reveal(file_path: str) -> None:
            reveal_calls["n"] += 1
            real_reveal(file_path)

        window._project_tree_presenter.reveal_path = counting_reveal  # type: ignore[method-assign]  # noqa: SLF001
        with patch("os.lstat", counting_lstat), patch.object(Path, "resolve", counting_resolve):
            window._editor_tab_workflow.open_file_at_line(str(target), 1)  # noqa: SLF001
            _qapp.processEvents()
        assert sibling_resolves["n"] == 0
        assert sibling_lstats["n"] == 0
        assert reveal_calls["n"] == 1, reveal_calls["n"]
        repeated = {path: count for path, count in Counter(resolve_calls["paths"]).items() if count > 1}
        assert not repeated, repeated
        assert resolve_calls["n"] <= 8, resolve_calls["paths"]
        assert lstat_calls["n"] <= 80, lstat_calls["n"]
        selected = window._project_tree_widget.selectedItems()  # noqa: SLF001
        assert [str(item.data(0, TREE_ROLE_RELATIVE_PATH) or "") for item in selected] == ["src/opened.py"]
    finally:
        shutdown_main_window_for_test(window, _qapp)
