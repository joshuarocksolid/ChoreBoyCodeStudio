"""Unit tests for Python import rewrite planning."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence.import_rewrite import apply_import_rewrites, plan_import_rewrites

pytestmark = pytest.mark.unit


def test_plan_import_rewrites_updates_import_lines(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "app").mkdir()
    (project_root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (project_root / "app" / "consumer.py").write_text(
        "from app.module import value\nimport app.module\nprint(value)\n",
        encoding="utf-8",
    )

    previews = plan_import_rewrites(
        str(project_root),
        old_relative_path="app/module.py",
        new_relative_path="app/new_module.py",
    )

    assert len(previews) == 1
    preview = previews[0]
    assert "app.new_module" in preview.updated_content
    assert preview.changed_line_numbers == [1, 2]


def test_apply_import_rewrites_writes_updated_payload(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    target_file = project_root / "consumer.py"
    target_file.write_text("import app.module\n", encoding="utf-8")

    previews = plan_import_rewrites(
        str(project_root),
        old_relative_path="app/module.py",
        new_relative_path="app/new_module.py",
    )
    updated_files = apply_import_rewrites(previews)

    assert str(target_file.resolve()) in updated_files
    assert "app.new_module" in target_file.read_text(encoding="utf-8")
