"""Unit tests for shared file exclusion helpers."""

from __future__ import annotations

import pytest

from app.project.file_excludes import should_exclude_relative_path

pytestmark = pytest.mark.unit


def test_should_exclude_relative_path_matches_nested_segment_patterns() -> None:
    assert should_exclude_relative_path("src/node_modules/pkg/index.js", ["node_modules"], is_directory=False) is True


def test_should_exclude_relative_path_matches_direct_name_and_glob_patterns() -> None:
    assert should_exclude_relative_path("dist/main.pyc", ["*.pyc"], is_directory=False) is True
    assert should_exclude_relative_path("src/main.py", ["src/*.py"], is_directory=False) is True


def test_should_exclude_relative_path_handles_directories_and_non_matches() -> None:
    assert should_exclude_relative_path("venv", ["venv"], is_directory=True) is True
    assert should_exclude_relative_path("src/app/main.py", ["tests"], is_directory=False) is False
