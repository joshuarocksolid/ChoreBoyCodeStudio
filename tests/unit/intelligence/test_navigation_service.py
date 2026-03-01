"""Unit tests for go-to-definition lookup service."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence.navigation_service import lookup_definition

pytestmark = pytest.mark.unit


def test_lookup_definition_prefers_current_file_location(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    current = project_root / "current.py"
    other = project_root / "other.py"
    current.write_text("def target():\n    return 1\n", encoding="utf-8")
    other.write_text("def target():\n    return 2\n", encoding="utf-8")

    result = lookup_definition(str(project_root), str(current.resolve()), "target")

    assert result.found is True
    assert result.locations[0].file_path == str(current.resolve())
