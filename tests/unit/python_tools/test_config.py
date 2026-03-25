"""Unit tests for Python formatting/import config resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.python_tools.config import resolve_python_tooling_settings

pytestmark = pytest.mark.unit


def _fixture_root(name: str) -> Path:
    return Path(__file__).resolve().parents[2] / "fixtures" / "formatting" / name


def test_resolve_python_tooling_settings_reads_project_local_pyproject() -> None:
    project_root = _fixture_root("py39_project")

    settings = resolve_python_tooling_settings(
        project_root=str(project_root),
        file_path=str(project_root / "input_format.py"),
    )

    assert settings.config_source == "project_pyproject"
    assert settings.pyproject_path == project_root / "pyproject.toml"
    assert settings.python_target_minor == 39
    assert settings.black_line_length == 40
    assert settings.isort_profile == "black"
    assert settings.isort_line_length == 40
    assert settings.isort_src_paths == (project_root / "src",)


def test_resolve_python_tooling_settings_defaults_to_py39_without_pyproject() -> None:
    project_root = _fixture_root("default_project")

    settings = resolve_python_tooling_settings(
        project_root=str(project_root),
        file_path=str(project_root / "input_imports.py"),
    )

    assert settings.config_source == "defaults"
    assert settings.pyproject_path is None
    assert settings.python_target_minor == 39
    assert settings.black_line_length == 88
    assert settings.isort_profile == "black"
    assert settings.isort_line_length == 88
