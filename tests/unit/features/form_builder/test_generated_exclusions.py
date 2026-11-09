"""cbcs/form_builder stays out of search, Jedi walks, and pytest collection."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.project.file_inventory import iter_python_files, iter_text_file_paths
from app.pytest.launch_plan import PytestLaunchPlan, build_pytest_command

pytestmark = pytest.mark.unit


def test_form_builder_metadata_is_absent_from_walks(tmp_path: Path) -> None:
    meta = tmp_path / "cbcs" / "form_builder"
    meta.mkdir(parents=True)
    (meta / "notes.py").write_text("x = 1\n", encoding="utf-8")
    (meta / "notes.txt").write_text("kept\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("y = 2\n", encoding="utf-8")
    python_paths = [path.relative_to(tmp_path).as_posix() for path in iter_python_files(tmp_path)]
    text_paths = [relative for _path, relative in iter_text_file_paths(tmp_path)]
    assert python_paths == ["main.py"]
    assert "cbcs/form_builder/notes.txt" not in text_paths
    assert "cbcs/form_builder/notes.py" not in text_paths


def test_pytest_collection_ignores_form_builder_metadata(tmp_path: Path) -> None:
    plan = PytestLaunchPlan(
        project_root=str(tmp_path),
        runtime_executable="python",
        run_tests_script=None,
        use_apprun_inline_payload=False,
    )
    command = build_pytest_command(plan, ["tests"])
    assert "--ignore=cbcs/form_builder" in command
