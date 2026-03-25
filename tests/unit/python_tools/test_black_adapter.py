"""Unit tests for Black-backed Python formatting."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.python_tools.black_adapter import format_python_text

pytestmark = pytest.mark.unit


def _fixture_root(name: str) -> Path:
    return Path(__file__).resolve().parents[2] / "fixtures" / "formatting" / name


def test_format_python_text_uses_project_local_black_settings() -> None:
    project_root = _fixture_root("py39_project")
    input_path = project_root / "input_format.py"
    expected_path = project_root / "expected_format.py"

    result = format_python_text(
        input_path.read_text(encoding="utf-8"),
        file_path=str(input_path),
        project_root=str(project_root),
    )

    assert result.status == "formatted"
    assert result.changed is True
    assert result.formatted_text == expected_path.read_text(encoding="utf-8")


def test_format_python_text_reports_syntax_errors_without_mutating_source() -> None:
    project_root = _fixture_root("broken_project")
    input_path = project_root / "broken.py"
    source = input_path.read_text(encoding="utf-8")

    result = format_python_text(
        source,
        file_path=str(input_path),
        project_root=str(project_root),
    )

    assert result.status == "syntax_error"
    assert result.changed is False
    assert result.formatted_text == source
