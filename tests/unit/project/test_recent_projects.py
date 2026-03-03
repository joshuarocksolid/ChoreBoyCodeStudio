"""Unit tests for recent-projects persistence helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.project.recent_projects import (
    OPEN_RECENT_MENU_LIMIT,
    load_recent_projects,
    remember_recent_project,
)

pytestmark = pytest.mark.unit


def test_load_recent_projects_returns_empty_list_when_file_missing(tmp_path: Path) -> None:
    """Missing recents file should be treated as empty state."""
    state_root = tmp_path / "state"

    assert load_recent_projects(state_root=state_root) == []


def test_remember_recent_project_prepends_most_recent_path(tmp_path: Path) -> None:
    """Remembering a project should place it at the front."""
    state_root = tmp_path / "state"
    project_a = _write_valid_project(tmp_path / "project_a", name="Project A")
    project_b = _write_valid_project(tmp_path / "project_b", name="Project B")

    remember_recent_project(project_a, state_root=state_root)
    result = remember_recent_project(project_b, state_root=state_root)

    assert result == [str(project_b.resolve()), str(project_a.resolve())]


def test_remember_recent_project_moves_existing_entry_to_front_without_duplicates(tmp_path: Path) -> None:
    """Adding an existing project should move it to front and keep unique entries."""
    state_root = tmp_path / "state"
    project_a = _write_valid_project(tmp_path / "project_a", name="Project A")
    project_b = _write_valid_project(tmp_path / "project_b", name="Project B")

    remember_recent_project(project_a, state_root=state_root)
    remember_recent_project(project_b, state_root=state_root)
    result = remember_recent_project(project_a, state_root=state_root)

    assert result == [str(project_a.resolve()), str(project_b.resolve())]
    assert len(result) == 2


def test_load_recent_projects_prunes_invalid_entries(tmp_path: Path) -> None:
    """Loading should prune missing paths, non-dirs, and invalid project layouts."""
    state_root = tmp_path / "state"
    recents_path = state_root / "recent_projects.json"
    valid_project = _write_valid_project(tmp_path / "valid_project", name="Valid")
    missing_project = tmp_path / "missing_project"
    non_directory = tmp_path / "not_a_project.txt"
    non_directory.write_text("not a directory\n", encoding="utf-8")
    invalid_project = tmp_path / "invalid_project"
    invalid_project.mkdir()

    recents_path.parent.mkdir(parents=True)
    recents_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "projects": [
                    str(valid_project.resolve()),
                    str(missing_project.resolve()),
                    str(non_directory.resolve()),
                    str(invalid_project.resolve()),
                ],
            }
        ),
        encoding="utf-8",
    )

    result = load_recent_projects(state_root=state_root)

    assert result == [str(valid_project.resolve())]


def test_load_recent_projects_normalizes_and_deduplicates_paths(tmp_path: Path) -> None:
    """Loaded entries should normalize path variants and dedupe deterministically."""
    state_root = tmp_path / "state"
    recents_path = state_root / "recent_projects.json"
    project_a = _write_valid_project(tmp_path / "project_a", name="Project A")
    project_b = _write_valid_project(tmp_path / "project_b", name="Project B")
    project_a_alias = project_a.parent / "." / project_a.name

    recents_path.parent.mkdir(parents=True)
    recents_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "projects": [
                    str(project_a_alias),
                    str(project_b.resolve()),
                    str(project_a.resolve()),
                ],
            }
        ),
        encoding="utf-8",
    )

    result = load_recent_projects(state_root=state_root)

    assert result == [str(project_a.resolve()), str(project_b.resolve())]


def test_load_recent_projects_limits_entries_to_max_count(tmp_path: Path) -> None:
    """Loaded recents should respect the caller-provided entry cap."""
    state_root = tmp_path / "state"
    max_entries = 2
    project_a = _write_valid_project(tmp_path / "project_a", name="Project A")
    project_b = _write_valid_project(tmp_path / "project_b", name="Project B")
    project_c = _write_valid_project(tmp_path / "project_c", name="Project C")

    remember_recent_project(project_a, state_root=state_root)
    remember_recent_project(project_b, state_root=state_root)
    remember_recent_project(project_c, state_root=state_root)

    result = load_recent_projects(state_root=state_root, max_entries=max_entries)

    assert result == [str(project_c.resolve()), str(project_b.resolve())]


def test_load_recent_projects_unbounded_by_default(tmp_path: Path) -> None:
    """Without max_entries the full history should be returned."""
    state_root = tmp_path / "state"
    projects = []
    for i in range(25):
        p = _write_valid_project(tmp_path / f"project_{i:03d}", name=f"Project {i}")
        projects.append(p)
        remember_recent_project(p, state_root=state_root)

    result = load_recent_projects(state_root=state_root)

    assert len(result) == 25
    assert result[0] == str(projects[-1].resolve())


def test_open_recent_menu_limit_is_reasonable() -> None:
    """OPEN_RECENT_MENU_LIMIT should be a small, positive integer for menus."""
    assert isinstance(OPEN_RECENT_MENU_LIMIT, int)
    assert 1 <= OPEN_RECENT_MENU_LIMIT <= 20


def _write_valid_project(project_root: Path, *, name: str) -> Path:
    manifest_path = project_root / "cbcs" / "project.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": name,
            }
        ),
        encoding="utf-8",
    )
    return project_root
