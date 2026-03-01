"""Unit tests for find-in-files helper logic."""

from pathlib import Path
import threading
import time

import pytest

from app.editors.search_panel import SearchWorker, find_in_files

pytestmark = pytest.mark.unit


def test_find_in_files_returns_matches_with_line_numbers(tmp_path: Path) -> None:
    """Search should return file/line snippets for matching text."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "alpha.py").write_text("hello\nneedle here\n", encoding="utf-8")
    (project_root / "beta.py").write_text("needle again\n", encoding="utf-8")

    matches = find_in_files(project_root, "needle")

    assert len(matches) == 2
    assert matches[0].relative_path == "alpha.py"
    assert matches[0].line_number == 2
    assert matches[1].relative_path == "beta.py"
    assert matches[1].line_number == 1


def test_find_in_files_ignores_cbcs_metadata_directory(tmp_path: Path) -> None:
    """Search should skip .cbcs metadata files."""
    project_root = tmp_path / "project"
    (project_root / ".cbcs").mkdir(parents=True)
    (project_root / ".cbcs" / "secret.txt").write_text("needle", encoding="utf-8")

    assert find_in_files(project_root, "needle") == []


def test_search_worker_emits_results_and_done_callbacks(tmp_path: Path) -> None:
    """Background worker should call on_results and on_done."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "alpha.py").write_text("needle\n", encoding="utf-8")

    seen: list[str] = []
    done = threading.Event()

    worker = SearchWorker(
        project_root=project_root,
        query="needle",
        on_results=lambda matches, _query: seen.append(matches[0].relative_path if matches else "none"),
        on_done=done.set,
    )
    worker.start()

    assert done.wait(timeout=2.0)
    assert seen == ["alpha.py"]


def test_search_worker_cancel_prevents_results_callback(tmp_path: Path) -> None:
    """Cancelled worker should not emit on_results callback."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    for index in range(200):
        (project_root / f"f{index}.py").write_text("needle\n", encoding="utf-8")

    seen: list[str] = []
    done = threading.Event()
    worker = SearchWorker(
        project_root=project_root,
        query="needle",
        on_results=lambda matches, _query: seen.append(str(len(matches))),
        on_done=done.set,
    )
    worker.cancel()
    worker.start()
    assert done.wait(timeout=2.0)
    time.sleep(0.05)
    assert seen == []
