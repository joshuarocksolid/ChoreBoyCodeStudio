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
    """Materialized project should include injected `cbcs/project.json` fields."""
    service = TemplateService(templates_root=str(_repo_templates_root()))
    destination = tmp_path / "new_project"

    created = service.materialize_template(
        template_id="utility_script",
        destination_path=destination,
        project_name="My Utility Project",
    )

    manifest_path = created / "cbcs" / "project.json"
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


def test_materialize_template_ignores_legacy_hidden_metadata_directories(tmp_path: Path) -> None:
    """Legacy hidden metadata directories should never be copied into projects."""
    templates_root = tmp_path / "templates"
    template_dir = templates_root / "custom_template"
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "template.json").write_text(
        """
{
  "template_id": "custom_template",
  "display_name": "Custom",
  "description": "Custom template",
  "template_version": 1
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (template_dir / "main.py").write_text("print('hello')\n", encoding="utf-8")
    hidden_metadata_dir = template_dir / ".cbcs"
    hidden_metadata_dir.mkdir(parents=True, exist_ok=True)
    (hidden_metadata_dir / "legacy.txt").write_text("legacy\n", encoding="utf-8")

    service = TemplateService(templates_root=str(templates_root))
    destination = tmp_path / "generated_project"
    created = service.materialize_template(
        template_id="custom_template",
        destination_path=destination,
        project_name="Generated",
    )

    assert created == destination.resolve()
    assert (created / "main.py").exists()
    assert (created / ".cbcs").exists() is False
    assert (created / "cbcs" / "project.json").exists()
