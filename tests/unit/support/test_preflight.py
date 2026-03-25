"""Unit tests for run/package preflight helpers."""
from __future__ import annotations

from pathlib import Path

from app.core.models import LoadedProject, ProjectMetadata
from app.support.preflight import build_package_preflight, build_run_preflight


def _build_loaded_project(project_root: Path) -> LoadedProject:
    (project_root / "cbcs").mkdir(parents=True, exist_ok=True)
    return LoadedProject(
        project_root=str(project_root.resolve()),
        manifest_path=str((project_root / "cbcs" / "project.json").resolve()),
        metadata=ProjectMetadata(
            schema_version=1,
            name="Example Project",
            default_entry="main.py",
            working_directory=".",
        ),
    )


def test_build_run_preflight_requires_open_project() -> None:
    result = build_run_preflight(loaded_project=None)

    assert result.workflow == "run"
    assert result.is_ready is False
    assert result.highest_severity == "blocking"
    assert [issue.issue_id for issue in result.issues] == ["run.no_project"]


def test_build_run_preflight_flags_missing_entry_file(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    loaded_project = _build_loaded_project(project_root)

    result = build_run_preflight(loaded_project=loaded_project)

    assert result.is_ready is False
    assert [issue.issue_id for issue in result.issues] == ["run.entry_not_found"]


def test_build_run_preflight_flags_working_directory_outside_project(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text("print('ok')\n", encoding="utf-8")
    loaded_project = _build_loaded_project(project_root)

    result = build_run_preflight(
        loaded_project=loaded_project,
        working_directory="../outside",
    )

    assert result.is_ready is False
    assert [issue.issue_id for issue in result.issues] == ["run.working_directory_outside_project"]


def test_build_run_preflight_returns_ready_for_valid_target(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text("print('ok')\n", encoding="utf-8")
    loaded_project = _build_loaded_project(project_root)

    result = build_run_preflight(loaded_project=loaded_project)

    assert result.is_ready is True
    assert result.issues == []
    assert result.summary == "Run target is ready."


def test_build_package_preflight_flags_output_overlap(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text("print('ok')\n", encoding="utf-8")

    result = build_package_preflight(
        project_root=str(project_root),
        project_name="Project",
        entry_file="main.py",
        output_dir=str(project_root),
    )

    assert result.is_ready is False
    assert [issue.issue_id for issue in result.issues] == ["package.output_overlaps_project"]


def test_build_package_preflight_flags_excluded_entry_file(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    entry_path = project_root / "cbcs" / "logs" / "run_entry.py"
    entry_path.parent.mkdir(parents=True)
    entry_path.write_text("print('log entry')\n", encoding="utf-8")

    result = build_package_preflight(
        project_root=str(project_root),
        project_name="Project",
        entry_file="cbcs/logs/run_entry.py",
        output_dir=str(tmp_path / "exports"),
    )

    assert result.is_ready is False
    assert [issue.issue_id for issue in result.issues] == ["package.entry_excluded"]
