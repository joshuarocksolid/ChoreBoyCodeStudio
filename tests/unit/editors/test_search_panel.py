"""Unit tests for find-in-files helper logic."""

from pathlib import Path
import threading
import time

import pytest

from app.editors.search_panel import SearchMatch, SearchOptions, SearchWorker, find_in_files, replace_in_files

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


def test_find_in_files_respects_pre_set_cancel_event(tmp_path: Path) -> None:
    """Search should short-circuit immediately when cancellation is already requested."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "alpha.py").write_text("needle\n", encoding="utf-8")
    cancel_event = threading.Event()
    cancel_event.set()

    assert find_in_files(project_root, "needle", cancel_event=cancel_event) == []


def test_find_in_files_case_sensitive(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "a.py").write_text("Hello\nhello\nHELLO\n", encoding="utf-8")

    opts_sensitive = SearchOptions(case_sensitive=True)
    matches = find_in_files(project_root, "Hello", options=opts_sensitive)
    assert len(matches) == 1
    assert matches[0].line_number == 1

    opts_insensitive = SearchOptions(case_sensitive=False)
    matches = find_in_files(project_root, "Hello", options=opts_insensitive)
    assert len(matches) == 3


def test_find_in_files_whole_word(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "a.py").write_text("cat\ncatalog\nthe cat sat\n", encoding="utf-8")

    opts = SearchOptions(whole_word=True)
    matches = find_in_files(project_root, "cat", options=opts)
    assert len(matches) == 2
    lines = {m.line_number for m in matches}
    assert lines == {1, 3}


def test_find_in_files_regex(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "a.py").write_text("foo123\nbar456\nfoo789\n", encoding="utf-8")

    opts = SearchOptions(regex=True)
    matches = find_in_files(project_root, r"foo\d+", options=opts)
    assert len(matches) == 2


def test_find_in_files_include_globs(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "a.py").write_text("needle\n", encoding="utf-8")
    (project_root / "b.txt").write_text("needle\n", encoding="utf-8")

    opts = SearchOptions(include_globs=["*.py"])
    matches = find_in_files(project_root, "needle", options=opts)
    assert len(matches) == 1
    assert matches[0].relative_path == "a.py"


def test_find_in_files_exclude_globs(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "a.py").write_text("needle\n", encoding="utf-8")
    (project_root / "b.py").write_text("needle\n", encoding="utf-8")

    opts = SearchOptions(exclude_globs=["b.py"])
    matches = find_in_files(project_root, "needle", options=opts)
    assert len(matches) == 1
    assert matches[0].relative_path == "a.py"


def test_find_in_files_returns_column_and_length(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "a.py").write_text("   needle here\n", encoding="utf-8")

    matches = find_in_files(project_root, "needle")
    assert len(matches) == 1
    assert matches[0].column == 3
    assert matches[0].match_length == 6


def test_replace_in_files_basic(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_a = project_root / "a.py"
    file_a.write_text("hello world\nhello again\n", encoding="utf-8")

    matches = find_in_files(project_root, "hello")
    count = replace_in_files(matches, "goodbye", "hello")
    assert count == 2
    assert file_a.read_text() == "goodbye world\ngoodbye again\n"


def test_replace_in_files_with_regex(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_a = project_root / "a.py"
    file_a.write_text("foo123\nbar456\nfoo789\n", encoding="utf-8")

    opts = SearchOptions(regex=True)
    matches = find_in_files(project_root, r"foo\d+", options=opts)
    count = replace_in_files(matches, "replaced", r"foo\d+", options=opts)
    assert count == 2
    assert "replaced" in file_a.read_text()


def test_search_worker_with_options(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "a.py").write_text("Hello\nhello\n", encoding="utf-8")

    seen: list[int] = []
    done = threading.Event()
    opts = SearchOptions(case_sensitive=True)

    worker = SearchWorker(
        project_root=project_root,
        query="Hello",
        options=opts,
        on_results=lambda matches, _q: seen.append(len(matches)),
        on_done=done.set,
    )
    worker.start()
    assert done.wait(timeout=2.0)
    assert seen == [1]
