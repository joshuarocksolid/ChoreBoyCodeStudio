"""Unit tests for ExampleProjectService materialization."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.errors import AppValidationError
from app.examples.example_project_service import ExampleProjectService

pytestmark = pytest.mark.unit


def _repo_example_projects_root() -> Path:
    return Path(__file__).resolve().parents[3] / "example_projects"


def test_materialize_showcase_creates_project_with_manifest(tmp_path: Path) -> None:
    service = ExampleProjectService(examples_root=str(_repo_example_projects_root()))
    destination = tmp_path / "my_example"

    created = service.materialize_showcase(
        destination_path=destination,
        project_name="My Example",
    )

    manifest_path = created / ".cbcs" / "project.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["name"] == "My Example"
    assert manifest["template"] == "crud_showcase"
    assert manifest["default_entry"] == "main.py"


def test_materialize_showcase_copies_expected_files(tmp_path: Path) -> None:
    service = ExampleProjectService(examples_root=str(_repo_example_projects_root()))
    destination = tmp_path / "showcase"

    created = service.materialize_showcase(
        destination_path=destination,
        project_name="Showcase",
    )

    assert (created / "main.py").exists()
    assert (created / "app" / "main_window.py").exists()
    assert (created / "app" / "repository.py").exists()
    assert (created / "app" / "freecad_probe.py").exists()
    assert (created / "README.md").exists()


def test_materialize_showcase_rejects_non_empty_destination(tmp_path: Path) -> None:
    service = ExampleProjectService(examples_root=str(_repo_example_projects_root()))
    destination = tmp_path / "existing"
    destination.mkdir(parents=True)
    (destination / "blocker.txt").write_text("present", encoding="utf-8")

    with pytest.raises(AppValidationError, match="Destination is not empty"):
        service.materialize_showcase(
            destination_path=destination,
            project_name="Will Fail",
        )


def test_materialize_showcase_does_not_appear_in_template_list() -> None:
    """Example project must not pollute the New Project template picker."""
    from app.templates.template_service import TemplateService

    template_service = TemplateService()
    template_ids = [t.template_id for t in template_service.list_templates()]
    assert "crud_showcase" not in template_ids
