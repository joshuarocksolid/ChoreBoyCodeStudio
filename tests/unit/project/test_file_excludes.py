"""Unit tests for shared file exclusion helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import constants
from app.project.file_excludes import (
    load_effective_exclude_patterns,
    parse_project_exclude_patterns,
    should_exclude_relative_path,
)

pytestmark = pytest.mark.unit


def test_should_exclude_relative_path_matches_nested_segment_patterns() -> None:
    assert should_exclude_relative_path("src/node_modules/pkg/index.js", ["node_modules"], is_directory=False) is True


def test_should_exclude_relative_path_matches_direct_name_and_glob_patterns() -> None:
    assert should_exclude_relative_path("dist/main.pyc", ["*.pyc"], is_directory=False) is True
    assert should_exclude_relative_path("src/main.py", ["src/*.py"], is_directory=False) is True


def test_should_exclude_relative_path_handles_directories_and_non_matches() -> None:
    assert should_exclude_relative_path("venv", ["venv"], is_directory=True) is True
    assert should_exclude_relative_path("src/app/main.py", ["tests"], is_directory=False) is False


def test_parse_project_exclude_patterns_returns_empty_when_missing() -> None:
    assert parse_project_exclude_patterns({}) == []


def test_parse_project_exclude_patterns_parses_clean_nonempty_values() -> None:
    payload = {
        constants.UI_FILE_EXCLUDES_SETTINGS_KEY: {
            constants.UI_FILE_EXCLUDES_PATTERNS_KEY: ["*.tmp", " build ", "", 123],
        }
    }
    assert parse_project_exclude_patterns(payload) == ["*.tmp", "build"]


class _StubSettingsService:
    def __init__(self, *, global_payload: dict, project_payload: dict) -> None:
        self._global_payload = global_payload
        self._project_payload = project_payload

    def load_global(self) -> dict:
        return dict(self._global_payload)

    def load_project(self, _project_root: str) -> dict:
        return dict(self._project_payload)


def test_load_effective_exclude_patterns_combines_global_and_project_patterns() -> None:
    service = _StubSettingsService(
        global_payload={
            constants.UI_FILE_EXCLUDES_SETTINGS_KEY: {
                constants.UI_FILE_EXCLUDES_PATTERNS_KEY: ["__pycache__", ".git"],
            }
        },
        project_payload={
            constants.UI_FILE_EXCLUDES_SETTINGS_KEY: {
                constants.UI_FILE_EXCLUDES_PATTERNS_KEY: ["build", ".git"],
            }
        },
    )

    effective = load_effective_exclude_patterns(service, "/tmp/project")

    assert effective == ["__pycache__", ".git", "build"]


def test_load_effective_exclude_patterns_skips_project_payload_when_no_root() -> None:
    service = _StubSettingsService(
        global_payload={
            constants.UI_FILE_EXCLUDES_SETTINGS_KEY: {
                constants.UI_FILE_EXCLUDES_PATTERNS_KEY: ["__pycache__"],
            }
        },
        project_payload={
            constants.UI_FILE_EXCLUDES_SETTINGS_KEY: {
                constants.UI_FILE_EXCLUDES_PATTERNS_KEY: ["should-not-appear"],
            }
        },
    )

    effective = load_effective_exclude_patterns(service, project_root=None)

    assert effective == ["__pycache__"]


def test_default_exclude_patterns_include_vendor() -> None:
    from app.project.file_excludes import DEFAULT_EXCLUDE_PATTERNS

    assert "vendor" in DEFAULT_EXCLUDE_PATTERNS


def test_iter_project_entries_skips_vendor_directory(tmp_path: Path) -> None:
    from app.project.file_inventory import iter_project_entries

    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text("print(1)\n", encoding="utf-8")
    vendor_dir = project_root / "vendor"
    vendor_dir.mkdir()
    for index in range(20):
        (vendor_dir / f"mod_{index:02d}.py").write_text("x=1\n", encoding="utf-8")

    entries = list(iter_project_entries(project_root, exclude_patterns=["vendor"]))

    assert all("vendor" not in entry.relative_path for entry in entries)
    assert any(entry.relative_path == "main.py" for entry in entries)
