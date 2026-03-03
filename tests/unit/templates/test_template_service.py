"""Unit tests for template discovery and materialization."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import AppValidationError
from app.templates.template_service import TemplateService

pytestmark = pytest.mark.unit


def _repo_templates_root() -> Path:
    return Path(__file__).resolve().parents[3] / "templates"


def test_list_templates_discovers_expected_builtin_templates() -> None:
    """Template service should discover all built-in template IDs."""
    service = TemplateService(templates_root=str(_repo_templates_root()))
    template_ids = [template.template_id for template in service.list_templates()]

    assert template_ids == ["headless_tool", "qt_app", "utility_script"]


def test_materialize_template_injects_project_manifest(tmp_path: Path) -> None:
    """Materialized project should include injected `.cbcs/project.json` fields."""
    service = TemplateService(templates_root=str(_repo_templates_root()))
    destination = tmp_path / "new_project"

    created = service.materialize_template(
        template_id="utility_script",
        destination_path=destination,
        project_name="My Utility Project",
    )

    manifest_path = created / ".cbcs" / "project.json"
    assert manifest_path.exists()
    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert '"name": "My Utility Project"' in manifest_text
    assert '"default_entry": "main.py"' in manifest_text
    assert '"template": "utility_script"' in manifest_text


def test_materialize_template_rejects_non_empty_destination(tmp_path: Path) -> None:
    """Materialization should fail when destination already contains files."""
    service = TemplateService(templates_root=str(_repo_templates_root()))
    destination = tmp_path / "existing_project"
    destination.mkdir(parents=True)
    (destination / "existing.txt").write_text("already here", encoding="utf-8")

    with pytest.raises(AppValidationError, match="Destination is not empty"):
        service.materialize_template(
            template_id="utility_script",
            destination_path=destination,
            project_name="Will Fail",
        )
