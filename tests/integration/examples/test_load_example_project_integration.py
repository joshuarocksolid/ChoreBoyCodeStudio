"""Integration tests for Help > Load Example Project end-to-end flow."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.examples.example_project_service import ExampleProjectService
from app.project.project_service import open_project

pytestmark = pytest.mark.integration


def _repo_example_projects_root() -> Path:
    return Path(__file__).resolve().parents[3] / "example_projects"


def test_materialized_showcase_opens_as_valid_project(tmp_path: Path) -> None:
    """Materialized example project should open with correct metadata and files."""
    service = ExampleProjectService(examples_root=str(_repo_example_projects_root()))
    project_root = service.materialize_showcase(
        destination_path=tmp_path / "showcase_project",
        project_name="My Showcase",
    )

    loaded = open_project(project_root)

    assert loaded.metadata.name == "My Showcase"
    assert loaded.metadata.template == "crud_showcase"
    assert loaded.metadata.default_entry == "main.py"

    assert (project_root / "main.py").exists()
    assert (project_root / "app" / "main_window.py").exists()
    assert (project_root / "app" / "repository.py").exists()
    assert (project_root / "app" / "freecad_probe.py").exists()
    assert (project_root / "README.md").exists()


def test_materialized_showcase_has_runnable_entrypoint(tmp_path: Path) -> None:
    """The example project main.py should be parseable Python."""
    service = ExampleProjectService(examples_root=str(_repo_example_projects_root()))
    project_root = service.materialize_showcase(
        destination_path=tmp_path / "check_syntax",
        project_name="SyntaxCheck",
    )
    main_py = project_root / "main.py"
    source = main_py.read_text(encoding="utf-8")
    compile(source, str(main_py), "exec")


