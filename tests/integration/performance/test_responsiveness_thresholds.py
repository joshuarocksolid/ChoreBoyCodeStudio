"""Integration timing checks for baseline responsiveness thresholds."""

from __future__ import annotations

import json
from pathlib import Path
import time

import pytest

from app.editors.editor_manager import EditorManager
from app.editors.search_panel import find_in_files
from app.project.project_service import open_project

pytestmark = [pytest.mark.integration, pytest.mark.performance, pytest.mark.timeout(120)]


def _write_project_manifest(project_root: Path, name: str) -> None:
    (project_root / "cbcs").mkdir(parents=True, exist_ok=True)
    (project_root / "cbcs" / "project.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": name,
                "default_entry": "run.py",
                "working_directory": ".",
            }
        ),
        encoding="utf-8",
    )


def test_open_project_500_files_under_one_second(tmp_path: Path) -> None:
    """Opening a medium project should remain within baseline threshold."""
    project_root = tmp_path / "medium_project"
    project_root.mkdir(parents=True)
    _write_project_manifest(project_root, "medium_project")
    for index in range(500):
        (project_root / f"file_{index:03d}.py").write_text(f"print({index})\n", encoding="utf-8")

    start = time.perf_counter()
    loaded_project = open_project(project_root)
    elapsed = time.perf_counter() - start

    assert len(loaded_project.entries) >= 500
    assert elapsed <= 1.0


def test_open_2000_loc_file_under_250ms(tmp_path: Path) -> None:
    """Opening a large script should be near-instant for editor manager."""
    file_path = tmp_path / "large.py"
    file_path.write_text("\n".join(f"print({index})" for index in range(2000)), encoding="utf-8")
    manager = EditorManager()

    start = time.perf_counter()
    opened = manager.open_file(str(file_path))
    elapsed = time.perf_counter() - start

    assert opened.was_already_open is False
    assert elapsed <= 0.25


def test_find_in_files_500_files_first_results_under_1_5s(tmp_path: Path) -> None:
    """Project-wide search should return first chunk quickly."""
    project_root = tmp_path / "search_project"
    project_root.mkdir(parents=True)
    _write_project_manifest(project_root, "search_project")
    for index in range(500):
        content = "target\n" if index == 0 else f"line {index}\n"
        (project_root / f"file_{index:03d}.py").write_text(content, encoding="utf-8")

    start = time.perf_counter()
    matches = find_in_files(project_root, "target", max_results=10)
    elapsed = time.perf_counter() - start

    assert matches
    assert elapsed <= 1.5


