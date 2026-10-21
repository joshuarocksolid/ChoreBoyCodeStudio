"""The per-buffer completion warmup runs against the real editor widget."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.project.project_service import create_blank_project
from app.shell import completion_warmup
from app.shell.main_window import MainWindow
from testing.main_window_shutdown import shutdown_main_window_for_test
from testing.main_window_test_helpers import prepare_main_window_for_test

pytestmark = pytest.mark.integration


def test_buffer_warmup_reads_the_open_python_file(tmp_path: Path, shell_qapp, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Warm")
    source = project_root / "main.py"
    source.write_text("import os\nos.\n", encoding="utf-8")
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    prepare_main_window_for_test(window, app=shell_qapp)
    try:
        assert window._file_project_commands_workflow.open_project_by_path(str(project_root.resolve()))
        assert window._editor_tab_factory.open_file_in_editor(str(source.resolve()))
        requested: list[str] = []
        monkeypatch.setattr(completion_warmup, "_window_shown", True)
        monkeypatch.setattr(
            window._semantic_session,
            "request_buffer_warmup",
            lambda **kwargs: requested.append(kwargs["current_file_path"]),
        )

        completion_warmup._start_buffer_warmup(window)

        assert requested == [str(source.resolve())]
    finally:
        shutdown_main_window_for_test(window, shell_qapp)
