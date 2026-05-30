"""Unit tests for vendor exclude migration on project open."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from app.core.models import LoadedProject, ProjectFileEntry, ProjectMetadata
from app.project.vendor_exclude_migration import maybe_persist_vendor_exclude

pytestmark = pytest.mark.unit


def _loaded_project(project_root: Path, *, exclude_patterns: list[str] | None = None) -> LoadedProject:
    metadata = ProjectMetadata(
        schema_version=1,
        name="Bench",
        exclude_patterns=list(exclude_patterns or []),
    )
    return LoadedProject(
        project_root=str(project_root.resolve()),
        manifest_path=str(project_root / "cbcs" / "project.json"),
        metadata=metadata,
        entries=[
            ProjectFileEntry(
                relative_path="main.py",
                absolute_path=str(project_root / "main.py"),
                is_directory=False,
            )
        ],
        manifest_materialized=True,
    )


def test_maybe_persist_vendor_exclude_writes_manifest_for_large_vendor_tree(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "cbcs").mkdir()
    manifest_path = project_root / "cbcs" / "project.json"
    manifest_path.write_text(
        json.dumps({"schema_version": 1, "name": "Bench", "default_entry": "main.py"}),
        encoding="utf-8",
    )
    vendor_dir = project_root / "vendor"
    vendor_dir.mkdir()
    for index in range(150):
        (vendor_dir / f"mod_{index:03d}.py").write_text("x=1\n", encoding="utf-8")

    updated = maybe_persist_vendor_exclude(
        _loaded_project(project_root),
        logger=logging.getLogger("test"),
    )

    assert updated.metadata.exclude_patterns == ["vendor"]
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["exclude_patterns"] == ["vendor"]


def test_maybe_persist_vendor_exclude_is_idempotent_when_manifest_already_excludes_vendor(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    vendor_dir = project_root / "vendor"
    vendor_dir.mkdir()
    for index in range(150):
        (vendor_dir / f"mod_{index:03d}.py").write_text("x=1\n", encoding="utf-8")

    loaded = _loaded_project(project_root, exclude_patterns=["vendor"])
    updated = maybe_persist_vendor_exclude(loaded, logger=logging.getLogger("test"))

    assert updated is loaded
