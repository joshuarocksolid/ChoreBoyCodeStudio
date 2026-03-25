"""Unit tests for isort-backed import organization."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.python_tools.isort_adapter import organize_imports_text

pytestmark = pytest.mark.unit


def _fixture_root(name: str) -> Path:
    return Path(__file__).resolve().parents[2] / "fixtures" / "formatting" / name


def test_organize_imports_defaults_to_python39_stdlib_classification() -> None:
    project_root = _fixture_root("default_project")
    input_path = project_root / "input_imports.py"
    expected_path = project_root / "expected_organized_imports.py"

    result = organize_imports_text(
        input_path.read_text(encoding="utf-8"),
        file_path=str(input_path),
        project_root=str(project_root),
    )

    assert result.status == "imports_organized"
    assert result.changed is True
    assert result.formatted_text == expected_path.read_text(encoding="utf-8")


def test_organize_imports_preserves_future_imports_comments_and_src_paths() -> None:
    project_root = _fixture_root("py39_project")
    input_path = project_root / "input_imports.py"
    expected_path = project_root / "expected_organized_imports.py"

    result = organize_imports_text(
        input_path.read_text(encoding="utf-8"),
        file_path=str(input_path),
        project_root=str(project_root),
    )

    assert result.status == "imports_organized"
    assert result.changed is True
    assert result.formatted_text == expected_path.read_text(encoding="utf-8")


def test_organize_imports_reports_syntax_errors_without_mutating_source() -> None:
    project_root = _fixture_root("broken_project")
    input_path = project_root / "broken.py"
    source = input_path.read_text(encoding="utf-8")

    result = organize_imports_text(
        source,
        file_path=str(input_path),
        project_root=str(project_root),
    )

    assert result.status == "syntax_error"
    assert result.changed is False
    assert result.formatted_text == source
