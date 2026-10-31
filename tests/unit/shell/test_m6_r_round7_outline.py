"""The first outline worker must not start inside the tab switch."""

from __future__ import annotations

import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core.models import LoadedProject, ProjectFileEntry, ProjectMetadata  # noqa: E402
from app.qt.QtWidgets import QApplication  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


def test_handle_editor_tab_changed_does_not_start_the_outline_thread(
    tmp_path: Path, _qapp: QApplication
) -> None:
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        project_root = tmp_path / "project"
        project_root.mkdir()
        target = project_root / "opened.py"
        target.write_text("def opened():\n    return 1\n", encoding="utf-8")
        loaded = LoadedProject(
            project_root=str(project_root.resolve()),
            manifest_path=str((project_root / "cbcs" / "project.json").resolve()),
            metadata=ProjectMetadata(schema_version=1, name="Outline", default_entry="opened.py"),
            entries=[
                ProjectFileEntry(
                    relative_path="opened.py",
                    absolute_path=str(target.resolve()),
                    is_directory=False,
                )
            ],
        )
        window._loaded_project = loaded  # noqa: SLF001
        window._project_tree_ui_workflow.populate_project_tree(loaded)  # noqa: SLF001
        starts_in_handler: list[str] = []
        submits_in_handler: list[str] = []
        submits = {"n": 0}
        real_start = __import__("threading").Thread.start
        real_submit = ThreadPoolExecutor.submit

        def counting_start(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            stack = "".join(traceback.format_stack())
            if "in handle_editor_tab_changed" in stack or "in _apply_editor_tab_changed" in stack:
                starts_in_handler.append(stack)
            return real_start(self, *args, **kwargs)

        def counting_submit(self, fn, *args, **kwargs):  # type: ignore[no-untyped-def]
            stack = "".join(traceback.format_stack())
            if "_schedule_outline_parse" in stack or "handle_active_tab_changed" in stack:
                submits["n"] += 1
            if "in handle_editor_tab_changed" in stack or "in _apply_editor_tab_changed" in stack:
                if "_schedule_outline_parse" in stack or "Thread.start" in stack:
                    submits_in_handler.append(stack)
            return real_submit(self, fn, *args, **kwargs)

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr("threading.Thread.start", counting_start)
            patch.setattr(ThreadPoolExecutor, "submit", counting_submit)
            window._editor_tab_workflow.open_file_at_line(str(target), 1)  # noqa: SLF001
            assert starts_in_handler == []
            assert submits_in_handler == []
            _qapp.processEvents()
        assert submits["n"] >= 1
    finally:
        shutdown_main_window_for_test(window, _qapp)
