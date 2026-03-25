"""Unit tests for project packaging config helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.models import ProjectMetadata
from app.packaging.config import (
    build_default_package_config,
    load_or_create_project_package_config,
    parse_project_package_config,
    resolve_project_package_config,
)

pytestmark = pytest.mark.unit


def _project_metadata() -> ProjectMetadata:
    return ProjectMetadata(
        schema_version=1,
        name="My Project",
        project_id="proj_test_id",
        default_entry="main.py",
    )


def test_build_default_package_config_uses_project_name_and_entry() -> None:
    config = build_default_package_config(project_metadata=_project_metadata())

    assert config.package_id == "my_project"
    assert config.display_name == "My Project"
    assert config.version == "0.1.0"
    assert config.entry_file == "main.py"


def test_resolve_project_package_config_returns_defaults_without_writing(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    (project_root / "cbcs").mkdir(parents=True)

    config = resolve_project_package_config(
        project_root=str(project_root),
        project_metadata=_project_metadata(),
    )

    assert config.display_name == "My Project"
    assert not (project_root / "cbcs" / "package.json").exists()


def test_load_or_create_project_package_config_persists_defaults(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    (project_root / "cbcs").mkdir(parents=True)

    config = load_or_create_project_package_config(
        project_root=str(project_root),
        project_metadata=_project_metadata(),
    )

    assert config.package_id == "my_project"
    assert (project_root / "cbcs" / "package.json").is_file()


def test_parse_project_package_config_rejects_invalid_version() -> None:
    with pytest.raises(ValueError, match="version must use a stable dotted release format"):
        parse_project_package_config(
            {
                "schema_version": 1,
                "package_id": "my_project",
                "display_name": "My Project",
                "version": "bad-version",
            }
        )
